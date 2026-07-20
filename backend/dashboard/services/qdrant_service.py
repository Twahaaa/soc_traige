"""Async Qdrant query service for the dashboard.

Every method reads stored ``TriageReport`` payloads from the ``triage_reports``
collection (the one ``triage.agent.TriageAgent`` writes to). No data is invented
here — the API only ever returns what the upstream pipeline actually produced.

Uses the async ``AsyncQdrantClient`` so FastAPI workers stay non-blocking.
"""

from __future__ import annotations

import logging
from typing import Optional

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qdrant_models

from dashboard.config_loader import triage_reports_collection
from dashboard.schemas import (
    HostStatOut,
    MITREAttackOut,
    MitreCountOut,
    IPReputationOut,
    StatsOut,
    TriageReportOut,
    TimelineEventOut,
)
from triage.report_schema import TriageReport

logger = logging.getLogger(__name__)

# higher caps cost real memory; dashboard only shows recent activity
_SCROLL_HARD_CAP = 1000
_SEVERITY_RANK = {
    "Critical": 4,
    "High": 3,
    "Medium": 2,
    "Low": 1,
    "Informational": 0,
}
_ALL_SEVERITIES = ("Critical", "High", "Medium", "Low", "Informational")


class QdrantService:
    def __init__(self, client: AsyncQdrantClient) -> None:
        self._client = client
        self._collection = triage_reports_collection()

    async def _scroll_payloads(
        self,
        severity: Optional[str] = None,
        limit: int = _SCROLL_HARD_CAP,
    ) -> list[dict]:
        """Scroll stored payloads (no vectors), optionally filtered by severity."""
        scroll_filter = None
        if severity:
            scroll_filter = qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="severity",
                        match=qdrant_models.MatchValue(value=severity),
                    )
                ]
            )
        try:
            points, _next_offset = await self._client.scroll(
                collection_name=self._collection,
                scroll_filter=scroll_filter,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:
            logger.warning("Qdrant scroll failed: %s", exc)
            return []
        return [p.payload or {} for p in points]

    async def list_reports(
        self,
        severity: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[TriageReportOut], int]:
        payloads = await self._scroll_payloads(severity=severity)
        # newest first
        payloads.sort(key=lambda p: p.get("timestamp", ""), reverse=True)
        total = len(payloads)
        page = payloads[offset : offset + limit]
        return [self._to_report_out(p) for p in page], total

    async def get_report(self, incident_id: str) -> Optional[TriageReportOut]:
        try:
            points = await self._client.retrieve(
                collection_name=self._collection,
                ids=[incident_id],
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:
            logger.warning("Qdrant retrieve failed for %s: %s", incident_id, exc)
            return None
        if not points:
            return None
        return self._to_report_out(points[0].payload or {})

    async def compute_stats(self, window_hours: int = 24) -> StatsOut:
        payloads = await self._scroll_payloads()
        severity_distribution = {sev: 0 for sev in _ALL_SEVERITIES}
        mitre_counts: dict[str, dict[str, str]] = {}
        mitre_totals: dict[str, int] = {}
        host_totals: dict[str, int] = {}
        host_highest: dict[str, str] = {}
        host_last_seen: dict[str, str] = {}
        total_alerts_24h = 0

        for p in payloads:
            sev = p.get("severity")
            if sev in severity_distribution:
                severity_distribution[sev] += 1
            ts = p.get("timestamp", "")
            host = p.get("affected_host", "unknown")
            host_totals[host] = host_totals.get(host, 0) + 1
            if sev and _SEVERITY_RANK.get(sev, 0) > _SEVERITY_RANK.get(host_highest.get(host, ""), 0):
                host_highest[host] = sev
            if ts > host_last_seen.get(host, ""):
                host_last_seen[host] = ts
            if self._within_hours(ts, window_hours):
                total_alerts_24h += 1
            mitre = p.get("mitre_attack")
            if isinstance(mitre, dict):
                tid = mitre.get("technique_id")
                if tid:
                    mitre_totals[tid] = mitre_totals.get(tid, 0) + 1
                    mitre_counts.setdefault(tid, {
                        "technique_id": tid,
                        "technique_name": mitre.get("technique_name", ""),
                    })

        top_mitre = [
            MitreCountOut(
                technique_id=info["technique_id"],
                technique_name=info["technique_name"],
                count=mitre_totals[tid],
            )
            for tid, info in sorted(mitre_counts.items(), key=lambda kv: kv[1], reverse=True)[:8]
        ]
        top_hosts = [
            HostStatOut(
                host=h,
                count=host_totals[h],
                highest_severity=host_highest.get(h, "Informational"),
                last_seen=host_last_seen.get(h, ""),
            )
            for h in sorted(host_totals, key=host_totals.get, reverse=True)[:8]
        ]
        return StatsOut(
            total_alerts_24h=total_alerts_24h,
            total_alerts_all=len(payloads),
            severity_distribution=severity_distribution,
            top_mitre=top_mitre,
            top_hosts=top_hosts,
        )

    async def list_host_stats(self, limit: int = 20) -> list[HostStatOut]:
        stats = await self.compute_stats()
        return stats.top_hosts[:limit]

    async def list_timeline_events(self, limit: int = 100) -> list[TimelineEventOut]:
        payloads = await self._scroll_payloads()
        payloads.sort(key=lambda p: p.get("timestamp", ""), reverse=True)
        events = []
        for p in payloads[:limit]:
            events.append(
                TimelineEventOut(
                    incident_id=p.get("incident_id", ""),
                    timestamp=p.get("timestamp", ""),
                    severity=p.get("severity", "Informational"),
                    title=p.get("title", ""),
                    host=p.get("affected_host", "unknown"),
                    anomaly_score=float(p.get("anomaly_score", 0.0)),
                )
            )
        return events

    @staticmethod
    def _within_hours(ts: str, hours: int) -> bool:
        if not ts:
            return False
        try:
            from datetime import datetime, timedelta, timezone

            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return False
        now = datetime.now(timezone.utc)
        return dt >= now - timedelta(hours=hours)

    @staticmethod
    def _to_report_out(payload: dict) -> TriageReportOut:
        # Validate via the canonical Pydantic model so unknown / malformed
        # payloads are rejected rather than silently surfacing as nulls.
        report = TriageReport.model_validate(payload)
        ip = None
        if report.ip_reputation is not None:
            ip = IPReputationOut(
                ip=report.ip_reputation.ip,
                abuse_score=report.ip_reputation.abuse_score,
                country=report.ip_reputation.country,
                isp=report.ip_reputation.isp,
                total_reports=report.ip_reputation.total_reports,
            )
        mitre = None
        if report.mitre_attack is not None:
            mitre = MITREAttackOut(
                technique_id=report.mitre_attack.technique_id,
                technique_name=report.mitre_attack.technique_name,
                tactic=report.mitre_attack.tactic,
                description=report.mitre_attack.description,
            )
        return TriageReportOut(
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
            ip_reputation=ip,
            mitre_attack=mitre,
            remediation_steps=report.remediation_steps,
            similar_past_incidents=report.similar_past_incidents,
            detection_source=report.detection_source,
        )