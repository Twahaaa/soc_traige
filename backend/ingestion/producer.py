"""Log producer that publishes raw logs to Redis Streams."""

from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from ingestion.prefilter import PreFilter
from ingestion.synthetic_logs import generate_logs
from queue.redis_manager import get_redis_client


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )


def _load_config() -> dict:
    import yaml

    config_path = Path(__file__).resolve().parents[1] / "config" / "settings.yaml"
    with config_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _read_log_file(path: Path) -> Iterable[str]:
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            cleaned = line.strip()
            if cleaned:
                yield cleaned


def main() -> None:
    _configure_logging()
    logger = logging.getLogger("producer")

    parser = argparse.ArgumentParser(description="Publish logs to Redis Streams.")
    parser.add_argument("--mode", choices=["normal", "attack"], default="normal")
    parser.add_argument("--rate", type=float, default=10.0)
    parser.add_argument("--count", type=int, default=None)
    parser.add_argument("--file", type=str, default=None)
    parser.add_argument("--dataset_dir", type=str, default=None)
    args = parser.parse_args()

    config = _load_config()
    prefilter = PreFilter(config)
    redis_client = get_redis_client()

    if args.file:
        source = Path(args.file).name
        log_iter = _read_log_file(Path(args.file))
    elif args.dataset_dir:
        dataset_dir = Path(args.dataset_dir)
        source = dataset_dir.name
        dataset_files = []
        for candidate in (dataset_dir / "HDFS.log", dataset_dir / "BGL.log", dataset_dir / "preprocessed" / "HDFS.log", dataset_dir / "preprocessed" / "BGL.log"):
            if candidate.exists():
                dataset_files.append(candidate)

        if not dataset_files:
            raise FileNotFoundError(f"No dataset log file found under {dataset_dir}")

        log_iter = (line for file_path in dataset_files for line in _read_log_file(file_path))
    else:
        source = "synthetic"
        log_iter = (entry["log_line"] for entry in generate_logs(args.mode, args.rate, args.count))

    published = 0
    for log_line in log_iter:
        result = prefilter.check(log_line, time.time())
        message = {
            "log_line": log_line,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "priority": result["priority"],
            "source": source,
            "prefilter_reason": result["reason"],
        }

        redis_client.xadd(
            "stream:raw_logs",
            {
                key: "null" if value is None else str(value)
                for key, value in message.items()
            },
        )

        published += 1
        if published % 100 == 0:
            logger.info(
                "%s published | last: %s | %s",
                published,
                message["priority"],
                message["log_line"][:60],
            )


if __name__ == "__main__":
    main()
