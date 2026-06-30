"""Optimal Strategic Petroleum Reserve drawdown via dynamic programming.

We treat SPR management during a shock as a finite-horizon Markov Decision
Process and solve it with **backward value iteration** (the optimal-control /
RL bedrock):

    state  : (day, reserve_level)
    action : daily release r in [0, max_release]
    reward : -(unmet_gap_cost) - (depletion_penalty) - (release_cost)
    dynamics: reserve_{t+1} = reserve_t - r ; gap may shrink as procurement
              ramps and the disruption resolves stochastically.

Backward induction yields the value function V*(day, level) and the optimal
policy pi*(day, level) - i.e. exactly how many barrels to release each day to
minimise the expected economic damage while preserving a strategic buffer.
This replaces the previous fixed-fraction heuristic with a provably optimal
schedule under the stated model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np

from geos import config


@dataclass
class ReservePolicy:
    horizon_days: int
    optimal_release_schedule: List[float]   # mbbl/day per day
    expected_days_cover: float
    final_reserve_mmbbl: float
    total_unmet_gap_mmbbl: float
    value: float
    schedule_summary: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "horizon_days": self.horizon_days,
            "optimal_release_schedule": [round(x, 3) for x in self.optimal_release_schedule],
            "expected_days_cover": round(self.expected_days_cover, 1),
            "final_reserve_mmbbl": round(self.final_reserve_mmbbl, 2),
            "total_unmet_gap_mmbbl": round(self.total_unmet_gap_mmbbl, 2),
            "value": round(self.value, 1),
            "schedule_summary": self.schedule_summary,
        }


class ReserveDP:
    """Finite-horizon MDP solver for optimal reserve drawdown."""

    def __init__(self, total_reserve_mmbbl: float, horizon_days: int = 30,
                 level_steps: int = 60, action_steps: int = 16) -> None:
        self.R = total_reserve_mmbbl
        self.H = horizon_days
        self.levels = np.linspace(0, total_reserve_mmbbl, level_steps)
        self.max_release = 0.25 * config.DAILY_CRUDE_DEMAND_MBPD  # cap mbbl/day
        self.actions = np.linspace(0, self.max_release, action_steps)

    def _gap_at(self, day: int, daily_gap0: float) -> float:
        """Expected supply gap on a given day (declines as procurement ramps
        and the disruption probabilistically resolves)."""
        ramp = max(0.0, 1.0 - day / max(1, self.H))   # procurement backfills
        resolve = 0.985 ** day                          # disruption decays
        return daily_gap0 * ramp * resolve

    def solve(self, daily_gap_mmbbl: float, depletion_penalty: float = 40.0,
              unmet_cost: float = 120.0) -> ReservePolicy:
        nL = len(self.levels)
        V = np.zeros((self.H + 1, nL))
        policy = np.zeros((self.H, nL))

        # terminal value: reward for reserve remaining (strategic buffer)
        V[self.H] = -depletion_penalty * (1 - self.levels / self.R)

        for day in range(self.H - 1, -1, -1):
            gap = self._gap_at(day, daily_gap_mmbbl)
            for li, level in enumerate(self.levels):
                best_v, best_a = -1e18, 0.0
                for r in self.actions:
                    release = min(r, level)
                    unmet = max(0.0, gap - release)
                    nxt = level - release
                    ni = int(np.clip(np.searchsorted(self.levels, nxt), 0, nL - 1))
                    reward = (-unmet_cost * unmet
                              - 2.0 * release            # mild release cost
                              - depletion_penalty * (1 - nxt / self.R) * 0.05)
                    v = reward + V[day + 1, ni]
                    if v > best_v:
                        best_v, best_a = v, release
                V[day, li] = best_v
                policy[day, li] = best_a

        # roll forward from full reserve to extract the realised schedule
        level = self.R
        schedule, unmet_total = [], 0.0
        for day in range(self.H):
            li = int(np.clip(np.searchsorted(self.levels, level), 0, nL - 1))
            r = float(policy[day, li])
            gap = self._gap_at(day, daily_gap_mmbbl)
            unmet_total += max(0.0, gap - r)
            level = max(0.0, level - r)
            schedule.append(r)

        avg_gap = max(1e-9, np.mean([self._gap_at(d, daily_gap_mmbbl)
                                     for d in range(self.H)]))
        days_cover = self.R / avg_gap if avg_gap > 1e-6 else float("inf")

        return ReservePolicy(
            horizon_days=self.H,
            optimal_release_schedule=schedule,
            expected_days_cover=min(days_cover, 999),
            final_reserve_mmbbl=level,
            total_unmet_gap_mmbbl=unmet_total,
            value=float(V[0, -1]),
            schedule_summary={
                "peak_release_mmbbl": round(float(max(schedule)), 3),
                "day1_release_mmbbl": round(schedule[0], 3),
                "total_released_mmbbl": round(self.R - level, 2),
            },
        )
