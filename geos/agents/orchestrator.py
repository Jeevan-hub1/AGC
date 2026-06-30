"""Supervisor Orchestrator.

The "digital brain" that turns a raw geopolitical event into a coordinated,
explainable national response. It:

  1. Seeds a shared Blackboard with the event, knowledge-graph cascade and the
     factual causal evaluation.
  2. Runs the specialist agents in dependency order (intelligence -> scenario
     -> action -> policy), each enriching the blackboard.
  3. Computes NERI before and after the shock.
  4. Assembles a single Decision Brief with the end-to-end audit trail.

The whole pipeline is synchronous and deterministic (seeded), so it returns a
full national response in well under a second - the demo's signature moment.
"""

from __future__ import annotations

import time
from typing import List, Optional

from geos import config
from geos.agents.base import Blackboard
from geos.agents.commodity_agent import CommodityAgent
from geos.agents.geopolitical_agent import GeopoliticalAgent
from geos.agents.maritime_agent import MaritimeAgent
from geos.agents.policy_agent import PolicyAgent
from geos.agents.procurement_agent import ProcurementAgent
from geos.agents.reserve_agent import ReserveAgent
from geos.agents.sanctions_agent import SanctionsAgent
from geos.agents.scenario_agent import ScenarioAgent
from geos.causal import CausalEngine
from geos.data.events import ShockEvent, get_event
from geos.knowledge_graph import build_world_graph
from geos.neri import NERICalculator


class SupervisorOrchestrator:
    def __init__(self, sim_runs: int = config.DEFAULT_SIM_RUNS) -> None:
        self.graph = build_world_graph()
        self.causal = CausalEngine()
        self.neri = NERICalculator()
        # ordered pipeline (dependency-respecting)
        self.pipeline = [
            GeopoliticalAgent(),
            MaritimeAgent(),
            SanctionsAgent(),
            ScenarioAgent(runs=sim_runs),
            CommodityAgent(),
            ProcurementAgent(),
            ReserveAgent(),
            PolicyAgent(),
        ]

    def roster(self) -> List[dict]:
        return [{"name": a.name, "role": a.role} for a in self.pipeline]

    def respond(self, event: ShockEvent, sim_runs: Optional[int] = None) -> dict:
        start = time.perf_counter()

        # --- factual world evaluation ---
        causal_result = self.causal.evaluate(event)
        cascade = self.graph.cascade(
            disrupted_suppliers=event.affected_suppliers,
            disrupted_corridors=event.affected_corridors,
        )
        neri_before = self.neri.compute()
        neri_after = self.neri.compute(
            causal=causal_result, hormuz_block=event.hormuz_closure_prob
        )

        board = Blackboard({
            "event": event,
            "graph": self.graph,
            "causal": causal_result,
            "cascade": cascade,
            "neri_before": neri_before,
            "neri_after": neri_after,
        })

        if sim_runs is not None:
            self.pipeline[3] = ScenarioAgent(runs=sim_runs)

        reports = [agent.run(board) for agent in self.pipeline]
        elapsed = (time.perf_counter() - start) * 1000

        return {
            "event": {
                "id": event.id, "title": event.title,
                "category": event.category, "narrative": event.narrative,
            },
            "neri_before": neri_before.to_dict(),
            "neri_after": neri_after.to_dict(),
            "neri_delta": round(neri_after.score - neri_before.score, 1),
            "causal": causal_result.to_dict(),
            "cascade": {
                self.graph.node_attrs(k).get("name", k): round(v * 100, 1)
                for k, v in cascade.items()
            },
            "scenario": (
                board.read("scenario_distribution").to_dict()
                if board.read("scenario_distribution") else None
            ),
            "agent_reports": [r.to_dict() for r in reports],
            "decision_brief": self._brief(board, reports, neri_before, neri_after),
            "total_elapsed_ms": round(elapsed, 1),
        }

    def respond_to_id(self, event_id: str, sim_runs: Optional[int] = None) -> dict:
        return self.respond(get_event(event_id), sim_runs=sim_runs)

    def respond_black_swan(self, event_ids: List[str],
                           sim_runs: Optional[int] = None) -> dict:
        from geos.scenario.montecarlo import WarGameSimulator
        events = [get_event(e) for e in event_ids]
        compound = WarGameSimulator._compound(
            events, "black_swan_" + "_".join(event_ids),
            "Black Swan: " + " + ".join(e.title for e in events),
        )
        result = self.respond(compound, sim_runs=sim_runs)
        result["black_swan_components"] = [e.title for e in events]
        return result

    # ------------------------------------------------------------------ #
    def _brief(self, board, reports, neri_before, neri_after) -> dict:
        proc = board.read("procurement_orchestrator", {})
        policy = board.read("policy_generator", {})
        causal = board.read("causal")
        return {
            "summary": (
                f"Resilience moved {neri_before.score:.0f} -> {neri_after.score:.0f} "
                f"({neri_after.band}). Brent ${causal.brent_usd:.0f} "
                f"(+{causal.brent_change_pct:.0f}%). Procurement plan covers "
                f"{proc.get('coverage_pct', 0)}% of shortfall."
            ),
            "top_actions": [
                a for a in (policy.get("policy_actions", []) or [])
                if a.get("priority") == "HIGH"
            ][:4],
            "confidence": round(
                sum(r.confidence for r in reports) / len(reports), 3
            ),
        }
