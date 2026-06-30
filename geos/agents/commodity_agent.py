"""Commodity & Price Intelligence Agent.

Reads the Causal Engine's price channel and the Monte Carlo distribution to
report the expected Brent trajectory, spot premia and tail risk. This is the
bridge between physical disruption and financial impact.
"""

from __future__ import annotations

from geos import config
from geos.agents.base import Agent, AgentReport, Blackboard


class CommodityAgent(Agent):
    name = "commodity_intel"
    role = "Commodity & Price Intelligence"

    def analyze(self, board: Blackboard) -> AgentReport:
        causal = board.read("causal")
        dist = board.read("scenario_distribution")

        brent = causal.brent_usd
        change = causal.brent_change_pct

        findings = {
            "baseline_brent_usd": config.BASELINE_BRENT_USD,
            "expected_brent_usd": round(brent, 1),
            "brent_change_pct": round(change, 1),
            "risk_premium_pct": round(causal.risk_premium_pct, 1),
        }
        if dist:
            b = dist.metrics["brent_usd"]
            findings.update({
                "brent_p5": b["p5"],
                "brent_p50": b["p50"],
                "brent_p95": b["p95"],
                "worst_case_brent": dist.worst_case_brent,
                "prob_brent_above_120": dist.prob_brent_above_120,
            })

        headline = (
            f"Brent expected ${brent:.0f} (+{change:.0f}%); "
            + (f"95th-pct ${dist.metrics['brent_usd']['p95']:.0f}, "
               f"P(>$120)={dist.prob_brent_above_120:.0%}." if dist else
               "run scenario for distribution.")
        )

        recs = []
        if change > 25:
            recs.append("Hedge near-month crude exposure; activate spot risk budget.")
        if dist and dist.prob_brent_above_120 > 0.5:
            recs.append(
                "High probability of >$120 Brent - pre-position fiscal buffer for "
                "fuel subsidy / excise adjustment."
            )
        if not recs:
            recs.append("Price impact contained; standard hedging sufficient.")

        return AgentReport(
            agent=self.name,
            headline=headline,
            confidence=0.85,
            findings=findings,
            recommendations=recs,
        )
