"""Pre-filter for critical log detection."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List


class PreFilter:
    """Rule-based pre-filter that flags critical log lines."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.critical_keywords: List[str] = config["prefilter"]["critical_keywords"]
        self.auth_fail_threshold: int = config["prefilter"]["auth_fail_threshold"]
        self.auth_fail_window_seconds: int = config["prefilter"]["auth_fail_window_seconds"]
        self.privilege_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in config["prefilter"]["privilege_escalation_patterns"]
        ]
        self.failed_auth_timestamps: Dict[str, List[float]] = defaultdict(list)
        self.failed_password_re = re.compile(r"Failed password", re.IGNORECASE)
        self.ip_re = re.compile(r"from (\d+\.\d+\.\d+\.\d+)")

    def check(self, log_line: str, timestamp: float) -> Dict[str, Any]:
        """Return priority and reason for a given log line."""
        for keyword in self.critical_keywords:
            if keyword in log_line:
                return {"priority": "critical", "reason": f"keyword_match:{keyword}"}

        for pattern in self.privilege_patterns:
            if pattern.search(log_line):
                return {"priority": "critical", "reason": "privilege_escalation"}

        if self.failed_password_re.search(log_line):
            ip_match = self.ip_re.search(log_line)
            if ip_match:
                ip = ip_match.group(1)
                self._record_failure(ip, timestamp)
                if self._is_bruteforce(ip):
                    return {"priority": "critical", "reason": f"brute_force:{ip}"}

        return {"priority": "normal", "reason": None}

    def _record_failure(self, ip: str, timestamp: float) -> None:
        """Record failed login timestamp and prune old entries."""
        # Keep only failures inside the rolling time window.
        window_start = timestamp - self.auth_fail_window_seconds
        timestamps = self.failed_auth_timestamps[ip]
        timestamps.append(timestamp)
        self.failed_auth_timestamps[ip] = [ts for ts in timestamps if ts >= window_start]

    def _is_bruteforce(self, ip: str) -> bool:
        """Return True if failures exceed the configured threshold."""
        # Threshold is strict so it triggers after N+1 events.
        return len(self.failed_auth_timestamps[ip]) > self.auth_fail_threshold
