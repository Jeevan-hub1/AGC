"""Sanctions & Compliance Intelligence Agent.

Evaluates sanctions exposure of the current supplier mix: which liftings face
payment/insurance/secondary-sanction risk, and how much import share is
jeopardised. Critical for India given ~36% Russian dependence.
"""

from __future__ import annotations

from geos.agents.base import Agent, AgentReport, Blackboard
from geos.data import seed_data as sd


class SanctionsAgent(Agent):
    name = "sanctions_intel"
    role = "Sanctions & Compliance Intelligence"

    def analyze(self, board: Blackboard) -> AgentReport:
        event = board.read("event")
        pressure = event.sanctions_pressure
        affected = set(event.affected_suppliers)

        exposed_share = 0.0
        flagged = []
        for s in sd.SUPPLIERS:
            risk = pressure if s.id in affected else 0.0
            # Russia carries structural secondary-sanctions risk even at baseline
            if s.country == "Russia":
                risk = max(risk, 0.4 + pressure * 0.4)
            if risk > 0.3:
                exposed_share += s.share
                flagged.append({
                    "supplier": s.name,
                    "share_pct": round(s.share * 100, 1),
                    "sanction_risk": round(risk, 2),
                })

        flagged.sort(key=lambda x: x["share_pct"], reverse=True)
        confidence = 0.72 + 0.2 * pressure

        headline = (
            f"{exposed_share*100:.0f}% of import volume under sanctions/payment "
            f"risk across {len(flagged)} supplier(s)."
        )

        recs = []
        if exposed_share > 0.3:
            recs.append(
                "Diversify away from sanction-exposed barrels; pre-clear "
                "alternative payment & insurance (non-USD, domestic P&I) channels."
            )
        if any(f["supplier"].startswith("Russia") for f in flagged):
            recs.append(
                "Secure rupee/dirham settlement rails for Russian crude continuity."
            )
        if not recs:
            recs.append("Sanctions exposure within tolerance; monitor.")

        return AgentReport(
            agent=self.name,
            headline=headline,
            confidence=min(0.95, confidence),
            findings={
                "sanctions_pressure": round(pressure, 2),
                "exposed_import_share_pct": round(exposed_share * 100, 1),
                "flagged_suppliers": flagged,
            },
            recommendations=recs,
        )
