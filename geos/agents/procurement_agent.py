"""Autonomous Procurement Orchestrator Agent.

The action centrepiece: given the suppliers/corridors knocked out by a shock,
it computes the import shortfall and generates a *ranked, executable*
procurement plan that backfills the gap from alternative sources.

Ranking is a transparent multi-criteria utility model (game-theory friendly):

    utility = w_avail * spare_capacity_norm
            + w_rel   * reliability
            - w_cost  * spot_premium_norm
            - w_time  * lead_time_norm
            - w_sanc  * sanction_risk

Volumes are then allocated greedily against the shortfall, respecting each
alternative's realistic spare-lifting headroom. The output is something a
procurement desk can act on within hours - the stated evaluation goal.
"""

from __future__ import annotations

from typing import Dict, List

from geos import config
from geos.agents.base import Agent, AgentReport, Blackboard
from geos.data import seed_data as sd

WEIGHTS = {"avail": 0.30, "rel": 0.25, "cost": 0.20, "time": 0.15, "sanc": 0.10}

# Realistic incremental spare-lifting headroom as a multiple of current share
SPARE_HEADROOM = {
    "sup_sa": 1.2,   # Saudi has large spare capacity
    "sup_ae": 0.8,
    "sup_us": 1.5,   # US shale flexible
    "sup_ru": 0.4,
    "sup_iq": 0.5,
    "sup_ng": 0.7,
    "sup_br": 0.8,
    "sup_ku": 0.5,
}


class ProcurementAgent(Agent):
    name = "procurement_orchestrator"
    role = "Autonomous Procurement Orchestrator"

    def _disrupted_suppliers(self, board: Blackboard) -> set:
        event = board.read("event")
        graph = board.read("graph")
        disrupted = set(event.affected_suppliers)
        # corridor-cut suppliers (e.g. all-Hormuz suppliers if Hormuz blocked)
        if "cor_hormuz" in event.affected_corridors and event.hormuz_closure_prob > 0.4:
            for s in sd.SUPPLIERS:
                if s.via_hormuz:
                    disrupted.add(s.id)
        return disrupted

    def analyze(self, board: Blackboard) -> AgentReport:
        event = board.read("event")
        disrupted = self._disrupted_suppliers(board)

        by_id = {s.id: s for s in sd.SUPPLIERS}
        # shortfall = share of imports from disrupted suppliers, scaled by severity
        severity = max(event.hormuz_closure_prob, 0.5) if disrupted else 0.0
        shortfall_share = sum(by_id[d].share for d in disrupted) * severity

        # candidate alternatives = non-disrupted suppliers with spare headroom
        candidates = [s for s in sd.SUPPLIERS if s.id not in disrupted]

        # normalisation bounds
        max_premium = max(s.spot_premium_usd for s in sd.SUPPLIERS)
        max_lead = max(s.lead_time_days for s in sd.SUPPLIERS)

        scored: List[dict] = []
        for s in candidates:
            spare = SPARE_HEADROOM.get(s.id, 0.5) * s.share
            sanction_risk = 0.8 if s.country == "Russia" else 0.0
            if event.sanctions_pressure > 0.5 and s.id in event.affected_suppliers:
                sanction_risk = max(sanction_risk, event.sanctions_pressure)
            utility = (
                WEIGHTS["avail"] * (spare / (max(s.share for s in sd.SUPPLIERS)))
                + WEIGHTS["rel"] * s.reliability
                - WEIGHTS["cost"] * (s.spot_premium_usd / max_premium)
                - WEIGHTS["time"] * (s.lead_time_days / max_lead)
                - WEIGHTS["sanc"] * sanction_risk
            )
            scored.append({
                "supplier_id": s.id,
                "supplier": s.name,
                "grade": s.grade,
                "spare_share": spare,
                "reliability": s.reliability,
                "spot_premium_usd": s.spot_premium_usd,
                "lead_time_days": s.lead_time_days,
                "sanction_risk": round(sanction_risk, 2),
                "utility": round(utility, 4),
            })

        scored.sort(key=lambda x: x["utility"], reverse=True)

        # greedy allocation against the shortfall
        remaining = shortfall_share
        plan: List[dict] = []
        est_premium_cost = 0.0
        for c in scored:
            if remaining <= 1e-6:
                break
            take = min(c["spare_share"], remaining)
            if take <= 0:
                continue
            remaining -= take
            volume_mbpd = round(take * config.DAILY_CRUDE_DEMAND_MBPD, 3)
            est_premium_cost += volume_mbpd * 1_000_000 * c["spot_premium_usd"]
            plan.append({
                "rank": len(plan) + 1,
                "supplier": c["supplier"],
                "grade": c["grade"],
                "backfill_share_pct": round(take * 100, 2),
                "volume_mbpd": volume_mbpd,
                "spot_premium_usd": c["spot_premium_usd"],
                "lead_time_days": c["lead_time_days"],
                "utility_score": c["utility"],
            })

        coverage = (shortfall_share - remaining) / shortfall_share if shortfall_share else 1.0

        # --- game-theoretic spot pricing (Cournot-Nash equilibrium) ---
        shortfall_mbpd = shortfall_share * config.DAILY_CRUDE_DEMAND_MBPD
        equilibrium = None
        if shortfall_mbpd > 1e-3:
            from geos.optim.game_theory import ProcurementGame
            eq = ProcurementGame().solve(
                disrupted_ids=list(disrupted), shortfall_mbpd=shortfall_mbpd)
            equilibrium = eq.to_dict()

        headline = (
            f"Shortfall {shortfall_share*100:.1f}% of imports; generated "
            f"{len(plan)}-source plan covering {coverage*100:.0f}% "
            f"(uncovered {remaining*100:.1f}%)."
            + (f" Nash clearing price ${equilibrium['clearing_price_usd']:.0f}."
               if equilibrium else "")
        )

        recs = [
            f"Execute liftings from {p['supplier']} (+{p['backfill_share_pct']}%, "
            f"{p['volume_mbpd']} mbpd, {p['lead_time_days']}d lead)."
            for p in plan[:3]
        ]
        if remaining > 1e-3:
            recs.append(
                f"Residual {remaining*100:.1f}% gap - escalate to Strategic Reserve "
                "drawdown and demand-management."
            )

        return AgentReport(
            agent=self.name,
            headline=headline,
            confidence=0.83,
            findings={
                "disrupted_suppliers": [by_id[d].name for d in disrupted],
                "shortfall_share_pct": round(shortfall_share * 100, 2),
                "coverage_pct": round(coverage * 100, 1),
                "residual_gap_pct": round(remaining * 100, 2),
                "est_daily_premium_cost_usd": round(est_premium_cost, 0),
                "ranked_plan": plan,
                "nash_equilibrium": equilibrium,
            },
            recommendations=recs,
        )
