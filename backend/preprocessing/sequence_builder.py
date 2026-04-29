"""Consume raw logs, build sliding windows, and route them to Redis streams."""

from __future__ import annotations

import argparse
import logging
import re
from collections import deque
from pathlib import Path
from typing import Any, Deque, Mapping

import yaml

from queue.redis_manager import get_redis_client, setup_consumer_groups
from queue.router import build_sequence_payload, choose_stream, encode_stream_payload


RAW_LOG_STREAM = "stream:raw_logs"
PREPROCESSING_GROUP = "group:preprocessing"
PREPROCESSING_CONSUMER = "sequence_builder"


def _load_config() -> dict[str, Any]:
    """Load the shared backend settings file."""
    config_path = Path(__file__).resolve().parents[1] / "config" / "settings.yaml"
    with config_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def tokenize_log_line(log_line: str) -> list[str]:
    """Tokenize a log line for NeuralLog without parsing it."""
    tokens: list[str] = []
    for raw_token in re.split(r"[\s:,]+", log_line):
        cleaned = re.sub(r"[^A-Za-z]+", "", raw_token).lower()
        if cleaned:
            tokens.append(cleaned)
    return tokens


class SequenceBuilder:
    """Maintain a sliding window of raw logs and publish fixed-length sequences."""

    tokenize = staticmethod(tokenize_log_line)

    def __init__(self, window_size: int, redis_client: Any | None = None) -> None:
        if window_size <= 0:
            raise ValueError("window_size must be greater than zero")

        self.window_size = window_size
        self.redis_client = redis_client or get_redis_client()
        self.window: Deque[dict[str, Any]] = deque(maxlen=window_size)

    def ingest(self, fields: Mapping[str, str]) -> tuple[str, dict[str, Any]] | None:
        """Append one raw message and emit a routed sequence once the window is full."""
        log_line = str(fields.get("log_line", ""))
        priority = str(fields.get("priority", "normal")).lower()
        timestamp = str(fields.get("timestamp", ""))
        source = str(fields.get("source", "synthetic"))

        self.window.append(
            {
                "tokens": self.tokenize(log_line),
                "raw_line": log_line,
                "priority": "critical" if priority == "critical" else "normal",
                "timestamp": timestamp,
            }
        )

        if len(self.window) < self.window_size:
            return None

        window_entries = list(self.window)
        stream_name = choose_stream(window_entries)
        payload = build_sequence_payload(window_entries, source=source)
        return stream_name, payload

    def publish(self, stream_name: str, payload: Mapping[str, Any]) -> None:
        """Publish a sequence payload to the routed Redis stream."""
        self.redis_client.xadd(stream_name, encode_stream_payload(payload))


def main() -> None:
    """Consume raw logs from Redis and push sliding windows into the routing streams."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    logger = logging.getLogger("preprocessor")

    config = _load_config()
    window_size = int(config["neurallog"]["window_size"])
    redis_client = get_redis_client()
    setup_consumer_groups()
    builder = SequenceBuilder(window_size=window_size, redis_client=redis_client)

    while True:
        responses = redis_client.xreadgroup(
            groupname=PREPROCESSING_GROUP,
            consumername=PREPROCESSING_CONSUMER,
            streams={RAW_LOG_STREAM: ">"},
            count=10,
            block=1000,
        )

        if not responses:
            continue

        for _stream_name, messages in responses:
            for message_id, fields in messages:
                try:
                    result = builder.ingest(fields)
                    if result is None:
                        continue

                    stream_name, payload = result
                    builder.publish(stream_name, payload)
                    logger.info(
                        "[preprocessor] window=%d | priority=%s -> %s",
                        builder.window_size,
                        payload["priority"],
                        stream_name.removeprefix("stream:"),
                    )
                except Exception:
                    logger.exception("Failed to process raw stream message %s", message_id)
                finally:
                    redis_client.xack(RAW_LOG_STREAM, PREPROCESSING_GROUP, message_id)


if __name__ == "__main__":
    main()
