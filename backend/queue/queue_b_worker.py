"""Consume critical sequences and hand them to triage."""

from __future__ import annotations

import argparse
import json
import logging
from typing import Any

from detection.neurallog.inference import NeuralLogInference

from .redis_manager import get_redis_client, setup_consumer_groups
from triage.agent import TriageAgent


QUEUE_B_STREAM = "stream:queue_b"
QUEUE_B_ESCALATED_STREAM = "stream:queue_b_escalated"
QUEUE_B_GROUP = "group:queue_b"
QUEUE_B_CONSUMER = "queue_b_worker"


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


def _normalize_message(fields: dict[str, str], detection_source: str, anomaly_score: float) -> dict[str, Any]:
    return {
        "sequence": _load_json(fields.get("sequence", "[]"), []),
        "raw_lines": _load_json(fields.get("raw_lines", "[]"), []),
        "anomaly_score": anomaly_score,
        "priority": fields.get("priority", "critical"),
        "window_start_ts": fields.get("window_start_ts", ""),
        "window_end_ts": fields.get("window_end_ts", ""),
        "source": fields.get("source", "synthetic"),
        "detection_source": detection_source,
    }


def main() -> None:
    _configure_logging()
    logger = logging.getLogger("queue_b")

    parser = argparse.ArgumentParser(description="Triage critical and escalated sequences.")
    parser.add_argument("--model-path", default="data/models/neurallog.pt")
    args = parser.parse_args()

    setup_consumer_groups()
    redis_client = get_redis_client()
    inference = NeuralLogInference(args.model_path)
    triage_agent = TriageAgent()

    while True:
        responses = redis_client.xreadgroup(
            groupname=QUEUE_B_GROUP,
            consumername=QUEUE_B_CONSUMER,
            streams={QUEUE_B_STREAM: ">", QUEUE_B_ESCALATED_STREAM: ">"},
            count=5,
            block=2000,
        )

        if not responses:
            continue

        for stream_name, messages in responses:
            for message_id, fields in messages:
                try:
                    sequence = _load_json(fields.get("sequence", "[]"), [])
                    raw_lines = _load_json(fields.get("raw_lines", "[]"), [])
                    if stream_name == QUEUE_B_STREAM:
                        prediction = inference.predict(sequence)
                        anomaly_score = prediction["score"]
                        detection_source = "prefilter"
                    else:
                        anomaly_score = float(fields.get("anomaly_score", 0.0))
                        detection_source = "neurallog_queue_a"

                    message = _normalize_message(fields, detection_source, anomaly_score)
                    message["sequence"] = sequence
                    message["raw_lines"] = raw_lines

                    triage_agent.run(message)
                    logger.info(
                        "[queue_b] TRIAGE TRIGGERED | source=%s | score=%.3f",
                        detection_source,
                        anomaly_score,
                    )
                except Exception:
                    logger.exception("Failed to process queue_b message %s", message_id)
                finally:
                    redis_client.xack(stream_name, QUEUE_B_GROUP, message_id)


if __name__ == "__main__":
    main()
