"""Generative Policy Agent.

Synthesises a prioritised, explainable national response package from every
upstream agent's findings: emergency measures, demand-management, fiscal
buffers, and diplomatic actions - each tagged with rationale and urgency.

This is template-driven generative reasoning (no external LLM dependency) so
the demo is deterministic; the same interface accepts an LLM backend in
production for free-form policy drafting.
"""

from __future__ import annotations

from typing import List

from geos.agents.base import Agent, AgentReport, Blackboard


class PolicyAgent(Agent):
    name = "policy_generator"
    role = "Generative Policy Synthesis"

    def analyze(self, board: Blackboard) -> AgentReport:
        causal = board.read("causal")
        proc = board.read("procurement_orchestrator", {})
        reserve = board.read("reserve_optimizer", {})
        sanctions = board.read("sanctions_intel", {})
        neri = board.read("neri_after")

        actions: List[dict] = []

        def add(priority: str, domain: str, action: str, rationale: str):
            actions.append({
                "priority": priority, "domain": domain,
                "action": action, "rationale": rationale,
            })

        # Price / fiscal
        if causal and causal.brent_change_pct > 25:
            add("HIGH", "Fiscal",
                "Pre-authorise a fuel-excise buffer and targeted LPG/diesel subsidy.",
                f"Brent +{causal.brent_change_pct:.0f}% drives CPI "
                f"+{causal.inflation_delta_pp:.2f}pp; protect vulnerable consumers.")

        # Procurement
        if proc.get("coverage_pct", 100) < 100:
            add("HIGH", "Procurement",
                "Empower refiners to lift spot cargoes from ranked alternatives "
                "under emergency procurement delegation.",
                f"Plan covers {proc.get('coverage_pct')}% of the "
                f"{proc.get('shortfall_share_pct')}% shortfall.")

        # Reserves
        if reserve.get("days_cover_under_shock") is not None:
            add("MEDIUM", "Strategic Reserve",
                f"Begin phased SPR drawdown ({reserve.get('recommended_daily_release_mmbbl')}"
                " mmbbl/day) with replenishment pre-booking.",
                f"Provides {reserve.get('days_cover_under_shock')} days of gap cover.")

        # Sanctions / diplomacy
        if sanctions.get("exposed_import_share_pct", 0) > 30:
            add("HIGH", "Diplomacy/Finance",
                "Activate non-USD settlement and domestic marine-insurance backstops.",
                f"{sanctions.get('exposed_import_share_pct')}% of imports face "
                "sanctions/payment risk.")

        # Demand management
        if causal and causal.power_sector_stress > 20:
            add("MEDIUM", "Demand Management",
                "Issue voluntary demand-curtailment advisory for non-essential "
                "industrial fuel use; prioritise power-sector feedstock.",
                f"Power-sector stress index {causal.power_sector_stress:.0f}.")

        if not actions:
            add("LOW", "Monitoring",
                "Maintain heightened monitoring; no emergency measures required.",
                "Impact within tolerance.")

        order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        actions.sort(key=lambda a: order[a["priority"]])

        band = neri.band if neri else "n/a"
        headline = (
            f"Generated {len(actions)} prioritised policy actions "
            f"(NERI band: {band})."
        )

        return AgentReport(
            agent=self.name,
            headline=headline,
            confidence=0.8,
            findings={"policy_actions": actions, "neri_band": band},
            recommendations=[f"[{a['priority']}] {a['action']}" for a in actions[:4]],
        )
