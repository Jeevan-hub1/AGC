"""Predictive Risk Agent — the foresight layer.

Runs FIRST in the pipeline. Uses the trained Geopolitical Risk Foundation
Model to forecast per-corridor disruption probability and lead time, and the
attention GNN to propagate systemic risk across the knowledge graph. Publishes
``risk_forecast`` and ``gnn_cascade`` to the blackboard so every downstream
agent reasons against a forward-looking, ML-derived risk picture rather than
just the declared event.
"""

from __future__ import annotations

from geos.agents.base import Agent, AgentReport, Blackboard
from geos.ml import GNNCascade, get_risk_model


class PredictiveRiskAgent(Agent):
    name = "predictive_risk"
    role = "Predictive Risk (Foundation Model + GNN)"

    def analyze(self, board: Blackboard) -> AgentReport:
        event = board.read("event")
        graph = board.read("graph")

        model = get_risk_model()
        preds = model.predict_corridors(event)
        top = preds[0]

        gnn = GNNCascade(graph)
        gnn_res = gnn.cascade(
            disrupted_suppliers=getattr(event, "affected_suppliers", []),
            disrupted_corridors=getattr(event, "affected_corridors", []),
        )

        forecast = [p.to_dict() for p in preds]
        board.write("risk_forecast", forecast)
        board.write("gnn_cascade", gnn_res)
        board.write("model_auc", model.auc_)

        headline = (
            f"Foundation model (AUC {model.auc_:.2f}) flags '{top.corridor_name}' "
            f"at {top.disruption_probability:.0%} disruption probability with "
            f"~{top.lead_time_days:.0f}-day lead time."
        )

        return AgentReport(
            agent=self.name,
            headline=headline,
            confidence=float(min(0.95, 0.6 + model.auc_ * 0.35)),
            findings={
                "model_auc": round(model.auc_, 3),
                "corridor_forecast": forecast,
                "highest_risk_corridor": top.corridor_name,
                "lead_time_days": round(top.lead_time_days, 1),
                "gnn_mean_network_risk": gnn_res["mean_network_risk"],
                "gnn_systemic_ranking": gnn_res["systemic_risk_ranking"][:5],
            },
            recommendations=[
                f"Act within the {top.lead_time_days:.0f}-day window before "
                f"'{top.corridor_name}' crosses the disruption threshold.",
                "GNN propagation shows risk concentrating at "
                f"{gnn_res['systemic_risk_ranking'][0]['node']}."
                if gnn_res["systemic_risk_ranking"] else "Network risk contained.",
            ],
        )
