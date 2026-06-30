"""Unit tests for the National Energy Resilience Index."""

import pytest

from geos import config
from geos.causal import CausalEngine
from geos.data.events import get_event
from geos.neri import NERICalculator


@pytest.fixture
def calc():
    return NERICalculator()


def test_weights_sum_to_one():
    assert sum(config.NERI_WEIGHTS.values()) == pytest.approx(1.0, abs=1e-6)


def test_baseline_in_stable_band(calc):
    s = calc.compute()
    assert 0 <= s.score <= 100
    assert s.band in {"STABLE", "WATCH", "RESILIENT"}


def test_score_drops_under_shock(calc):
    base = calc.compute()
    ev = get_event("hormuz_partial")
    cr = CausalEngine().evaluate(ev)
    shocked = calc.compute(causal=cr, hormuz_block=ev.hormuz_closure_prob)
    assert shocked.score < base.score


def test_war_is_critical(calc):
    ev = get_event("global_war_shock")
    cr = CausalEngine().evaluate(ev)
    s = calc.compute(causal=cr, hormuz_block=ev.hormuz_closure_prob)
    assert s.band == "CRITICAL"
    assert s.score < config.NERI_CRITICAL + 5


def test_components_bounded(calc):
    s = calc.compute()
    for v in s.components.values():
        assert 0 <= v <= 100


def test_drivers_reported(calc):
    s = calc.compute()
    assert len(s.drivers) == 3
