"""NVD CVE lookup helper."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import requests


logger = logging.getLogger(__name__)


class CVELookup:
    """Query the NVD API for CVEs related to a software keyword."""

    SOFTWARE_RE = re.compile(r"\b(sshd|apache|nginx|mysql|php|openssh)\b", re.IGNORECASE)

    def _extract_keyword(self, text: str) -> str | None:
        match = self.SOFTWARE_RE.search(text)
        return match.group(1).lower() if match else None

    def lookup(self, keyword: str) -> list[dict[str, Any]]:
        if not keyword:
            return []

        api_key = os.getenv("NVD_API_KEY", "").strip()
        params = {"keywordSearch": keyword, "resultsPerPage": 3}
        if api_key:
            params["apiKey"] = api_key

        try:
            response = requests.get(
                "https://services.nvd.nist.gov/rest/json/cves/2.0",
                params=params,
                timeout=15,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.warning("CVE lookup failed for %s: %s", keyword, exc)
            return []

        results: list[dict[str, Any]] = []
        for item in payload.get("vulnerabilities", []):
            cve = item.get("cve", {})
            metrics = cve.get("metrics", {})
            cvss_score = None
            for metric_key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
                metric_list = metrics.get(metric_key)
                if metric_list:
                    cvss_score = metric_list[0].get("cvssData", {}).get("baseScore")
                    break

            results.append(
                {
                    "cve_id": cve.get("id", ""),
                    "description": next(
                        (
                            desc.get("value", "")
                            for desc in cve.get("descriptions", [])
                            if desc.get("lang") == "en"
                        ),
                        "",
                    ),
                    "cvss_score": cvss_score,
                }
            )
        return results
