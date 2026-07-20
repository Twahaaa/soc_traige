"""Shared config + connection-client factories for the dashboard API.

Reads ``config/settings.yaml`` (no hardcoded values — see backend_AGENTS.md rule 7)
and exposes factories that lazily create Redis (async) and Qdrant (async) clients.

Importing this module is cheap; clients are only constructed on first use so
unit tests can run without live Redis/Qdrant by monkey-patching the factories.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import redis.asyncio as aioredis
import yaml
from dotenv import load_dotenv
from qdrant_client import AsyncQdrantClient


def _config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "settings.yaml"


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    """Load and cache settings.yaml (with .env overlay)."""
    load_dotenv()
    with _config_path().open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def get_async_redis() -> aioredis.Redis:
    """Build an async Redis client from settings.yaml."""
    cfg = load_config()["redis"]
    return aioredis.Redis(
        host=cfg["host"],
        port=cfg["port"],
        decode_responses=True,
    )


def get_async_qdrant() -> AsyncQdrantClient:
    """Build an async Qdrant client from settings.yaml."""
    cfg = load_config()["qdrant"]
    return AsyncQdrantClient(
        host=cfg["host"],
        port=cfg["port"],
        check_compatibility=False,
    )


def cors_origins() -> list[str]:
    """CORS-allowed origins derived from the dashboard.nextjs_port setting."""
    cfg = load_config()["dashboard"]
    return [f"http://localhost:{cfg['nextjs_port']}"]


def triage_reports_stream() -> str:
    """Name of the Redis stream that carries new triage reports."""
    return "stream:triage_reports"


def dashboard_consumer_group() -> str:
    """Consumer group the dashboard belongs to (pre-declared in redis_manager)."""
    return "group:dashboard"


def triage_reports_collection() -> str:
    return load_config()["qdrant"]["collection"]