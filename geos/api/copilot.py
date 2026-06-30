"""AI Copilot - a lightweight intent router over the GEOS engines.

Maps natural-language policymaker questions to the right engine call and
returns an explainable answer with confidence and supporting numbers. This is
deterministic keyword+entity routing (no external LLM needed for the demo); the
same interface accepts an LLM backend in production for free-form dialogue.
"""

from __future__ import annotations

import re
from typing import Dict

from geos import config
from geos.agents import SupervisorOrchestrator
from geos.data.events import EVENT_CATALOG, get_event

_EVENT_KEYWORDS = {
    "hormuz_partial": ["hormuz", "strait", "gulf closure"],
    "redsea_suspension": ["red sea", "houthi", "bab-el-mandeb", "suez"],
    "iran_export_drop": ["iran", "iranian"],
    "opec_emergency_cut": ["opec", "production cut", "output cut"],
    "russia_secondary_sanctions": ["russia", "russian", "urals", "sanction"],
    "global_war_shock": ["war", "multi-theater", "world war", "black swan"],
}


class Copilot:
    def __init__(self, orchestrator: SupervisorOrchestrator) -> None:
        self.orch = orchestrator

    def _match_event(self, q: str) -> str | None:
        q = q.lower()
        for eid, kws in _EVENT_KEYWORDS.items():
            if any(k in q for k in kws):
                return eid
        return None

    def ask(self, question: str) -> Dict:
        q = question.lower().strip()

        # Intent: how long can imports be sustained?
        if re.search(r"how long|sustain|days? of|reserve|cover", q):
            days = config.SPR_DAYS_COVER
            return {
                "intent": "reserve_cover",
                "answer": (
                    f"India holds ~{days} days of strategic petroleum reserve "
                    "cover at full national consumption. Under a partial Hormuz "
                    "disruption, parallel procurement extends effective cover, "
                    "but a sustained full closure would exhaust the buffer "
                    "quickly - hence the need for pre-positioned alternatives."
                ),
                "confidence": 0.9,
                "supporting": {"spr_days_cover": days,
                               "import_dependency": config.INDIA_CRUDE_IMPORT_DEPENDENCY},
            }

        # Intent: scenario "what happens if X"
        eid = self._match_event(q)
        if eid and re.search(r"what|happen|impact|affect|if|close|drop|cut", q):
            result = self.orch.respond_to_id(eid, sim_runs=2000)
            c = result["causal"]
            return {
                "intent": "scenario_impact",
                "event": result["event"]["title"],
                "answer": result["decision_brief"]["summary"],
                "confidence": result["decision_brief"]["confidence"],
                "supporting": {
                    "neri_before": result["neri_before"]["score"],
                    "neri_after": result["neri_after"]["score"],
                    "brent_usd": c["brent_usd"],
                    "inflation_delta_pp": c["inflation_delta_pp"],
                    "gdp_drag_pp": c["gdp_drag_pp"],
                },
                "top_actions": result["decision_brief"]["top_actions"],
            }

        # Intent: which refiners affected
        if re.search(r"refin|jamnagar|feedstock|plant", q):
            eid = eid or "hormuz_partial"
            result = self.orch.respond_to_id(eid, sim_runs=1000)
            return {
                "intent": "refinery_exposure",
                "event": result["event"]["title"],
                "answer": "Feedstock-at-risk by refinery (share of compatible inbound supply):",
                "confidence": 0.82,
                "supporting": result["cascade"],
            }

        # Fallback
        return {
            "intent": "unknown",
            "answer": (
                "I can answer questions about scenario impacts (e.g. 'What "
                "happens if Hormuz closes?'), reserve cover ('How long can India "
                "sustain imports?'), and refinery exposure. Try naming an event."
            ),
            "confidence": 0.4,
            "available_events": [e.title for e in EVENT_CATALOG.values()],
        }
