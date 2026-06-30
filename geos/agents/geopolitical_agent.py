"""Geopolitical Intelligence Agent.

Converts a shock event into structured geopolitical risk scores (Hormuz,
Red Sea, supplier stability, overall maritime threat) and an AI-style summary.
In production this agent ingests GDELT / news / diplomatic feeds; here it
reasons over the event's declared tension levers and the knowledge graph.
"""

from __future__ import annotations

from geos.agents.base import Agent, AgentReport, Blackboard
from geos.data import seed_data as sd


class GeopoliticalAgent(Agent):
    name = "geopolitical_intel"
    role = "Geopolitical Risk Intelligence"

    def analyze(self, board: Blackboard) -> AgentReport:
        event = board.read("event")
        tension = event.geopolitical_tension_delta

        hormuz_risk = min(100, (event.hormuz_closure_prob * 70 + tension * 30))
        redsea_risk = 30 + (40 if "cor_redsea" in event.affected_corridors else 0) \
            + tension * 20
        maritime_threat = max(hormuz_risk, redsea_risk)

        # supplier stability = reliability discounted by whether affected
        affected = set(event.affected_suppliers)
        stability = {}
        for s in sd.SUPPLIERS:
            base = s.reliability * 100
            if s.id in affected:
                base *= 0.5
            stability[s.name] = round(base, 1)

        worst = min(stability.items(), key=lambda kv: kv[1])
        confidence = 0.7 + 0.2 * min(1.0, tension + event.hormuz_closure_prob)

        headline = (
            f"Geopolitical tension elevated ({tension:.0%}); "
            f"Hormuz risk {hormuz_risk:.0f}/100, maritime threat "
            f"{maritime_threat:.0f}/100."
        )

        return AgentReport(
            agent=self.name,
            headline=headline,
            confidence=min(0.97, confidence),
            findings={
                "hormuz_risk": round(hormuz_risk, 1),
                "redsea_risk": round(min(100, redsea_risk), 1),
                "maritime_threat": round(min(100, maritime_threat), 1),
                "supplier_stability": stability,
                "least_stable_supplier": worst[0],
                "tension": round(tension, 3),
            },
            recommendations=[
                f"Flag {worst[0]} as the least-stable lifting source this window.",
                "Raise diplomatic channels for Gulf transit assurances."
                if hormuz_risk > 50 else "Maintain standard diplomatic posture.",
            ],
        )
