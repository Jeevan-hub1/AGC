"""Unit + multi-agent coordination tests."""

import pytest

from geos.agents import SupervisorOrchestrator
from geos.data.events import EVENT_CATALOG


@pytest.fixture(scope="module")
def orch():
    return SupervisorOrchestrator(sim_runs=400)


def test_roster_has_eight_agents(orch):
    assert len(orch.roster()) == 8


def test_every_event_produces_full_response(orch):
    for eid in EVENT_CATALOG:
        r = orch.respond_to_id(eid, sim_runs=300)
        assert len(r["agent_reports"]) == 8
        assert "decision_brief" in r
        assert r["total_elapsed_ms"] > 0
        # every report is explainable
        for rep in r["agent_reports"]:
            assert 0.0 <= rep["confidence"] <= 1.0
            assert rep["headline"]


def test_procurement_plan_is_executable(orch):
    r = orch.respond_to_id("hormuz_partial", sim_runs=300)
    proc = next(a for a in r["agent_reports"]
                if a["agent"] == "procurement_orchestrator")
    plan = proc["findings"]["ranked_plan"]
    assert len(plan) >= 1
    # ranks are contiguous and volumes positive
    assert [p["rank"] for p in plan] == list(range(1, len(plan) + 1))
    assert all(p["volume_mbpd"] > 0 for p in plan)


def test_neri_drops_after_shock(orch):
    r = orch.respond_to_id("global_war_shock", sim_runs=300)
    assert r["neri_after"]["score"] < r["neri_before"]["score"]
    assert r["neri_delta"] < 0


def test_black_swan_coordination(orch):
    r = orch.respond_black_swan(
        ["hormuz_partial", "russia_secondary_sanctions"], sim_runs=300
    )
    assert "black_swan_components" in r
    assert len(r["agent_reports"]) == 8


def test_no_agent_loops_or_duplicates(orch):
    r = orch.respond_to_id("redsea_suspension", sim_runs=300)
    names = [a["agent"] for a in r["agent_reports"]]
    assert len(names) == len(set(names))  # each agent runs exactly once
