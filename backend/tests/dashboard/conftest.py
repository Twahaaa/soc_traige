"""Test fixtures: in-memory async Qdrant fake + sample TriageReport payload.

The Qdrant fake implements the subset of ``AsyncQdrantClient`` used by
``QdrantService``: ``scroll``, ``retrieve``, ``get_collection``, ``close``.
All other calls raise — tests fail loud if a route reaches beyond the fake.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from uuid import uuid4

import pytest
from qdrant_client.http import models as qdrant_models


def make_report_payload(
    *,
    severity: str = "Critical",
    title: str = "Brute-force login burst from 203.0.113.5",
    affected_host: str = "mail-svr-01",
    anomaly_score: float = 0.92,
    log_source: str = "hdfs",
    include_mitre: bool = True,
    include_ip: bool = True,
    timestamp_offset_seconds: int = 0,
) -> dict[str, Any]:
    ts = datetime.now(timezone.utc) - timedelta(seconds=timestamp_offset_seconds)
    return {
        "incident_id": str(uuid4()),
        "timestamp": ts.isoformat(),
        "severity": severity,
        "title": title,
        "affected_host": affected_host,
        "log_source": log_source,
        "anomaly_score": anomaly_score,
        "description": "Multiple failed SSH logins from a single source within 60s.",
        "evidence": [
            "Jan 30 14:35:01 mail-svr-01 sshd[2103]: Failed password for root from 203.0.113.5 port 51000",
            "Jan 30 14:35:09 mail-svr-01 sshd[2105]: Failed password for root from 203.0.113.5 port 51001",
        ],
        "cve_references": ["CVE-2024-6387"],
        "ip_reputation": (
            {
                "ip": "203.0.113.5",
                "abuse_score": 87,
                "country": "RU",
                "isp": "Example ISP",
                "total_reports": 412,
            }
            if include_ip
            else None
        ),
        "mitre_attack": (
            {
                "technique_id": "T1110",
                "technique_name": "Brute Force",
                "tactic": "Credential Access",
                "description": "Adversary attempts many passwords against authentication.",
            }
            if include_mitre
            else None
        ),
        "remediation_steps": [
            "Block source IP at firewall",
            "Disable root SSH login",
        ],
        "similar_past_incidents": ["INC-20240429-0017"],
        "detection_source": "prefilter",
    }


@dataclass
class _Point:
    id: str
    payload: dict


@dataclass
class _CollectionInfo:
    points_count: int


class FakeAsyncQdrantClient:
    """In-memory subset of qdrant_client.AsyncQdrantClient."""

    def __init__(self) -> None:
        self._points: list[_Point] = []
        self._closed = False

    # helpers used by tests
    def seed(self, payload: dict) -> None:
        self._points.append(_Point(id=payload["incident_id"], payload=dict(payload)))

    def upsert(self, *, collection_name, points, **_):
        for p in points:
            self._points = [x for x in self._points if x.id != p.id]
            self._points.append(_Point(id=p.id, payload=p.payload or {}))

    async def scroll(self, *, collection_name, scroll_filter=None, limit=10, with_payload=True, with_vectors=False):
        rows = list(self._points)
        if scroll_filter is not None:
            must = getattr(scroll_filter, "must", None) or []
            for cond in must:
                key = cond.key
                value = cond.match.value
                rows = [r for r in rows if r.payload.get(key) == value]
        return rows[:limit], None

    async def retrieve(self, *, collection_name, ids, with_payload=True, with_vectors=False):
        out = []
        for r in self._points:
            if str(r.id) in [str(i) for i in ids]:
                out.append(r)
        return out

    async def get_collection(self, *, collection_name):
        return _CollectionInfo(points_count=len(self._points))

    async def close(self):
        self._closed = True


@pytest.fixture
def fake_qdrant():
    return FakeAsyncQdrantClient()


@pytest.fixture
def seeded_qdrant(fake_qdrant):
    fake_qdrant.seed(make_report_payload(severity="Critical", title="SSH brute force", affected_host="mail-svr-01", timestamp_offset_seconds=60))
    fake_qdrant.seed(make_report_payload(severity="High", title="Suspicious sudo command", affected_host="web-svr-02", timestamp_offset_seconds=3600))
    fake_qdrant.seed(make_report_payload(severity="Medium", title="Unusual outbound DNS", affected_host="firewall-01", timestamp_offset_seconds=7200, include_mitre=False))
    return fake_qdrant


class FakeBridge:
    """Async-iterable substitute for RedisStreamBridge."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue = asyncio.Queue()
        self._subscribed = False

    async def push(self, report_dict: dict) -> None:
        from dashboard.schemas import TriageReportOut
        await self._queue.put(TriageReportOut.model_validate(report_dict))

    async def stream(self):
        self._subscribed = True
        try:
            while True:
                item = await self._queue.get()
                yield item
        except asyncio.CancelledError:
            return


@pytest.fixture
def fake_bridge():
    return FakeBridge()