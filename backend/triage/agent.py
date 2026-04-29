"""Stage-3-safe triage handoff that returns a structured report."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from triage.report_schema import TriageReport


logger = logging.getLogger(__name__)


class TriageAgent:
    """Create a minimal valid triage report for Stage 3 queue handoff."""

    def run(self, sequence_message: dict[str, Any]) -> TriageReport:
        raw_lines = [str(line) for line in sequence_message.get("raw_lines", [])]
        anomaly_score = float(sequence_message.get("anomaly_score", 0.0))
        detection_source = str(sequence_message.get("detection_source", "unknown"))
        affected_host = self._extract_host(raw_lines)
        severity = self._classify_severity(raw_lines, anomaly_score)

        report = TriageReport(
            incident_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            severity=severity,
            title=f"{severity} anomaly on {affected_host}",
            affected_host=affected_host,
            log_source=str(sequence_message.get("source", "synthetic")),
            anomaly_score=anomaly_score,
            description="Stage 3 triage handoff placeholder. Full LLM triage is implemented in Stage 4.",
            evidence=raw_lines,
            cve_references=[],
            ip_reputation=None,
            mitre_attack=None,
            remediation_steps=["Review the related logs and confirm the alert context."],
            similar_past_incidents=[],
            detection_source=detection_source,
        )
        logger.info("Created stage-3 triage report %s", report.incident_id)
        return report

    def _extract_host(self, raw_lines: list[str]) -> str:
        if not raw_lines:
            return "unknown"
        first_line = raw_lines[0]
        parts = first_line.split()
        if len(parts) >= 3:
            return parts[2].rstrip(":")
        return "unknown"

    def _classify_severity(self, raw_lines: list[str], anomaly_score: float) -> str:
        joined = " ".join(raw_lines).lower()
        if "critical" in joined or "reverse shell" in joined or "/bin/bash" in joined:
            return "Critical"
        if anomaly_score >= 0.85:
            return "High"
        if anomaly_score >= 0.65:
            return "Medium"
        return "Low"
