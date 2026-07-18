"""Prompt builder for deterministic triage reports."""

from __future__ import annotations

from typing import Any


def build_prompt(
    raw_lines: list[str],
    anomaly_score: float,
    detection_source: str,
    mitre_result: Any,
    ip_result: Any,
    cve_results: list[dict[str, Any]],
    similar_incidents: list[dict[str, Any]],
) -> str:
    evidence = "\n".join(f"- {line}" for line in raw_lines)
    prompt = f"""You are a SOC analyst assistant.

Evidence:
{evidence}

Anomaly score: {anomaly_score:.3f}
Detection source: {detection_source}

MITRE match: {mitre_result}
IP reputation: {ip_result}
CVE results: {cve_results}
Similar incidents: {similar_incidents}

Severity rules:
- Critical: active exploitation, privilege escalation success, reverse shell indicator
- High: brute force with successful login, known malware pattern
- Medium: brute force without successful login, port scanning
- Low: single failed login, anomalous but low-confidence
- Informational: anomaly score triggered but no clear threat

Respond with ONLY a JSON object matching this exact schema (no markdown, no code fences, no explanation):

{{
  "severity": "Critical|High|Medium|Low|Informational",
  "title": "short one-line summary of the incident",
  "description": "1-3 sentence analyst narrative explaining what happened",
  "remediation_steps": ["step 1", "step 2", "..."]
}}

Do NOT include any other fields. Do NOT echo the input evidence.
"""
    return prompt
