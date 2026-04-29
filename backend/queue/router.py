"""Helpers for routing sliding windows to the correct Redis stream."""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence


QUEUE_A_STREAM = "stream:queue_a"
QUEUE_B_STREAM = "stream:queue_b"


def choose_stream(window: Sequence[Mapping[str, Any]]) -> str:
    """Select the critical fast-path when any item in the window is critical."""
    for entry in window:
        if str(entry.get("priority", "normal")).lower() == "critical":
            return QUEUE_B_STREAM
    return QUEUE_A_STREAM


def build_sequence_payload(window: Sequence[Mapping[str, Any]], source: str) -> dict[str, Any]:
    """Build the shared sequence payload used by the preprocessing streams."""
    if not window:
        raise ValueError("window must not be empty")

    priority = "critical" if choose_stream(window) == QUEUE_B_STREAM else "normal"
    return {
        "sequence": [list(entry["tokens"]) for entry in window],
        "raw_lines": [str(entry["raw_line"]) for entry in window],
        "priority": priority,
        "window_start_ts": str(window[0]["timestamp"]),
        "window_end_ts": str(window[-1]["timestamp"]),
        "source": source,
    }


def encode_stream_payload(payload: Mapping[str, Any]) -> dict[str, str]:
    """Serialize nested sequence fields for Redis Streams."""
    return {
        "sequence": json.dumps(payload["sequence"]),
        "raw_lines": json.dumps(payload["raw_lines"]),
        "priority": str(payload["priority"]),
        "window_start_ts": str(payload["window_start_ts"]),
        "window_end_ts": str(payload["window_end_ts"]),
        "source": str(payload["source"]),
    }
