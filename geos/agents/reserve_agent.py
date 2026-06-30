"""Strategic Reserve Optimisation Agent.

Decides how to use the Strategic Petroleum Reserve (SPR) to cover the residual
import gap that procurement cannot immediately backfill. Produces a drawdown
schedule, days-of-cover under the shock, and a replenishment recommendation.
"""

from __future__ import annotations

from geos import config
from geos.agents.base import Agent, AgentReport, Blackboard
from geos.data import seed_data as sd


class ReserveAgent(Agent):
    name = "reserve_optimizer"
    role = "Strategic Reserve Optimisation"

    def analyze(self, board: Blackboard) -> AgentReport:
        proc = board.read("procurement_orchestrator", {})
        residual_gap = proc.get("residual_gap_pct", 0.0) / 100.0

        total_capacity_mmbbl = sum(r.capacity_mmbbl for r in sd.RESERVES)
        available_mmbbl = sum(r.capacity_mmbbl * r.fill_pct for r in sd.RESERVES)

        # daily gap volume to be covered by SPR (million barrels/day)
        daily_gap_mmbbl = residual_gap * config.DAILY_CRUDE_DEMAND_MBPD
        if daily_gap_mmbbl > 1e-6:
            days_cover = available_mmbbl / daily_gap_mmbbl
        else:
            days_cover = float("inf")

        # phased drawdown: cap daily release at 20% of demand to preserve buffer
        max_daily_release = 0.20 * config.DAILY_CRUDE_DEMAND_MBPD
        recommended_release = min(daily_gap_mmbbl, max_daily_release)

        schedule = []
        for r in sd.RESERVES:
            site_avail = r.capacity_mmbbl * r.fill_pct
            share = site_avail / available_mmbbl if available_mmbbl else 0
            schedule.append({
                "site": r.name,
                "available_mmbbl": round(site_avail, 2),
                "daily_release_mmbbl": round(recommended_release * share, 3),
            })

        finite_days = None if days_cover == float("inf") else round(days_cover, 1)

        # --- optimal drawdown via dynamic programming (finite-horizon MDP) ---
        dp_policy = None
        if daily_gap_mmbbl > 1e-6:
            from geos.optim.reserve_dp import ReserveDP
            dp = ReserveDP(total_reserve_mmbbl=available_mmbbl, horizon_days=30)
            dp_policy = dp.solve(daily_gap_mmbbl=daily_gap_mmbbl).to_dict()

        headline = (
            f"Residual gap {residual_gap*100:.1f}%/day; SPR provides "
            + (f"{finite_days} days of cover at current drawdown."
               if finite_days is not None else "ample cover (no gap).")
            + (f" DP-optimal day-1 release "
               f"{dp_policy['schedule_summary']['day1_release_mmbbl']} mmbbl."
               if dp_policy else "")
        )

        recs = []
        if residual_gap > 0:
            recs.append(
                f"Authorise phased SPR drawdown of {recommended_release:.2f} mmbbl/day "
                f"across {len(schedule)} sites."
            )
            if finite_days is not None and finite_days < 30:
                recs.append(
                    f"Cover is only {finite_days} days - trigger demand-management "
                    "and accelerate alternative procurement in parallel."
                )
            recs.append(
                "Pre-book replenishment cargoes for the post-disruption price dip."
            )
        else:
            recs.append("No SPR action required; maintain fill levels.")

        return AgentReport(
            agent=self.name,
            headline=headline,
            confidence=0.86,
            findings={
                "total_capacity_mmbbl": round(total_capacity_mmbbl, 1),
                "available_mmbbl": round(available_mmbbl, 1),
                "baseline_days_cover": config.SPR_DAYS_COVER,
                "days_cover_under_shock": finite_days,
                "recommended_daily_release_mmbbl": round(recommended_release, 3),
                "drawdown_schedule": schedule,
                "dp_optimal_policy": dp_policy,
            },
            recommendations=recs,
        )
