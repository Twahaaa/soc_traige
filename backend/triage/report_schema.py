"""Pydantic schema for structured triage reports."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class IPReputation(BaseModel):
    ip: str
    abuse_score: int
    country: str
    isp: str
    total_reports: int


class MITREAttack(BaseModel):
    technique_id: str
    technique_name: str
    tactic: str
    description: str


class TriageReport(BaseModel):
    incident_id: str
    timestamp: str
    severity: Literal["Critical", "High", "Medium", "Low", "Informational"]
    title: str
    affected_host: str
    log_source: str
    anomaly_score: float
    description: str
    evidence: list[str] = Field(default_factory=list)
    cve_references: list[str] = Field(default_factory=list)
    ip_reputation: Optional[IPReputation] = None
    mitre_attack: Optional[MITREAttack] = None
    remediation_steps: list[str] = Field(default_factory=list)
    similar_past_incidents: list[str] = Field(default_factory=list)
    detection_source: str
