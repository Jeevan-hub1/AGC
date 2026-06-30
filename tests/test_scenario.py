"""Unit tests for the Monte Carlo war-gaming simulator."""

import pytest

from geos.scenario import WarGameSimulator


@pytest.fixture
def sim():
    return WarGameSimulator(seed=42)


def test_distribution_shape(sim):
    d = sim.run_event_id("hormuz_partial", runs=500)
    assert d.runs == 500
    for metric in ["brent_usd", "inflation_delta_pp", "gdp_drag_pp"]:
        m = d.metrics[metric]
        assert m["p5"] <= m["p50"] <= m["p95"]
    assert len(d.histograms["brent_usd"]["counts"]) == 20


def test_probabilities_are_valid(sim):
    d = sim.run_event_id("hormuz_partial", runs=500)
    assert 0.0 <= d.prob_brent_above_120 <= 1.0
    assert 0.0 <= d.prob_recession_signal <= 1.0
    assert d.worst_case_brent >= d.metrics["brent_usd"]["p95"]


def test_black_swan_is_worse_than_components(sim):
    single = sim.run_event_id("hormuz_partial", runs=800).metrics["brent_usd"]["p50"]
    swan = sim.black_swan(
        ["hormuz_partial", "russia_secondary_sanctions"], runs=800
    ).metrics["brent_usd"]["p50"]
    assert swan >= single


def test_reproducible_with_seed():
    a = WarGameSimulator(seed=7).run_event_id("opec_emergency_cut", runs=300)
    b = WarGameSimulator(seed=7).run_event_id("opec_emergency_cut", runs=300)
    assert a.metrics["brent_usd"]["mean"] == b.metrics["brent_usd"]["mean"]
