"""Tests for the live feed (fallback path) and the detection benchmark."""

import pytest

from geos import config
from geos.analytics import DetectionBenchmark
from geos.data import live_feed


# ---------------- Live feed ---------------- #
def test_fallback_snapshot_uses_baseline():
    snap = live_feed._fallback()
    assert snap.source == "fallback"
    assert snap.prices["brent"] == config.BASELINE_BRENT_USD
    d = snap.to_dict()
    assert d["brent"] == config.BASELINE_BRENT_USD
    assert "as_of_iso" in d


def test_feed_returns_valid_snapshot(monkeypatch):
    # force the network path to fail -> must degrade gracefully (cache/fallback)
    monkeypatch.setattr(live_feed, "_fetch_symbol",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no net")))
    feed = live_feed.LiveFeed()
    snap = feed.get(force=True)
    assert snap.source in {"cache", "fallback"}
    assert snap.prices.get("brent", 0) > 0


def test_live_brent_is_positive():
    feed = live_feed.LiveFeed()
    assert feed.live_brent() > 0


# ---------------- Benchmark ---------------- #
@pytest.fixture(scope="module")
def result():
    return DetectionBenchmark().run(episodes=400)


def test_phoenix_beats_baseline_on_fnr(result):
    assert result.phoenix.fnr < result.baseline.fnr
    assert result.fnr_reduction_rel > 0.4   # at least a 40% relative cut


def test_phoenix_detects_earlier(result):
    assert result.phoenix.mean_lead_days > result.baseline.mean_lead_days
    assert result.lead_time_gain_days > 0


def test_confusion_counts_consistent(result):
    for m in (result.phoenix, result.baseline):
        total = m.tp + m.fp + m.tn + m.fn
        assert total == result.episodes
        assert 0 <= m.recall <= 1
        assert 0 <= m.precision <= 1
        assert 0 <= m.fnr <= 1


def test_phoenix_recall_high(result):
    assert result.phoenix.recall > 0.85


def test_series_example_present(result):
    ex = result.series_example
    assert "price_z" in ex and "fusion" in ex
    assert len(ex["price_z"]) == result.horizon_days
