"""Maritime & Logistics Intelligence Agent.

Assesses corridor disruption, reroute penalties (added voyage days / freight),
and dark-fleet / sanctions-evasion signals. Consumes the knowledge-graph
cascade to quantify which refineries lose feedstock.
"""

from __future__ import annotations

from geos.agents.base import Agent, AgentReport, Blackboard
from geos.data import seed_data as sd

# Approximate added voyage days when a corridor is bypassed
REROUTE_PENALTY_DAYS = {
    "cor_hormuz": 0,        # no full bypass; volumes are stranded, not rerouted
    "cor_redsea": 14,       # Red Sea -> Cape of Good Hope
    "cor_malacca": 4,
}


class MaritimeAgent(Agent):
    name = "maritime_intel"
    role = "Maritime & Logistics Intelligence"

    def analyze(self, board: Blackboard) -> AgentReport:
        event = board.read("event")
        graph = board.read("graph")
        cascade = board.read("cascade", {})

        affected_corridors = event.affected_corridors
        added_days = max(
            [REROUTE_PENALTY_DAYS.get(c, 6) for c in affected_corridors],
            default=0,
        )

        # refineries with the most feedstock at risk
        ranked = sorted(cascade.items(), key=lambda kv: kv[1], reverse=True)
        top = [
            {
                "refinery": graph.node_attrs(rid).get("name", rid),
                "feedstock_at_risk_pct": round(v * 100, 1),
            }
            for rid, v in ranked[:3]
        ]

        # freight proxy: each added day ~ +1.4% landed cost; stranded Hormuz adds more
        freight_premium = added_days * 1.4
        if "cor_hormuz" in affected_corridors:
            freight_premium += event.hormuz_closure_prob * 12

        dark_fleet = event.sanctions_pressure > 0.5
        headline = (
            f"{len(affected_corridors) or 'No'} corridor(s) disrupted; "
            f"+{added_days} voyage days, ~+{freight_premium:.1f}% landed cost."
        )

        recs = []
        if added_days:
            recs.append(
                f"Pre-charter tankers now; reroute adds {added_days} days - "
                "freight rates will spike within 48h."
            )
        if "cor_hormuz" in affected_corridors:
            recs.append(
                "Prioritise non-Hormuz barrels (Russia/US/West Africa/Brazil)."
            )
        if dark_fleet:
            recs.append("Heightened dark-fleet / STS-transfer monitoring advised.")

        return AgentReport(
            agent=self.name,
            headline=headline,
            confidence=0.8,
            findings={
                "added_voyage_days": added_days,
                "freight_premium_pct": round(freight_premium, 1),
                "refineries_most_exposed": top,
                "dark_fleet_alert": dark_fleet,
            },
            recommendations=recs or ["No corridor mitigation required."],
        )
