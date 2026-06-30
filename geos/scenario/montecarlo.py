"""Energy War-Gaming Simulator.

Samples thousands of plausible futures around a shock event by perturbing the
causal levers with calibrated uncertainty, then runs each draw through the
Causal Engine. The result is a *probability distribution* over Brent price,
inflation, GDP drag and supply shortfall - not a single point forecast.

Also supports "Black Swan" compounding: combine multiple events into a single
unprecedented crisis and simulate its joint distribution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from geos import config
from geos.causal.scm import CausalEngine
from geos.data.events import ShockEvent, get_event


@dataclass
class ScenarioDistribution:
    runs: int
    metrics: Dict[str, Dict[str, float]]   # metric -> {mean, p5, p50, p95, std}
    histograms: Dict[str, Dict[str, list]]  # metric -> {bins, counts}
    worst_case_brent: float
    prob_brent_above_120: float
    prob_recession_signal: float            # P(GDP drag > 1.0pp)

    def to_dict(self) -> dict:
        return {
            "runs": self.runs,
            "metrics": self.metrics,
            "histograms": self.histograms,
            "worst_case_brent": round(self.worst_case_brent, 2),
            "prob_brent_above_120": round(self.prob_brent_above_120, 4),
            "prob_recession_signal": round(self.prob_recession_signal, 4),
        }


class WarGameSimulator:
    def __init__(self, engine: Optional[CausalEngine] = None,
                 seed: Optional[int] = config.RANDOM_SEED) -> None:
        self.engine = engine or CausalEngine()
        self.rng = np.random.default_rng(seed)

    # ------------------------------------------------------------------ #
    def _sample_event(self, base: ShockEvent) -> ShockEvent:
        """Draw a perturbed instance of the event's causal levers."""
        def clip01(x: float) -> float:
            return float(np.clip(x, 0.0, 1.0))

        # Multiplicative log-normal noise on intensities; additive on probs.
        noise = lambda mu: float(self.rng.normal(mu, max(0.05, abs(mu) * 0.35)))

        return ShockEvent(
            id=base.id,
            title=base.title,
            category=base.category,
            hormuz_closure_prob=clip01(base.hormuz_closure_prob + noise(0.0)),
            supply_loss_frac=max(0.0, base.supply_loss_frac * (1 + self.rng.normal(0, 0.4))),
            affected_suppliers=base.affected_suppliers,
            affected_corridors=base.affected_corridors,
            geopolitical_tension_delta=clip01(base.geopolitical_tension_delta + noise(0.0)),
            sanctions_pressure=clip01(base.sanctions_pressure),
            demand_shock_frac=base.demand_shock_frac + self.rng.normal(0, 0.01),
            brent_jump_pct=max(0.0, base.brent_jump_pct * (1 + self.rng.normal(0, 0.3))),
        )

    @staticmethod
    def _compound(events: List[ShockEvent], event_id: str, title: str) -> ShockEvent:
        """Merge several events into one compound (Black Swan) event."""
        return ShockEvent(
            id=event_id,
            title=title,
            category="black_swan",
            hormuz_closure_prob=min(1.0, max(e.hormuz_closure_prob for e in events)),
            supply_loss_frac=sum(e.supply_loss_frac for e in events),
            affected_suppliers=sorted({s for e in events for s in e.affected_suppliers}),
            affected_corridors=sorted({c for e in events for c in e.affected_corridors}),
            geopolitical_tension_delta=min(1.0, sum(e.geopolitical_tension_delta for e in events) * 0.8),
            sanctions_pressure=min(1.0, max(e.sanctions_pressure for e in events)),
            demand_shock_frac=sum(e.demand_shock_frac for e in events),
            brent_jump_pct=max(e.brent_jump_pct for e in events),
            narrative=" + ".join(e.title for e in events),
        )

    # ------------------------------------------------------------------ #
    def run(self, event: ShockEvent, runs: int = config.DEFAULT_SIM_RUNS
            ) -> ScenarioDistribution:
        samples = {"brent_usd": [], "inflation_delta_pp": [],
                   "gdp_drag_pp": [], "effective_shortfall_pct": []}

        for _ in range(runs):
            draw = self._sample_event(event)
            res = self.engine.evaluate(draw)
            samples["brent_usd"].append(res.brent_usd)
            samples["inflation_delta_pp"].append(res.inflation_delta_pp)
            samples["gdp_drag_pp"].append(res.gdp_drag_pp)
            samples["effective_shortfall_pct"].append(res.effective_shortfall_pct)

        arrs = {k: np.array(v) for k, v in samples.items()}
        metrics = {
            k: {
                "mean": round(float(a.mean()), 3),
                "p5": round(float(np.percentile(a, 5)), 3),
                "p50": round(float(np.percentile(a, 50)), 3),
                "p95": round(float(np.percentile(a, 95)), 3),
                "std": round(float(a.std()), 3),
            }
            for k, a in arrs.items()
        }

        histograms = {}
        for k, a in arrs.items():
            counts, edges = np.histogram(a, bins=20)
            histograms[k] = {
                "bins": [round(float(x), 2) for x in edges[:-1]],
                "counts": [int(c) for c in counts],
            }

        brent = arrs["brent_usd"]
        gdp = arrs["gdp_drag_pp"]
        return ScenarioDistribution(
            runs=runs,
            metrics=metrics,
            histograms=histograms,
            worst_case_brent=float(brent.max()),
            prob_brent_above_120=float((brent > 120).mean()),
            prob_recession_signal=float((np.abs(gdp) > 1.0).mean()),
        )

    def run_event_id(self, event_id: str, runs: int = config.DEFAULT_SIM_RUNS
                     ) -> ScenarioDistribution:
        return self.run(get_event(event_id), runs=runs)

    def black_swan(self, event_ids: List[str], runs: int = config.DEFAULT_SIM_RUNS,
                   title: Optional[str] = None) -> ScenarioDistribution:
        events = [get_event(e) for e in event_ids]
        compound = self._compound(
            events, "black_swan_" + "_".join(event_ids),
            title or ("Black Swan: " + " + ".join(e.title for e in events)),
        )
        return self.run(compound, runs=runs)
