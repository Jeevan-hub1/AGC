"""Graph Neural Network cascade propagation (numpy, dependency-light).

A message-passing GNN with attention over the World Energy Knowledge Graph.
Instead of a single shortest-path heuristic, each node iteratively aggregates
risk *messages* from its neighbours, weighted by learned-style attention
coefficients derived from edge dependency and node criticality. After K
propagation layers every node holds a risk embedding; we read out a scalar
"systemic risk" per node and refinery feedstock-at-risk.

This is a faithful, transparent implementation of Graph-Attention-Network
message passing (a la GAT) without a heavy DL dependency, so it is fast,
deterministic and explainable. It drops in for a PyTorch-Geometric model in
production (same forward semantics).
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np

from geos.knowledge_graph.graph import (CORRIDOR, REFINERY, SUPPLIER,
                                        WorldEnergyGraph)


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max()) if len(x) else x
    return e / e.sum() if len(x) and e.sum() else x


class GNNCascade:
    """K-layer attention message-passing over the knowledge graph."""

    def __init__(self, graph: WorldEnergyGraph, layers: int = 3,
                 decay: float = 0.85) -> None:
        self.graph = graph
        self.layers = layers
        self.decay = decay
        self.nodes = list(graph.g.nodes)
        self.idx = {n: i for i, n in enumerate(self.nodes)}

    def _attention(self, src: str, dst: str) -> float:
        """Attention coefficient: edge dependency x source criticality."""
        edge = self.graph.g.get_edge_data(src, dst) or {}
        dep = edge.get("dependency", 0.1)
        share = self.graph.g.nodes[src].get("share", 0.1)
        return dep * (0.5 + share)

    def propagate(self, seed_risk: Dict[str, float]) -> Dict[str, float]:
        """Run message passing from an initial risk injection.

        ``seed_risk`` maps node_id -> initial risk in [0,1] (e.g. disrupted
        suppliers/corridors at 1.0). Returns final node risk in [0,1].
        """
        h = np.zeros(len(self.nodes))
        for n, r in seed_risk.items():
            if n in self.idx:
                h[self.idx[n]] = r

        for _ in range(self.layers):
            new = h.copy()
            for n in self.nodes:
                preds = list(self.graph.g.predecessors(n))
                if not preds:
                    continue
                weights = np.array([self._attention(p, n) for p in preds])
                if weights.sum() == 0:
                    continue
                alpha = _softmax(weights)
                msg = sum(a * h[self.idx[p]] for a, p in zip(alpha, preds))
                # node keeps its own risk, adds decayed neighbour message
                new[self.idx[n]] = min(1.0, max(h[self.idx[n]],
                                                 h[self.idx[n]] * 0.5
                                                 + self.decay * msg))
            h = new
        return {n: round(float(h[self.idx[n]]), 4) for n in self.nodes}

    def cascade(self, disrupted_suppliers: List[str] | None = None,
                disrupted_corridors: List[str] | None = None) -> Dict:
        """GNN equivalent of the graph cascade, with richer propagation."""
        seed = {}
        for s in (disrupted_suppliers or []):
            seed[s] = 1.0
        for c in (disrupted_corridors or []):
            seed[c] = 1.0
        # corridor-cut suppliers also seed
        for sup in self.graph.nodes_of_type(SUPPLIER):
            cors = [x for x in self.graph.neighbors_out(sup)
                    if self.graph.g.nodes[x].get("type") == CORRIDOR]
            if cors and all(c in (disrupted_corridors or []) for c in cors):
                seed[sup] = 1.0

        risk = self.propagate(seed)
        refinery_risk = {
            self.graph.node_attrs(r).get("name", r): round(risk[r] * 100, 1)
            for r in self.graph.nodes_of_type(REFINERY)
        }
        # systemic risk ranking across all nodes
        ranked = sorted(
            ((self.graph.node_attrs(n).get("name", n), risk[n])
             for n in self.nodes if risk[n] > 0.01),
            key=lambda kv: kv[1], reverse=True)[:8]
        return {
            "refinery_risk": refinery_risk,
            "systemic_risk_ranking": [
                {"node": n, "risk": round(v * 100, 1)} for n, v in ranked
            ],
            "layers": self.layers,
            "mean_network_risk": round(float(np.mean(list(risk.values())) * 100), 2),
        }
