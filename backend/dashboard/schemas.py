"""Pydantic response models for the dashboard API.

These mirror ``triage.report_schema`` field names verbatim (snake_case) so the
backend's internal ``TriageReport.model_dump()`` serialises straight into these
models without any aliasing. The Next.js frontend types are written against the
exact same field set — one source of truth.

Stats / hosts / timeline / health models are NEW aggregated shapes derived
from stored ``TriageReport`` payloads (no synthetic fields).
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


Severity = Literal["Critical", "High", "Medium", "Low", "Informational"]


class IPReputationOut(BaseModel):
    ip: str
    abuse_score: int
    country: str
    isp: str
    total_reports: int


class MITREAttackOut(BaseModel):
    technique_id: str
    technique_name: str
    tactic: str
    description: str


class TriageReportOut(BaseModel):
    """Wire shape returned by every report endpoint. Identical to backend TriageReport."""

    incident_id: str
    timestamp: str
    severity: Severity
    title: str
    affected_host: str
    log_source: str
    anomaly_score: float
    description: str
    evidence: list[str] = Field(default_factory=list)
    cve_references: list[str] = Field(default_factory=list)
    ip_reputation: Optional[IPReputationOut] = None
    mitre_attack: Optional[MITREAttackOut] = None
    remediation_steps: list[str] = Field(default_factory=list)
    similar_past_incidents: list[str] = Field(default_factory=list)
    detection_source: str


class MitreCountOut(BaseModel):
    technique_id: str
    technique_name: str
    count: int


class HostStatOut(BaseModel):
    host: str
    count: int
    highest_severity: Severity
    last_seen: str


class StatsOut(BaseModel):
    """Aggregated stats derived from stored TriageReports."""

    total_alerts_24h: int
    total_alerts_all: int
    severity_distribution: dict[Severity, int]
    top_mitre: list[MitreCountOut]
    top_hosts: list[HostStatOut]


class TimelineEventOut(BaseModel):
    """Projected timeline event derived from a stored TriageReport."""

    incident_id: str
    timestamp: str
    severity: Severity
    title: str
    host: str
    anomaly_score: float


class SystemStatusOut(BaseModel):
    name: str
    status: Literal["ok", "warn", "error"]
    detail: str


class HealthOut(BaseModel):
    components: list[SystemStatusOut]


class ReportListOut(BaseModel):
    """Envelope for paginated report listing."""

    items: list[TriageReportOut]
    total: int
    limit: int
    offset: int