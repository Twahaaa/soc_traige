"""Health endpoint — probes each backing component with a real request.

No hardcoded or mock status values. The dashboard StatusBar renders these
component names verbatim, so changing a name here changes the UI label.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter

from dashboard.config_loader import get_async_qdrant, get_async_redis, load_config
from dashboard.schemas import HealthOut, SystemStatusOut

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthOut)
async def get_health() -> HealthOut:
    components: list[SystemStatusOut] = []

    # Redis
    try:
        redis = get_async_redis()
        pong = await redis.ping()
        await redis.aclose()
        components.append(
            SystemStatusOut(
                name="Redis Streams",
                status="ok" if pong else "error",
                detail="PING ok" if pong else "PING returned no pong",
            )
        )
    except Exception as exc:
        components.append(
            SystemStatusOut(name="Redis Streams", status="error", detail=str(exc)[:120])
        )

    # Qdrant
    try:
        qdrant = get_async_qdrant()
        collection = load_config()["qdrant"]["collection"]
        info = await qdrant.get_collection(collection_name=collection)
        count = getattr(info, "points_count", None) or 0
        await qdrant.close()
        components.append(
            SystemStatusOut(
                name="Qdrant",
                status="ok",
                detail=f"collection {collection} · {count} points",
            )
        )
    except Exception as exc:
        components.append(
            SystemStatusOut(name="Qdrant", status="error", detail=str(exc)[:120])
        )

    # Ollama (optional local LLM fallback — health is best-effort)
    try:
        cfg = load_config()["llm"]["providers"]["ollama"]
        base_url = cfg.get("base_url", "http://localhost:11434")
        async with httpx.AsyncClient(timeout=1.5) as client:
            resp = await client.get(f"{base_url}/api/tags")
        ok = resp.status_code == 200
        components.append(
            SystemStatusOut(
                name="Ollama LLM",
                status="ok" if ok else "warn",
                detail=f"{cfg.get('model','?')} @ {base_url}",
            )
        )
    except Exception as exc:
        components.append(
            SystemStatusOut(name="Ollama LLM", status="warn", detail="not reachable (optional)")
        )

    return HealthOut(components=components)