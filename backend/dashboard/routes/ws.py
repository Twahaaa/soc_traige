"""WebSocket endpoint for streaming new triage reports to the dashboard.

Protocol:
- On connect: server sends a JSON ``{"type": "snapshot", "items": [...]}`` with
  the latest stored reports (via Qdrant), so the frontend can hydrate
  immediately.
- New reports from the Redis stream are sent as
  ``{"type": "report", "item": {...}}``.
- On client disconnect, the per-connection queue is unregistered from the
  bridge so the reader task never blocks on a dead consumer.

The bridge singleton lives on ``app.state.bridge`` (see ``dashboard.main``).
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from qdrant_client import AsyncQdrantClient

from dashboard.config_loader import get_async_qdrant
from dashboard.services.qdrant_service import QdrantService
from dashboard.services.redis_service import RedisStreamBridge

router = APIRouter()
logger = logging.getLogger(__name__)

SNAPSHOT_LIMIT = 50


@router.websocket("/ws/reports")
async def report_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    bridge: RedisStreamBridge = websocket.app.state.bridge

    # 1. initial snapshot
    try:
        qdrant = get_async_qdrant()
        svc = QdrantService(qdrant)
        items, _total = await svc.list_reports(limit=SNAPSHOT_LIMIT)
        await qdrant.close()
        await websocket.send_text(
            json.dumps({"type": "snapshot", "items": [item.model_dump() for item in items]})
        )
    except Exception as exc:
        logger.warning("WS snapshot failed: %s", exc)
        await websocket.send_text(json.dumps({"type": "snapshot", "items": []}))

    # 2. live stream
    try:
        async for report in bridge.stream():
            await websocket.send_text(
                json.dumps({"type": "report", "item": report.model_dump()})
            )
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("WS stream ended: %s", exc)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass