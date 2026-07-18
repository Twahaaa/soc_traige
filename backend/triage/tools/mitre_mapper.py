"""MITRE ATT&CK technique mapper."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from triage.report_schema import MITREAttack


logger = logging.getLogger(__name__)


class MITREMapper:
    def __init__(self, techniques_path: str = "data/mitre/techniques.json") -> None:
        path = Path(techniques_path)
        if not path.exists():
            self.techniques: list[dict[str, object]] = []
            return
        with path.open("r", encoding="utf-8") as handle:
            self.techniques = json.load(handle)

    @staticmethod
    def _score_technique(joined_text: str, technique: dict[str, Any]) -> int:
        keywords = [str(keyword).lower() for keyword in technique.get("keywords", [])]
        return sum(1 for keyword in keywords if keyword in joined_text)

    def map(self, log_lines: list[str]) -> Optional[MITREAttack]:
        joined = " ".join(log_lines).lower()
        best_match: tuple[int, dict[str, object]] | None = None

        for technique in self.techniques:
            count = self._score_technique(joined, technique)
            if count and (best_match is None or count > best_match[0]):
                best_match = (count, technique)

        if best_match is None:
            return None

        technique = best_match[1]
        return MITREAttack(
            technique_id=str(technique.get("technique_id", "")),
            technique_name=str(technique.get("technique_name", "")),
            tactic=str(technique.get("tactic", "")),
            description=str(technique.get("description", "")),
        )
