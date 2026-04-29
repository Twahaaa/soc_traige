"""BGL dataset loader for NeuralLog training."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

from preprocessing.sequence_builder import tokenize_log_line


def _extract_bgl_timestamp(line: str) -> str:
    parts = line.split()
    if len(parts) >= 3:
        return f"{parts[1]} {parts[2]}"
    if len(parts) >= 2:
        return parts[1]
    return ""


def _is_anomalous_bgl_line(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("-")


class BGLLoader:
    """Load BGL log windows using a chronological sliding window."""

    def load_sequences(
        self,
        data_dir: str,
        window_size: int = 20,
        step_size: int = 1,
    ) -> Iterator[dict[str, Any]]:
        """Yield sliding windows with labels derived from anomalous lines."""
        if window_size <= 0:
            raise ValueError("window_size must be greater than zero")
        if step_size <= 0:
            raise ValueError("step_size must be greater than zero")

        log_path = Path(data_dir) / "BGL.log"
        if not log_path.exists():
            raise FileNotFoundError(f"Missing BGL log file: {log_path}")

        records: list[dict[str, Any]] = []
        with log_path.open("r", encoding="utf-8", errors="ignore") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue

                records.append(
                    {
                        "tokens": tokenize_log_line(line),
                        "raw_line": line,
                        "timestamp": _extract_bgl_timestamp(line),
                        "label": 1 if _is_anomalous_bgl_line(line) else 0,
                    }
                )

        if len(records) < window_size:
            return

        for start_index in range(0, len(records) - window_size + 1, step_size):
            window = records[start_index : start_index + window_size]
            label = 1 if any(entry["label"] == 1 for entry in window) else 0

            yield {
                "sequence": [entry["tokens"] for entry in window],
                "raw_lines": [entry["raw_line"] for entry in window],
                "priority": "critical" if label == 1 else "normal",
                "window_start_ts": window[0]["timestamp"],
                "window_end_ts": window[-1]["timestamp"],
                "source": "bgl",
                "label": label,
            }
