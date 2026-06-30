"""Catalog of geopolitical / logistics shock events the system reasons about.

Each event declares the *causal levers* it pulls. The Causal Engine consumes
these levers; the Monte Carlo simulator samples around them; the agents narrate
and act on them. This keeps event semantics in one auditable place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ShockEvent:
    id: str
    title: str
    category: str
    # Causal levers (signed deltas applied to model variables)
    hormuz_closure_prob: float = 0.0      # 0-1 probability corridor blocked
    supply_loss_frac: float = 0.0         # fraction of global supply removed
    affected_suppliers: List[str] = field(default_factory=list)
    affected_corridors: List[str] = field(default_factory=list)
    geopolitical_tension_delta: float = 0.0   # 0-1 added tension
    sanctions_pressure: float = 0.0           # 0-1 sanctions intensity
    demand_shock_frac: float = 0.0            # +/- demand change
    brent_jump_pct: float = 0.0               # immediate price reaction prior
    narrative: str = ""


EVENT_CATALOG: Dict[str, ShockEvent] = {
    "hormuz_partial": ShockEvent(
        id="hormuz_partial",
        title="Strait of Hormuz Partial Closure (14 days)",
        category="maritime_chokepoint",
        hormuz_closure_prob=0.65,
        affected_corridors=["cor_hormuz"],
        affected_suppliers=["sup_iq", "sup_sa", "sup_ae", "sup_ku"],
        geopolitical_tension_delta=0.45,
        brent_jump_pct=0.18,
        narrative=(
            "Military escalation forces a partial closure of the Strait of "
            "Hormuz. ~42% of India's crude imports are exposed."
        ),
    ),
    "iran_export_drop": ShockEvent(
        id="iran_export_drop",
        title="Iran Exports Drop 30% (sanctions enforcement)",
        category="sanctions",
        supply_loss_frac=0.015,
        sanctions_pressure=0.6,
        geopolitical_tension_delta=0.25,
        brent_jump_pct=0.06,
        narrative=(
            "Renewed US sanctions enforcement removes ~1.5% of global supply; "
            "secondary-sanctions risk chills Russian and Gulf liftings."
        ),
    ),
    "redsea_suspension": ShockEvent(
        id="redsea_suspension",
        title="Red Sea Shipping Suspension (Houthi attacks)",
        category="maritime_chokepoint",
        affected_corridors=["cor_redsea"],
        affected_suppliers=["sup_us", "sup_ng"],
        geopolitical_tension_delta=0.2,
        brent_jump_pct=0.05,
        narrative=(
            "Escalating attacks suspend Red Sea transit; Atlantic-basin barrels "
            "reroute around the Cape, adding 12-18 voyage days."
        ),
    ),
    "opec_emergency_cut": ShockEvent(
        id="opec_emergency_cut",
        title="OPEC+ Emergency Production Cut (2 mbpd)",
        category="opec_policy",
        supply_loss_frac=0.02,
        geopolitical_tension_delta=0.1,
        brent_jump_pct=0.09,
        narrative=(
            "OPEC+ announces a surprise 2 mbpd cut to defend prices, tightening "
            "spot availability for Asian refiners."
        ),
    ),
    "russia_secondary_sanctions": ShockEvent(
        id="russia_secondary_sanctions",
        title="Secondary Sanctions on Russian Crude Buyers",
        category="sanctions",
        affected_suppliers=["sup_ru"],
        sanctions_pressure=0.7,
        supply_loss_frac=0.01,
        geopolitical_tension_delta=0.3,
        brent_jump_pct=0.08,
        narrative=(
            "Secondary sanctions threaten payment and insurance channels for "
            "discounted Russian crude - India's single largest supplier (~36%)."
        ),
    ),
    "global_war_shock": ShockEvent(
        id="global_war_shock",
        title="Multi-Theater Conflict (black-swan stress)",
        category="systemic",
        hormuz_closure_prob=0.8,
        supply_loss_frac=0.05,
        affected_corridors=["cor_hormuz", "cor_redsea"],
        affected_suppliers=["sup_iq", "sup_sa", "sup_ae", "sup_ku", "sup_ru"],
        geopolitical_tension_delta=0.8,
        sanctions_pressure=0.5,
        brent_jump_pct=0.35,
        narrative=(
            "Simultaneous Gulf and Atlantic disruptions - a tail scenario used "
            "to stress-test national resilience and SPR adequacy."
        ),
    ),
}


def list_events() -> List[dict]:
    return [
        {
            "id": e.id,
            "title": e.title,
            "category": e.category,
            "narrative": e.narrative,
        }
        for e in EVENT_CATALOG.values()
    ]


def get_event(event_id: str) -> ShockEvent:
    if event_id not in EVENT_CATALOG:
        raise KeyError(f"Unknown event '{event_id}'. Known: {list(EVENT_CATALOG)}")
    return EVENT_CATALOG[event_id]
