"""Game-theoretic procurement equilibrium.

Spot crude prices during a supply shock are not exogenous - they are the
outcome of strategic interaction between producers with market power. We model
this as a **Cournot oligopoly**: each non-disrupted supplier chooses an
incremental export quantity to maximise its own profit, given a downward-
sloping inverse-demand curve for the scarce barrels India must replace.

We solve for the **Nash equilibrium** by best-response fixed-point iteration:

    inverse demand:   P(Q) = a - b * Q           (Q = total extra supply)
    producer i profit: π_i = (P(Q) - c_i) * q_i
    best response:     q_i* = (a - c_i - b * Q_{-i}) / (2b)

Iterating the best responses converges to the unique interior Cournot-Nash
equilibrium. The clearing price feeds the procurement agent so spot premia are
*endogenous* to scarcity rather than fixed constants - a materially more
sophisticated model than a static premium table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np

from geos import config
from geos.data import seed_data as sd


@dataclass
class EquilibriumResult:
    clearing_price_usd: float          # equilibrium spot price (USD/bbl)
    total_extra_supply_mbpd: float
    iterations: int
    converged: bool
    allocations: List[dict] = field(default_factory=list)
    baseline_price_usd: float = config.BASELINE_BRENT_USD

    def to_dict(self) -> dict:
        return {
            "clearing_price_usd": round(self.clearing_price_usd, 2),
            "premium_over_baseline_usd": round(
                self.clearing_price_usd - self.baseline_price_usd, 2),
            "total_extra_supply_mbpd": round(self.total_extra_supply_mbpd, 3),
            "iterations": self.iterations,
            "converged": self.converged,
            "allocations": self.allocations,
        }


class ProcurementGame:
    """Cournot-Nash equilibrium solver for scarce-barrel spot pricing."""

    def __init__(self, demand_intercept: float | None = None,
                 demand_slope: float = 55.0) -> None:
        # a: choke price (USD) when no extra barrels supplied during scarcity
        self.a = demand_intercept
        self.b = demand_slope        # price sensitivity to total extra supply

    def _marginal_cost(self, supplier: "sd.Supplier") -> float:
        """Producer marginal cost proxy = baseline + its spot premium,
        discounted by reliability (reliable producers act as lower-cost)."""
        return (config.BASELINE_BRENT_USD + supplier.spot_premium_usd
                * (1.4 - supplier.reliability))

    def solve(self, disrupted_ids: List[str], shortfall_mbpd: float,
              max_iter: int = 200, tol: float = 1e-4) -> EquilibriumResult:
        players = [s for s in sd.SUPPLIERS if s.id not in set(disrupted_ids)]
        if not players:
            return EquilibriumResult(config.BASELINE_BRENT_USD * 2, 0, 0, False)

        # choke price scales with how big the shortfall is (scarcity intensity)
        scarcity = min(2.0, 0.5 + shortfall_mbpd)
        a = self.a if self.a is not None else config.BASELINE_BRENT_USD * (1 + scarcity)
        b = self.b
        costs = np.array([self._marginal_cost(s) for s in players])
        # capacity caps (max incremental barrels each can lift), in mbpd
        from geos.agents.procurement_agent import SPARE_HEADROOM
        caps = np.array([SPARE_HEADROOM.get(s.id, 0.5) * s.share
                         * config.DAILY_CRUDE_DEMAND_MBPD for s in players])

        q = np.zeros(len(players))
        converged = False
        it = 0
        for it in range(1, max_iter + 1):
            q_prev = q.copy()
            for i in range(len(players)):
                Q_minus = q.sum() - q[i]
                br = (a - costs[i] - b * Q_minus) / (2 * b)
                q[i] = float(np.clip(br, 0.0, caps[i]))
            if np.max(np.abs(q - q_prev)) < tol:
                converged = True
                break

        Q = float(q.sum())
        price = max(config.BASELINE_BRENT_USD, a - b * Q)

        allocations = []
        for i, s in enumerate(players):
            if q[i] <= 1e-6:
                continue
            allocations.append({
                "supplier": s.name,
                "supplier_id": s.id,
                "extra_supply_mbpd": round(float(q[i]), 3),
                "marginal_cost_usd": round(float(costs[i]), 2),
                "profit_usd_per_day": round(float((price - costs[i]) * q[i] * 1e6), 0),
            })
        allocations.sort(key=lambda x: x["extra_supply_mbpd"], reverse=True)

        return EquilibriumResult(
            clearing_price_usd=price,
            total_extra_supply_mbpd=Q,
            iterations=it,
            converged=converged,
            allocations=allocations,
        )
