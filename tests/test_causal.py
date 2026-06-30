"""Unit tests for the Causal AI Engine."""

import pytest

from geos import config
from geos.causal import CausalEngine
from geos.data.events import get_event


@pytest.fixture
def engine():
    return CausalEngine()


def test_baseline_no_event_is_calm(engine):
    # an event with zero levers should not move prices much
    from geos.data.events import ShockEvent
    calm = ShockEvent(id="calm", title="calm", category="none")
    r = engine.evaluate(calm)
    assert r.brent_usd == pytest.approx(config.BASELINE_BRENT_USD, abs=1.0)
    assert r.effective_shortfall_pct == pytest.approx(0.0, abs=1e-6)


def test_hormuz_partial_lands_in_realistic_band(engine):
    r = engine.evaluate(get_event("hormuz_partial"))
    # partial closure should push Brent into the ~$115-140 stress band
    assert 110 <= r.brent_usd <= 145
    assert r.inflation_delta_pp > 0
    assert r.gdp_drag_pp < 0  # GDP drag is negative


def test_monotonic_in_hormuz_block(engine):
    ev = get_event("hormuz_partial")
    low = engine.do(ev, hormuz_blocked=0.2)
    high = engine.do(ev, hormuz_blocked=0.9)
    assert high.brent_usd > low.brent_usd
    assert high.effective_shortfall_pct > low.effective_shortfall_pct


def test_do_intervention_changes_outcome(engine):
    ev = get_event("iran_export_drop")
    delta = engine.counterfactual_delta(ev, hormuz_blocked=1.0)
    # clamping a full Hormuz block must raise Brent vs the factual world
    assert delta["brent_usd"] > 0


def test_explanation_present(engine):
    r = engine.evaluate(get_event("global_war_shock"))
    assert set(["shortfall", "brent", "inflation", "gdp"]).issubset(r.explanation)
