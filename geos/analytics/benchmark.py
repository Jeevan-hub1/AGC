"""Detection benchmark: PHOENIX compound detection vs single-sensor baseline.

This module quantifies the headline evaluation metric for the challenge:
**reduction in false-negative rate** and **detection lead time** versus a
single-sensor baseline.

Setup
-----
We generate a labelled corpus of disruption "episodes". Each episode is a short
multi-signal time series leading up to a possible onset at t=0:

    signals per day: price_z (Brent z-score), tension, naval_presence,
                     incident_rate, sanctions_pressure

* A **single-sensor baseline** only watches one signal (Brent price) and fires
  when it crosses a threshold. It therefore (a) fires late - price moves only
  once physical disruption hits - and (b) misses "silent" disruptions where
  supply is cut without an immediate price spike (false negatives).

* **PHOENIX** fires on a *compound* condition: a weighted fusion of all signals
  crossing a threshold. Because precursors (tension, naval build-up, incidents)
  rise *before* price, PHOENIX detects earlier and catches the silent cases -
  exactly the "data present but unacted upon" failure the challenge targets.

Outputs confusion matrices, precision/recall, false-negative rate for both
detectors, the FNR reduction, and mean detection lead time (days before onset).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np

from geos import config

SIGNALS = ["price_z", "tension", "naval_presence", "incident_rate", "sanctions"]
# PHOENIX fusion weights (precursor signals matter as much as price)
FUSION_WEIGHTS = np.array([0.30, 0.25, 0.20, 0.15, 0.10])


@dataclass
class DetectorMetrics:
    name: str
    tp: int
    fp: int
    tn: int
    fn: int
    mean_lead_days: float

    @property
    def recall(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d else 0.0

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else 0.0

    @property
    def fnr(self) -> float:                       # false-negative rate
        d = self.tp + self.fn
        return self.fn / d if d else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "confusion": {"tp": self.tp, "fp": self.fp, "tn": self.tn, "fn": self.fn},
            "recall": round(self.recall, 3),
            "precision": round(self.precision, 3),
            "fnr": round(self.fnr, 3),
            "f1": round(self.f1, 3),
            "mean_lead_days": round(self.mean_lead_days, 2),
        }


@dataclass
class BenchmarkResult:
    episodes: int
    horizon_days: int
    phoenix: DetectorMetrics
    baseline: DetectorMetrics
    fnr_reduction_abs: float
    fnr_reduction_rel: float
    lead_time_gain_days: float
    summary: str = ""
    series_example: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "episodes": self.episodes,
            "horizon_days": self.horizon_days,
            "phoenix": self.phoenix.to_dict(),
            "baseline": self.baseline.to_dict(),
            "fnr_reduction_abs": round(self.fnr_reduction_abs, 3),
            "fnr_reduction_rel_pct": round(self.fnr_reduction_rel * 100, 1),
            "lead_time_gain_days": round(self.lead_time_gain_days, 2),
            "summary": self.summary,
            "series_example": self.series_example,
        }


class DetectionBenchmark:
    """Generates labelled episodes and scores both detectors."""

    def __init__(self, horizon_days: int = 14,
                 price_threshold: float = 2.0,     # baseline fires at +2 sigma
                 fusion_threshold: float = 0.34,
                 seed: int = config.RANDOM_SEED) -> None:
        self.H = horizon_days
        self.price_thr = price_threshold
        self.fusion_thr = fusion_threshold
        self.rng = np.random.default_rng(seed)

    def _episode(self, disrupted: bool) -> Tuple[np.ndarray, bool, str]:
        """Return (H x len(SIGNALS)) signal matrix, label, type tag."""
        H = self.H
        sig = np.zeros((H, len(SIGNALS)))
        kind = "benign"

        if disrupted:
            # precursors ramp from an onset-lead day; ~40% are "silent" (price
            # barely moves but supply is cut) -> baseline tends to miss these
            silent = self.rng.random() < 0.4
            # ~15% are "stealth": even precursors are faint (genuinely hard)
            stealth = 0.55 if self.rng.random() < 0.15 else 1.0
            lead = self.rng.integers(7, H + 1)    # precursors begin earlier
            for t in range(H):
                prog = max(0.0, (t - (H - lead)) / max(1, lead))  # 0..1 ramp
                sig[t, 1] = np.clip(stealth * (0.25 + 0.75 * prog) + self.rng.normal(0, 0.07), 0, 1)
                sig[t, 2] = np.clip(stealth * (0.18 + 0.72 * prog) + self.rng.normal(0, 0.07), 0, 1)
                sig[t, 3] = np.clip(stealth * (0.15 + 0.65 * prog) + self.rng.normal(0, 0.09), 0, 1)
                sig[t, 4] = np.clip(stealth * (0.12 + 0.55 * prog) + self.rng.normal(0, 0.09), 0, 1)
                # price only really moves late in the ramp (physical onset)
                price_amp = (0.6 if silent else 3.4)
                sig[t, 0] = price_amp * (prog ** 2) + self.rng.normal(0, 0.4)             # price z
            kind = "silent" if silent else "overt"
        else:
            # benign-but-noisy: random fluctuations, occasional price blip
            for t in range(H):
                sig[t, 0] = self.rng.normal(0, 0.7)
                sig[t, 1:] = np.clip(self.rng.normal(0.12, 0.1, 4), 0, 1)
        return sig, disrupted, kind

    def _baseline_fire(self, sig: np.ndarray) -> int:
        """First day price crosses threshold; -1 if never."""
        for t in range(self.H):
            if sig[t, 0] >= self.price_thr:
                return t
        return -1

    def _phoenix_fire(self, sig: np.ndarray) -> int:
        """First day the fused compound score crosses threshold; -1 if never."""
        # normalise price z into 0..1 for fusion
        for t in range(self.H):
            price_n = np.clip(sig[t, 0] / 4.0, 0, 1)
            feats = np.array([price_n, sig[t, 1], sig[t, 2], sig[t, 3], sig[t, 4]])
            if float(FUSION_WEIGHTS @ feats) >= self.fusion_thr:
                return t
        return -1

    def run(self, episodes: int = 400) -> BenchmarkResult:
        H = self.H
        bp = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
        pp = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
        b_leads, p_leads = [], []
        example = None

        for i in range(episodes):
            disrupted = self.rng.random() < 0.5
            sig, label, kind = self._episode(disrupted)
            b_fire = self._baseline_fire(sig)
            p_fire = self._phoenix_fire(sig)

            # classification (did it fire at all within the window?)
            b_hit, p_hit = b_fire >= 0, p_fire >= 0
            for store, hit in ((bp, b_hit), (pp, p_hit)):
                if label and hit:
                    store["tp"] += 1
                elif label and not hit:
                    store["fn"] += 1
                elif not label and hit:
                    store["fp"] += 1
                else:
                    store["tn"] += 1

            # lead time = days before onset (t=H-1 is onset) that it first fired
            if label and b_hit:
                b_leads.append((H - 1) - b_fire)
            if label and p_hit:
                p_leads.append((H - 1) - p_fire)

            if example is None and label and kind != "benign":
                example = {
                    "kind": kind,
                    "days": list(range(H)),
                    "price_z": [round(float(x), 2) for x in sig[:, 0]],
                    "fusion": [round(float(FUSION_WEIGHTS @ np.array(
                        [np.clip(sig[t, 0] / 4, 0, 1), sig[t, 1], sig[t, 2],
                         sig[t, 3], sig[t, 4]])), 3) for t in range(H)],
                    "baseline_fire_day": int(b_fire),
                    "phoenix_fire_day": int(p_fire),
                }

        baseline = DetectorMetrics("Single-Sensor Baseline", bp["tp"], bp["fp"],
                                   bp["tn"], bp["fn"],
                                   float(np.mean(b_leads)) if b_leads else 0.0)
        phoenix = DetectorMetrics("PHOENIX Compound Detection", pp["tp"], pp["fp"],
                                  pp["tn"], pp["fn"],
                                  float(np.mean(p_leads)) if p_leads else 0.0)

        fnr_abs = baseline.fnr - phoenix.fnr
        fnr_rel = (fnr_abs / baseline.fnr) if baseline.fnr else 0.0
        lead_gain = phoenix.mean_lead_days - baseline.mean_lead_days

        summary = (
            f"PHOENIX cuts the false-negative rate from {baseline.fnr:.0%} to "
            f"{phoenix.fnr:.0%} ({fnr_rel:.0%} relative reduction) and detects "
            f"{lead_gain:.1f} days earlier on average than a single-sensor "
            f"baseline across {episodes} episodes."
        )

        return BenchmarkResult(
            episodes=episodes, horizon_days=H, phoenix=phoenix, baseline=baseline,
            fnr_reduction_abs=fnr_abs, fnr_reduction_rel=fnr_rel,
            lead_time_gain_days=lead_gain, summary=summary,
            series_example=example or {},
        )
