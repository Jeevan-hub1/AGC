"""National Energy Resilience Index (NERI).

A composite 0-100 score (higher = more resilient) built from eight transparent
sub-indicators. Each sub-indicator is normalised to 0-100, then combined with
the documented weights in ``config.NERI_WEIGHTS``.

NERI is the platform's headline early-warning number: it sits at a healthy
baseline in calm conditions and collapses toward the critical band when a shock
propagates through suppliers, corridors, prices and reserves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from geos import config
from geos.causal.scm import CausalResult
from geos.data import seed_data as sd


def _band(score: float) -> str:
    if score < config.NERI_CRITICAL:
        return "CRITICAL"
    if score < config.NERI_WATCH:
        return "WATCH"
    if score < 75:
        return "STABLE"
    return "RESILIENT"


@dataclass
class NERIScore:
    score: float
    band: str
    components: Dict[str, float]            # sub-indicator -> 0-100
    weighted_contributions: Dict[str, float]
    drivers: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 1),
            "band": self.band,
            "components": {k: round(v, 1) for k, v in self.components.items()},
            "weighted_contributions": {
                k: round(v, 2) for k, v in self.weighted_contributions.items()
            },
            "drivers": self.drivers,
        }


class NERICalculator:
    """Compute NERI from baseline structure + an optional active shock."""

    def __init__(self, baseline_brent: float | None = None) -> None:
        self.weights = config.NERI_WEIGHTS
        self._baseline_brent = baseline_brent

    @property
    def baseline_brent(self) -> float:
        return self._baseline_brent if self._baseline_brent else config.BASELINE_BRENT_USD

    # ---- sub-indicators (each returns 0-100, higher = more resilient) ---- #
    def _import_dependency(self) -> float:
        # 88% import dependency -> low resilience on this axis
        return (1 - config.INDIA_CRUDE_IMPORT_DEPENDENCY) * 100 + 50 * (
            1 - config.INDIA_CRUDE_IMPORT_DEPENDENCY
        )

    def _supplier_diversity(self) -> float:
        # Herfindahl-Hirschman based: lower concentration -> higher resilience
        hhi = sum(s.share ** 2 for s in sd.SUPPLIERS)
        return float(max(0.0, (1 - hhi) * 100))

    def _route_vulnerability(self, hormuz_block: float) -> float:
        exposure = config.HORMUZ_TRANSIT_SHARE
        # baseline penalises the structural Hormuz exposure; shock worsens it
        base = (1 - exposure) * 100
        return float(max(0.0, base * (1 - 0.8 * hormuz_block)))

    def _strategic_reserves(self) -> float:
        # 9.5 days cover vs a 30-day comfort target
        target_days = 30.0
        return float(min(100.0, (config.SPR_DAYS_COVER / target_days) * 100))

    def _price_stability(self, brent: float) -> float:
        # full marks at baseline; degrades as Brent rises above baseline
        ratio = brent / self.baseline_brent
        return float(max(0.0, 100 - (ratio - 1) * 120))

    def _geopolitical_tension(self, tension: float) -> float:
        return float(max(0.0, (1 - tension) * 100))

    def _logistics_risk(self, hormuz_block: float) -> float:
        avg_route_risk = sum(c.base_risk for c in sd.CORRIDORS) / len(sd.CORRIDORS)
        return float(max(0.0, (1 - avg_route_risk) * 100 * (1 - 0.5 * hormuz_block)))

    def _demand_pressure(self, shortfall_pct: float) -> float:
        return float(max(0.0, 100 - shortfall_pct * 2.5))

    # --------------------------------------------------------------- #
    def compute(self, causal: Optional[CausalResult] = None,
                tension: float = 0.1, hormuz_block: float = 0.0) -> NERIScore:
        brent = causal.brent_usd if causal else config.BASELINE_BRENT_USD
        shortfall = causal.effective_shortfall_pct if causal else 0.0
        if causal:
            # infer tension/hormuz from the shock if not explicitly supplied
            tension = max(tension, min(1.0, causal.risk_premium_pct / 12.0))

        components = {
            "import_dependency": self._import_dependency(),
            "route_vulnerability": self._route_vulnerability(hormuz_block),
            "strategic_reserves": self._strategic_reserves(),
            "supplier_diversity": self._supplier_diversity(),
            "price_stability": self._price_stability(brent),
            "geopolitical_tension": self._geopolitical_tension(tension),
            "logistics_risk": self._logistics_risk(hormuz_block),
            "demand_pressure": self._demand_pressure(shortfall),
        }

        contributions = {k: components[k] * self.weights[k] for k in components}
        score = sum(contributions.values())

        # identify the weakest weighted drivers
        drivers = sorted(contributions.items(), key=lambda kv: kv[1])[:3]
        driver_msgs = [
            f"{k.replace('_', ' ').title()} at {components[k]:.0f}/100 "
            f"(contributes {contributions[k]:.1f} pts)"
            for k, _ in drivers
        ]

        return NERIScore(
            score=score,
            band=_band(score),
            components=components,
            weighted_contributions=contributions,
            drivers=driver_msgs,
        )
