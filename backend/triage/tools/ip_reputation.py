"""AbuseIPDB reputation lookup helper."""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

import requests

from triage.report_schema import IPReputation


logger = logging.getLogger(__name__)


class IPReputationChecker:
    """Query AbuseIPDB and extract public IP addresses from logs."""

    PRIVATE_PATTERNS = (
        re.compile(r"^10\."),
        re.compile(r"^192\.168\."),
        re.compile(r"^172\.(1[6-9]|2\d|3[0-1])\."),
        re.compile(r"^127\."),
    )

    def check(self, ip: str) -> Optional[IPReputation]:
        api_key = os.getenv("ABUSEIPDB_API_KEY", "").strip()
        if not api_key:
            logger.warning("ABUSEIPDB_API_KEY is not set; skipping IP reputation lookup")
            return None

        try:
            response = requests.get(
                "https://api.abuseipdb.com/api/v2/check",
                params={"ipAddress": ip, "maxAgeInDays": 90},
                headers={"Key": api_key, "Accept": "application/json"},
                timeout=15,
            )
            response.raise_for_status()
            data = response.json().get("data", {})
        except Exception as exc:
            logger.warning("IP reputation lookup failed for %s: %s", ip, exc)
            return None

        return IPReputation(
            ip=ip,
            abuse_score=int(data.get("abuseConfidenceScore", 0)),
            country=str(data.get("countryCode", "")),
            isp=str(data.get("isp", "")),
            total_reports=int(data.get("totalReports", 0)),
        )

    def extract_public_ip(self, log_lines: list[str]) -> Optional[str]:
        for line in log_lines:
            for match in re.findall(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", line):
                if not any(pattern.match(match) for pattern in self.PRIVATE_PATTERNS):
                    return match
        return None

    @staticmethod
    def extract_public_ip_from_text(log_text: str) -> Optional[str]:
        """Extract the first non-private IPv4 address from a block of text."""
        for match in re.findall(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", log_text):
            if not any(
                pattern.match(match)
                for pattern in (
                    re.compile(r"^10\."),
                    re.compile(r"^192\.168\."),
                    re.compile(r"^172\.(1[6-9]|2\d|3[0-1])\."),
                    re.compile(r"^127\."),
                )
            ):
                return match
        return None
