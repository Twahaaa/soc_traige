"""Consume queue A sequences, score them, and escalate anomalies."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from detection.neurallog.inference import NeuralLogInference

from .redis_manager import get_redis_client, setup_consumer_groups


QUEUE_A_STREAM = "stream:queue_a"
QUEUE_A_GROUP = "group:queue_a"
QUEUE_A_CONSUMER = "queue_a_worker"
QUEUE_B_ESCALATED_STREAM = "stream:queue_b_escalated"
RESULTS_STREAM = "stream:results_normal"


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )


def _load_json(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return default


def _encode_message(payload: dict[str, Any]) -> dict[str, str]:
    return {
        key: json.dumps(value) if isinstance(value, (list, dict)) else str(value)
        for key, value in payload.items()
    }


def _finalize_payload(fields: dict[str, str], predicted: dict[str, Any]) -> dict[str, Any]:
    sequence = _load_json(fields.get("sequence", "[]"), [])
    raw_lines = _load_json(fields.get("raw_lines", "[]"), [])
    return {
        "sequence": sequence,
        "raw_lines": raw_lines,
        "anomaly_score": predicted["score"],
        "priority": fields.get("priority", "normal"),
        "window_start_ts": fields.get("window_start_ts", ""),
        "window_end_ts": fields.get("window_end_ts", ""),
        "source": fields.get("source", "synthetic"),
    }


def main() -> None:
    _configure_logging()
    logger = logging.getLogger("queue_a")

    parser = argparse.ArgumentParser(description="Score queue A sequences with NeuralLog.")
    parser.add_argument("--model-path", default="data/models/neurallog.pt")
    args = parser.parse_args()

    setup_consumer_groups()
    redis_client = get_redis_client()
    inference = NeuralLogInference(args.model_path)

    while True:
        responses = redis_client.xreadgroup(
            groupname=QUEUE_A_GROUP,
            consumername=QUEUE_A_CONSUMER,
            streams={QUEUE_A_STREAM: ">"},
            count=5,
            block=2000,
        )

        if not responses:
            continue

        for _stream_name, messages in responses:
            for message_id, fields in messages:
                try:
                    sequence = _load_json(fields.get("sequence", "[]"), [])
                    predicted = inference.predict(sequence)
                    payload = _finalize_payload(fields, predicted)
                    raw_lines = payload["raw_lines"]

                    if predicted["label"] == "anomalous":
                        payload["detection_source"] = "neurallog_queue_a"
                        redis_client.xadd(QUEUE_B_ESCALATED_STREAM, _encode_message(payload))
                    else:
                        payload["label"] = predicted["label"]
                        redis_client.xadd(RESULTS_STREAM, _encode_message(payload))

                    first_line = raw_lines[0] if raw_lines else ""
                    logger.info(
                        "[queue_a] %s | score=%.3f | %s",
                        predicted["label"],
                        predicted["score"],
                        first_line[:60],
                    )
                except Exception:
                    logger.exception("Failed to process queue_a message %s", message_id)
                finally:
                    redis_client.xack(QUEUE_A_STREAM, QUEUE_A_GROUP, message_id)


if __name__ == "__main__":
    main()
