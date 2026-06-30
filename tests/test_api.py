"""Integration / end-to-end API tests."""

import pytest
from fastapi.testclient import TestClient

from geos.api.server import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["agents"] == 8


def test_events_and_agents(client):
    assert len(client.get("/api/events").json()["events"]) == 6
    assert len(client.get("/api/agents").json()["roster"]) == 8


def test_worldmodel(client):
    wm = client.get("/api/worldmodel").json()
    assert len(wm["suppliers"]) == 8
    assert "graph_stats" in wm


def test_scenario_e2e_hormuz(client):
    r = client.post("/api/scenario",
                    json={"event_id": "hormuz_partial", "sim_runs": 400})
    assert r.status_code == 200
    d = r.json()
    assert d["neri_after"]["score"] < d["neri_before"]["score"]
    assert d["causal"]["brent_usd"] > 110
    assert len(d["agent_reports"]) == 8


def test_scenario_unknown_event_404(client):
    r = client.post("/api/scenario", json={"event_id": "nope"})
    assert r.status_code == 404


def test_blackswan_e2e(client):
    r = client.post("/api/blackswan", json={
        "event_ids": ["hormuz_partial", "redsea_suspension"], "sim_runs": 400})
    assert r.status_code == 200
    assert "black_swan_components" in r.json()


def test_copilot_scenario_intent(client):
    r = client.post("/api/copilot",
                    json={"question": "What happens if Hormuz closes tomorrow?"})
    assert r.status_code == 200
    assert r.json()["intent"] == "scenario_impact"


def test_copilot_reserve_intent(client):
    r = client.post("/api/copilot",
                    json={"question": "How long can India sustain imports?"})
    assert r.json()["intent"] == "reserve_cover"


def test_frontend_served(client):
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200
