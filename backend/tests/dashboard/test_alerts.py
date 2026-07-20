"""REST alert / stats / timeline endpoint tests against the in-memory Qdrant fake."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dashboard.main import app
from dashboard.routes.alerts import get_qdrant_service
from dashboard.services.qdrant_service import QdrantService


@pytest.fixture
def client(seeded_qdrant, fake_bridge):
    # Override the QdrantService dependency to wrap the in-memory fake.
    def _override():
        return QdrantService(seeded_qdrant)
    app.dependency_overrides[get_qdrant_service] = _override
    # Bridge is an app-state attribute installed by lifespan; TestClient runs lifespan.
    # After the lifespan starts, replace it with our fake so WS tests can push.
    with TestClient(app) as tc:
        tc.app.state.bridge = fake_bridge
        yield tc
    app.dependency_overrides.clear()


def test_list_reports_returns_snake_case_fields(client):
    resp = client.get("/api/reports?limit=10")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"items", "total", "limit", "offset"}
    assert body["total"] == 3
    item = body["items"][0]
    for field in (
        "incident_id", "timestamp", "severity", "title", "affected_host",
        "log_source", "anomaly_score", "description", "evidence",
        "cve_references", "ip_reputation", "mitre_attack",
        "remediation_steps", "similar_past_incidents", "detection_source",
    ):
        assert field in item, f"missing snake_case field {field}"
    # ip_reputation snake_case
    assert item["ip_reputation"] is None or "abuse_score" in item["ip_reputation"]
    assert item["ip_reputation"] is None or "total_reports" in item["ip_reputation"]
    # mitre_attack snake_case
    assert item["mitre_attack"] is None or "technique_id" in item["mitre_attack"]


def test_list_reports_severity_filter(client):
    resp = client.get("/api/reports?severity=Critical")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["severity"] == "Critical"


def test_list_reports_severity_filter_no_matches(client):
    resp = client.get("/api/reports?severity=Informational")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_get_report_by_id(client):
    listing = client.get("/api/reports?limit=10").json()
    target_id = listing["items"][0]["incident_id"]
    resp = client.get(f"/api/reports/{target_id}")
    assert resp.status_code == 200
    assert resp.json()["incident_id"] == target_id
    assert resp.json()["mitre_attack"]["technique_id"] == "T1110"


def test_get_report_404(client):
    resp = client.get("/api/reports/does-not-exist")
    assert resp.status_code == 404


def test_stats_aggregation(client):
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["total_alerts_all"] == 3
    assert stats["severity_distribution"]["Critical"] == 1
    assert stats["severity_distribution"]["High"] == 1
    assert stats["severity_distribution"]["Medium"] == 1
    # two of three seeded reports carry a mitre_attack
    assert len(stats["top_mitre"]) == 1
    assert stats["top_mitre"][0]["technique_id"] == "T1110"
    assert stats["top_mitre"][0]["count"] == 2
    assert len(stats["top_hosts"]) == 3
    # highest severity per host
    hosts = {h["host"]: h for h in stats["top_hosts"]}
    assert hosts["mail-svr-01"]["highest_severity"] == "Critical"


def test_hosts_endpoint(client):
    resp = client.get("/api/hosts?limit=10")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 3
    for h in body:
        assert {"host", "count", "highest_severity", "last_seen"} <= set(h.keys())


def test_timeline_endpoint(client):
    resp = client.get("/api/timeline?limit=10")
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) == 3
    assert {"incident_id", "timestamp", "severity", "title", "host", "anomaly_score"} <= set(events[0].keys())
    # sorted newest first
    assert events[0]["timestamp"] >= events[1]["timestamp"]


def test_qdrant_failure_returns_empty(client, fake_qdrant):
    # Wipe all points then ask for a list — service must degrade to [] not 500.
    fake_qdrant._points = []
    resp = client.get("/api/reports")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0