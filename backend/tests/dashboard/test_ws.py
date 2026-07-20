"""WebSocket endpoint test: snapshot + live streamed report via fake bridge."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from dashboard.main import app
from dashboard.routes.alerts import get_qdrant_service
from dashboard.services.qdrant_service import QdrantService


@pytest.fixture
def ws_client(seeded_qdrant, fake_bridge):
    def _override():
        return QdrantService(seeded_qdrant)
    app.dependency_overrides[get_qdrant_service] = _override
    # WS handler calls get_async_qdrant() directly — patch it to return the fake.
    with patch("dashboard.routes.ws.get_async_qdrant", return_value=seeded_qdrant):
        with TestClient(app) as tc:
            tc.app.state.bridge = fake_bridge
            yield tc
    app.dependency_overrides.clear()


def test_ws_snapshot_on_connect(ws_client, seeded_qdrant):
    with ws_client.websocket_connect("/ws/reports") as sock:
        msg = sock.receive_json()
    assert msg["type"] == "snapshot"
    assert isinstance(msg["items"], list)
    assert len(msg["items"]) == 3
    assert "incident_id" in msg["items"][0]
    assert msg["items"][0]["mitre_attack"]["technique_id"] == "T1110"


def test_ws_streams_pushed_report(ws_client, fake_bridge, seeded_qdrant):
    from tests.dashboard.conftest import make_report_payload
    payload = make_report_payload(severity="High", title="Live WS report")

    with ws_client.websocket_connect("/ws/reports") as sock:
        # discard the snapshot
        snapshot = sock.receive_json()
        assert snapshot["type"] == "snapshot"
        # push a live report from the test thread onto the WS event loop
        ws_client.portal.call(fake_bridge.push, payload)
        msg = sock.receive_json()
    assert msg["type"] == "report"
    assert msg["item"]["title"] == "Live WS report"
    assert msg["item"]["severity"] == "High"
    assert msg["item"]["incident_id"] == payload["incident_id"]
    # snake_case shape preserved on the wire
    assert "abuse_score" in msg["item"]["ip_reputation"]
    assert "technique_id" in msg["item"]["mitre_attack"]