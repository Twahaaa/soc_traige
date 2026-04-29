"""Redis connection helpers and consumer group setup."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

import redis
import yaml
from dotenv import load_dotenv
from redis.exceptions import ResponseError


def _load_config() -> Dict[str, Any]:
    """Load settings from config/settings.yaml and environment variables."""
    load_dotenv()
    config_path = Path(__file__).resolve().parents[1] / "config" / "settings.yaml"
    with config_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def get_redis_client() -> redis.Redis:
    """Return a connected Redis client using settings.yaml."""
    config = _load_config()
    redis_config = config["redis"]
    return redis.Redis(
        host=redis_config["host"],
        port=redis_config["port"],
        decode_responses=True,
    )


def setup_consumer_groups() -> None:
    """Create all required Redis Streams consumer groups if missing."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    logger = logging.getLogger("redis_manager")
    client = get_redis_client()

    stream_groups = {
        "stream:raw_logs": "group:preprocessing",
        "stream:queue_a": "group:queue_a",
        "stream:queue_b": "group:queue_b",
        "stream:queue_b_escalated": "group:queue_b",
        "stream:results_normal": "group:dashboard",
        "stream:triage_reports": "group:dashboard",
    }

    for stream, group in stream_groups.items():
        try:
            client.xgroup_create(stream, group, id="$", mkstream=True)
            logger.info("Created consumer group %s for %s", group, stream)
        except ResponseError as exc:
            if "BUSYGROUP" in str(exc):
                logger.info("Consumer group %s already exists for %s", group, stream)
            else:
                raise
