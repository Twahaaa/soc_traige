"""HDFS dataset loader for NeuralLog training."""

from __future__ import annotations

import csv
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterator

from preprocessing.sequence_builder import tokenize_log_line


BLOCK_ID_RE = re.compile(r"(blk_[A-Za-z0-9-]+)")
NORMAL_LABELS = {"0", "normal", "norm", "false", "no"}
ANOMALY_LABELS = {"1", "anomaly", "anomalous", "abnormal", "true", "yes"}


def _parse_label(value: str) -> int:
    normalized = value.strip().lower()
    if normalized in ANOMALY_LABELS:
        return 1
    if normalized in NORMAL_LABELS:
        return 0
    return 1 if "anom" in normalized else 0


def _extract_hdfs_timestamp(line: str) -> str:
    parts = line.split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1]}"
    return ""


def _load_label_map(label_path: Path) -> dict[str, int]:
    label_map: dict[str, int] = {}

    with label_path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
        reader = csv.reader(handle)
        for index, row in enumerate(reader):
            if not row:
                continue

            first_cell = row[0].strip()
            second_cell = row[1].strip() if len(row) > 1 else "0"

            if index == 0 and not first_cell.startswith("blk_"):
                if any("block" in cell.lower() for cell in row) and any("label" in cell.lower() for cell in row):
                    continue

            if first_cell.startswith("blk_"):
                label_map[first_cell] = _parse_label(second_cell)

    return label_map


class HDFSLoader:
    """Load HDFS block sequences grouped by block identifier."""

    def load_sequences(self, data_dir: str) -> Iterator[dict[str, Any]]:
        """Yield tokenized block sequences with anomaly labels."""
        base_dir = Path(data_dir)
        log_path = base_dir / "HDFS.log"
        label_path = base_dir / "anomaly_label.csv"

        if not log_path.exists():
            raise FileNotFoundError(f"Missing HDFS log file: {log_path}")
        if not label_path.exists():
            raise FileNotFoundError(f"Missing HDFS label file: {label_path}")

        label_map = _load_label_map(label_path)
        grouped_lines: "OrderedDict[str, list[str]]" = OrderedDict()
        grouped_timestamps: dict[str, list[str]] = {}

        with log_path.open("r", encoding="utf-8", errors="ignore") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue

                match = BLOCK_ID_RE.search(line)
                if match is None:
                    continue

                block_id = match.group(1)
                grouped_lines.setdefault(block_id, []).append(line)
                grouped_timestamps.setdefault(block_id, []).append(_extract_hdfs_timestamp(line))

        for block_id, lines in grouped_lines.items():
            tokenized_lines = [tokenize_log_line(line) for line in lines]
            timestamps = grouped_timestamps.get(block_id, [])
            label = label_map.get(block_id, 0)

            yield {
                "sequence": tokenized_lines,
                "raw_lines": lines,
                "priority": "critical" if label == 1 else "normal",
                "window_start_ts": timestamps[0] if timestamps else "",
                "window_end_ts": timestamps[-1] if timestamps else "",
                "source": "hdfs",
                "label": label,
                "block_id": block_id,
            }
