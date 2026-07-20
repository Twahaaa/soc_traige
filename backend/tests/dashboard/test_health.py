"""Health endpoint test — overrides config_loader so no real Redis/Qdrant is hit."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from dashboard.main import app


class _MockRedis:
    def __init__(self, ok: bool = True):
        self.ok = ok

    async def ping(self):
        return self.ok

    async def aclose(self):
        return None


class _MockQdrant:
    async def get_collection(self, *, collection_name):
        class _Info:
            points_count = 7
        return _Info()

    async def close(self):
        return None


@pytest.fixture
def health_client(fake_bridge):
    with TestClient(app) as tc:
        tc.app.state.bridge = fake_bridge
        with patch("dashboard.routes.health.get_async_redis", return_value=_MockRedis(True)), \
             patch("dashboard.routes.health.get_async_qdrant", return_value=_MockQdrant()), \
             patch("dashboard.routes.health.load_config") as mock_cfg:
            mock_cfg.return_value = {
                "qdrant": {"collection": "triage_reports"},
                "llm": {"providers": {"ollama": {"model": "gemma3:1b", "base_url": "http://localhost:11434"}}},
            }
            yield tc


def test_health_returns_component_statuses(health_client):
    resp = health_client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "components" in body
    names = {c["name"] for c in body["components"]}
    assert {"Redis Streams", "Qdrant", "Ollama LLM"} <= names
    statuses = {c["status"] for c in body["components"]}
    assert statuses <= {"ok", "warn", "error"}
    redis = next(c for c in body["components"] if c["name"] == "Redis Streams")
    assert redis["status"] == "ok"
    qdrant = next(c for c in body["components"] if c["name"] == "Qdrant")
    assert qdrant["status"] == "ok"
    assert "7 points" in qdrant["detail"]