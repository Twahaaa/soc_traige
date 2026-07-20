"""Async Redis stream bridge for the WebSocket alert feed.

Reads new ``TriageReport`` entries from ``stream:triage_reports`` belonging to
consumer group ``group:dashboard`` (pre-declared by ``queue.redis_manager``)
and forwards each parsed ``TriageReportOut`` to the WebSocket layer.

Design:
- One ``asyncio.Task`` per running app reads the stream in a tight loop and
  pushes parsed reports into an internal ``asyncio.Queue``-like bus of
  subscriber queues. WS clients subscribe by registering a queue and are
  unregistered on disconnect — so a slow client never blocks the reader.
- The consumer group is created idempotently on startup (``MKSTREAM`` set).
- Reads with ``XREADGROUP group=group:dashboard consumer=dash-<id> streams=stream:triage_reports >``
  blocking up to a few seconds, then ACKs delivered messages.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import AsyncIterator, Optional

import redis.asyncio as aioredis

from dashboard.config_loader import (
    dashboard_consumer_group,
    get_async_redis,
    triage_reports_stream,
)
from dashboard.schemas import IPReputationOut, MITREAttackOut, TriageReportOut
from triage.report_schema import TriageReport

logger = logging.getLogger(__name__)

BLOCK_MS = 2000
BATCH_SIZE = 50


class RedisStreamBridge:
    """Owns one stream-reader task; subscribers register per-connection queues."""

    def __init__(self) -> None:
        self._client: Optional[aioredis.Redis] = None
        self._consumer = f"dash-{uuid.uuid4().hex[:8]}"
        self._task: Optional[asyncio.Task] = None
        self._subscribers: set[asyncio.Queue] = set()
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._client = get_async_redis()
        await self._ensure_group()
        self._task = asyncio.create_task(self._read_loop(), name="dashboard-redis-reader")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _ensure_group(self) -> None:
        assert self._client is not None
        stream = triage_reports_stream()
        group = dashboard_consumer_group()
        try:
            await self._client.xgroup_create(stream, group, id="$", mkstream=True)
            logger.info("Created consumer group %s for %s", group, stream)
        except aioredis.ResponseError as exc:
            if "BUSYGROUP" in str(exc):
                logger.info("Consumer group %s already exists for %s", group, stream)
            else:
                raise

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    async def _read_loop(self) -> None:
        assert self._client is not None
        stream = triage_reports_stream()
        group = dashboard_consumer_group()
        while not self._stop.is_set():
            try:
                resp = await self._client.xreadgroup(
                    groupname=group,
                    consumername=self._consumer,
                    streams={stream: ">"},
                    count=BATCH_SIZE,
                    block=BLOCK_MS,
                )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("xreadgroup failed: %s", exc)
                await asyncio.sleep(1)
                continue
            if not resp:
                continue
            for _stream, messages in resp:
                for msg_id, fields in messages:
                    self._dispatch(fields)
                    try:
                        await self._client.xack(stream, group, msg_id)
                    except Exception as exc:
                        logger.warning("xack failed for %s: %s", msg_id, exc)

    def _dispatch(self, fields: dict) -> None:
        raw = fields.get("report")
        if not raw:
            return
        try:
            report = TriageReport.model_validate_json(raw)
        except Exception as exc:
            logger.warning("Failed to parse triage report from stream: %s", exc)
            return
        out = TriageReportOut(
            incident_id=report.incident_id,
            timestamp=report.timestamp,
            severity=report.severity,
            title=report.title,
            affected_host=report.affected_host,
            log_source=report.log_source,
            anomaly_score=report.anomaly_score,
            description=report.description,
            evidence=report.evidence,
            cve_references=report.cve_references,
            ip_reputation=None
            if report.ip_reputation is None
            else IPReputationOut(
                ip=report.ip_reputation.ip,
                abuse_score=report.ip_reputation.abuse_score,
                country=report.ip_reputation.country,
                isp=report.ip_reputation.isp,
                total_reports=report.ip_reputation.total_reports,
            ),
            mitre_attack=None
            if report.mitre_attack is None
            else MITREAttackOut(
                technique_id=report.mitre_attack.technique_id,
                technique_name=report.mitre_attack.technique_name,
                tactic=report.mitre_attack.tactic,
                description=report.mitre_attack.description,
            ),
            remediation_steps=report.remediation_steps,
            similar_past_incidents=report.similar_past_incidents,
            detection_source=report.detection_source,
        )
        for q in list(self._subscribers):
            try:
                q.put_nowait(out)
            except asyncio.QueueFull:
                # slow client — drop this message for them rather than block the reader
                logger.warning("subscriber queue full, dropping report %s", out.incident_id)

    async def stream(self) -> AsyncIterator[TriageReportOut]:
        """Async generator for a single WS connection; cleanup on cancellation."""
        q = self.subscribe()
        try:
            while not self._stop.is_set():
                yield await q.get()
        finally:
            self.unsubscribe(q)