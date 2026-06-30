"""Scenario / War-Gaming Agent.

Runs the Monte Carlo simulator for the active event and publishes the
probability distribution to the blackboard for downstream agents.
"""

from __future__ import annotations

from geos import config
from geos.agents.base import Agent, AgentReport, Blackboard
from geos.scenario import WarGameSimulator


class ScenarioAgent(Agent):
    name = "scenario_wargamer"
    role = "Scenario War-Gaming"

    def __init__(self, runs: int = config.DEFAULT_SIM_RUNS) -> None:
        self.runs = runs
        self.sim = WarGameSimulator()

    def analyze(self, board: Blackboard) -> AgentReport:
        event = board.read("event")
        dist = self.sim.run(event, runs=self.runs)
        board.write("scenario_distribution", dist)

        b = dist.metrics["brent_usd"]
        infl = dist.metrics["inflation_delta_pp"]
        headline = (
            f"Simulated {dist.runs:,} futures: Brent p50 ${b['p50']:.0f} "
            f"(p5 ${b['p5']:.0f} / p95 ${b['p95']:.0f}); "
            f"recession-signal probability {dist.prob_recession_signal:.0%}."
        )

        return AgentReport(
            agent=self.name,
            headline=headline,
            confidence=0.9,
            findings={
                "runs": dist.runs,
                "brent": b,
                "inflation_delta_pp": infl,
                "prob_brent_above_120": dist.prob_brent_above_120,
                "prob_recession_signal": dist.prob_recession_signal,
                "worst_case_brent": round(dist.worst_case_brent, 1),
            },
            recommendations=[
                "Plan against the p95 tail, not the mean - resilience is set "
                "by the worst plausible case.",
            ],
        )
