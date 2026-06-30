"""Tests for the advanced ML / optimization layer."""

import pytest

from geos.data import seed_data as sd
from geos.data.events import get_event
from geos.ml import GNNCascade, get_risk_model
from geos.knowledge_graph import build_world_graph
from geos.optim import ProcurementGame, ReserveDP


# ---------------- Foundation Model ---------------- #
def test_risk_model_trains_and_scores():
    m = get_risk_model()
    assert m.auc_ > 0.6  # learns a useful signal from the synthetic corpus
    imp = m.feature_importance()
    assert abs(sum(imp.values()) - 1.0) < 1e-2  # rounded to 4dp, allow slack
    # tension should be a top driver
    assert imp["tension"] == max(imp.values())


def test_forecast_flags_hormuz_under_shock():
    m = get_risk_model()
    preds = m.predict_corridors(get_event("hormuz_partial"))
    top = preds[0]
    assert top.corridor_id == "cor_hormuz"
    assert top.disruption_probability > 0.7
    assert 0 < top.lead_time_days < 45


def test_higher_tension_raises_probability():
    m = get_risk_model()
    base = {"tension": 0.1, "tension_momentum": 0, "sanctions_pressure": 0,
            "price_momentum": 0, "naval_presence": 0.1, "incident_rate": 0.1,
            "season": 0.5, "base_risk": 0.1}
    hot = dict(base, tension=0.9, naval_presence=0.9, incident_rate=0.9)
    assert m.predict(hot).disruption_probability > m.predict(base).disruption_probability


# ---------------- GNN ---------------- #
def test_gnn_propagates_risk():
    gnn = GNNCascade(build_world_graph())
    res = gnn.cascade(disrupted_corridors=["cor_hormuz"])
    assert res["mean_network_risk"] > 0
    assert len(res["systemic_risk_ranking"]) > 0
    for r in res["refinery_risk"].values():
        assert 0 <= r <= 100


def test_gnn_no_disruption_is_zero():
    gnn = GNNCascade(build_world_graph())
    res = gnn.cascade()
    assert res["mean_network_risk"] == 0.0


# ---------------- Game theory ---------------- #
def test_nash_equilibrium_converges():
    disrupted = [s.id for s in sd.SUPPLIERS if s.via_hormuz]
    eq = ProcurementGame().solve(disrupted_ids=disrupted, shortfall_mbpd=1.6)
    assert eq.converged
    assert eq.clearing_price_usd > 82  # scarcity lifts price above baseline
    assert eq.total_extra_supply_mbpd > 0
    assert all(a["extra_supply_mbpd"] > 0 for a in eq.allocations)


def test_bigger_shortfall_raises_clearing_price():
    small = ProcurementGame().solve(["sup_iq"], shortfall_mbpd=0.3)
    big = ProcurementGame().solve(["sup_iq"], shortfall_mbpd=2.0)
    assert big.clearing_price_usd >= small.clearing_price_usd


# ---------------- DP reserve ---------------- #
def test_dp_reserve_policy_valid():
    total = sum(r.capacity_mmbbl * r.fill_pct for r in sd.RESERVES)
    pol = ReserveDP(total_reserve_mmbbl=total, horizon_days=30).solve(daily_gap_mmbbl=0.8)
    assert len(pol.optimal_release_schedule) == 30
    assert all(r >= 0 for r in pol.optimal_release_schedule)
    assert 0 <= pol.final_reserve_mmbbl <= total
    assert pol.total_unmet_gap_mmbbl >= 0


def test_dp_front_loads_releases():
    total = sum(r.capacity_mmbbl * r.fill_pct for r in sd.RESERVES)
    pol = ReserveDP(total_reserve_mmbbl=total, horizon_days=30).solve(daily_gap_mmbbl=1.0)
    sched = pol.optimal_release_schedule
    # early-horizon releases should not be smaller than late-horizon (gap decays)
    assert sum(sched[:10]) >= sum(sched[-10:])
