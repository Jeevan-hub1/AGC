"""World Energy Knowledge Graph.

A directed, typed graph that wires together suppliers, the corridors they
transit, the refineries that can process their grades, and the strategic
reserves that buffer shortfalls. Edges carry a ``dependency`` weight so we can
propagate a disruption forward and discover *cascading* impacts that no single
node reveals on its own.

This is a self-contained networkx implementation (no external graph DB) so the
demo boots instantly, while exposing a clean API that maps 1:1 onto a Neo4j /
GNN backend for the production roadmap.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import networkx as nx

from geos.data import seed_data as sd


# Node type constants
COUNTRY = "country"
SUPPLIER = "supplier"
CORRIDOR = "corridor"
REFINERY = "refinery"
RESERVE = "reserve"
COMMODITY = "commodity"


class WorldEnergyGraph:
    """Typed wrapper around a networkx DiGraph with disruption propagation."""

    def __init__(self, graph: nx.DiGraph) -> None:
        self.g = graph

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    def nodes_of_type(self, ntype: str) -> List[str]:
        return [n for n, d in self.g.nodes(data=True) if d.get("type") == ntype]

    def neighbors_out(self, node: str) -> List[str]:
        return list(self.g.successors(node))

    def node_attrs(self, node: str) -> dict:
        return dict(self.g.nodes[node])

    # ------------------------------------------------------------------ #
    # Core analytics
    # ------------------------------------------------------------------ #
    def systemic_vulnerability(self) -> Dict[str, float]:
        """Rank nodes by how much import flow depends on them.

        Uses a flow-weighted betweenness proxy: a node's score is the sum of
        supplier shares whose shortest path to the Indian refinery layer passes
        through it. High score => single point of failure.
        """
        scores: Dict[str, float] = {n: 0.0 for n in self.g.nodes}
        refineries = set(self.nodes_of_type(REFINERY))

        for sup in self.nodes_of_type(SUPPLIER):
            share = self.g.nodes[sup].get("share", 0.0)
            # find a path from supplier to any refinery
            for ref in refineries:
                if nx.has_path(self.g, sup, ref):
                    path = nx.shortest_path(self.g, sup, ref)
                    for n in path:
                        scores[n] += share
                    break
        return dict(sorted(scores.items(), key=lambda kv: kv[1], reverse=True))

    def cascade(
        self,
        disrupted_suppliers: Optional[List[str]] = None,
        disrupted_corridors: Optional[List[str]] = None,
    ) -> Dict[str, float]:
        """Propagate a disruption and return per-refinery feedstock-at-risk.

        Returns a mapping refinery_id -> fraction of its compatible inbound
        supply that is now jeopardised (0-1).
        """
        disrupted_suppliers = set(disrupted_suppliers or [])
        disrupted_corridors = set(disrupted_corridors or [])

        # A supplier is "cut" if directly disrupted OR all its corridors are cut.
        cut_suppliers: set = set(disrupted_suppliers)
        for sup in self.nodes_of_type(SUPPLIER):
            corridors = [
                c for c in self.neighbors_out(sup)
                if self.g.nodes[c].get("type") == CORRIDOR
            ]
            if corridors and all(c in disrupted_corridors for c in corridors):
                cut_suppliers.add(sup)

        impact: Dict[str, float] = {}
        for ref in self.nodes_of_type(REFINERY):
            # Inbound suppliers that feed this refinery (reverse edges through corridor)
            feeders = self._suppliers_feeding(ref)
            total = sum(self.g.nodes[s].get("share", 0.0) for s in feeders) or 1e-9
            at_risk = sum(
                self.g.nodes[s].get("share", 0.0)
                for s in feeders if s in cut_suppliers
            )
            impact[ref] = round(at_risk / total, 4)
        return impact

    def _suppliers_feeding(self, refinery: str) -> List[str]:
        ref_grades = set(self.g.nodes[refinery].get("compatible_grades", []))
        feeders = []
        for sup in self.nodes_of_type(SUPPLIER):
            if self.g.nodes[sup].get("grade") in ref_grades:
                feeders.append(sup)
        return feeders

    # ------------------------------------------------------------------ #
    # Serialization for the frontend
    # ------------------------------------------------------------------ #
    def to_cytoscape(self) -> dict:
        nodes = [
            {"data": {"id": n, **{k: v for k, v in d.items() if not isinstance(v, list)}}}
            for n, d in self.g.nodes(data=True)
        ]
        edges = [
            {"data": {"source": u, "target": v, **d}}
            for u, v, d in self.g.edges(data=True)
        ]
        return {"nodes": nodes, "edges": edges}

    def stats(self) -> dict:
        return {
            "nodes": self.g.number_of_nodes(),
            "edges": self.g.number_of_edges(),
            "suppliers": len(self.nodes_of_type(SUPPLIER)),
            "corridors": len(self.nodes_of_type(CORRIDOR)),
            "refineries": len(self.nodes_of_type(REFINERY)),
            "reserves": len(self.nodes_of_type(RESERVE)),
        }


def build_world_graph() -> WorldEnergyGraph:
    """Construct the knowledge graph from seed data."""
    g = nx.DiGraph()

    g.add_node("commodity_crude", type=COMMODITY, name="Crude Oil")

    # Suppliers + their countries
    for s in sd.SUPPLIERS:
        g.add_node(
            s.id, type=SUPPLIER, name=s.name, country=s.country,
            share=s.share, grade=s.grade, via_hormuz=s.via_hormuz,
            reliability=s.reliability, lead_time_days=s.lead_time_days,
            spot_premium_usd=s.spot_premium_usd, lat=s.coords[0], lon=s.coords[1],
        )
        cid = f"country_{s.country.lower().replace(' ', '_')}"
        if cid not in g:
            g.add_node(cid, type=COUNTRY, name=s.country)
        g.add_edge(cid, s.id, rel="produces", dependency=s.share)

    # Corridors
    for c in sd.CORRIDORS:
        g.add_node(
            c.id, type=CORRIDOR, name=c.name, base_risk=c.base_risk,
            throughput=c.daily_throughput_mbpd,
        )

    # Supplier -> corridor (which chokepoint each supplier transits)
    for s in sd.SUPPLIERS:
        if s.via_hormuz:
            g.add_edge(s.id, "cor_hormuz", rel="transits", dependency=s.share)
        elif s.country in {"USA", "Nigeria", "Brazil"}:
            g.add_edge(s.id, "cor_atlantic", rel="transits", dependency=s.share)
        # Russia ships via multiple non-Hormuz routes; model as direct/flexible

    # Refineries (with grade compatibility)
    for r in sd.REFINERIES:
        g.add_node(
            r.id, type=REFINERY, name=r.name, capacity=r.capacity_mbpd,
            complexity=r.complexity, compatible_grades=r.compatible_grades,
            lat=r.coords[0], lon=r.coords[1],
        )
        # corridor -> refinery (everything Gulf-routed lands at west coast)
        g.add_edge("cor_hormuz", r.id, rel="delivers", dependency=0.4)
        g.add_edge("cor_atlantic", r.id, rel="delivers", dependency=0.2)
        # Russia direct feed
        g.add_edge("sup_ru", r.id, rel="supplies", dependency=0.36)

    # Reserves buffer refineries
    for rv in sd.RESERVES:
        g.add_node(
            rv.id, type=RESERVE, name=rv.name, capacity=rv.capacity_mmbbl,
            fill_pct=rv.fill_pct, lat=rv.coords[0], lon=rv.coords[1],
        )
        for r in sd.REFINERIES:
            g.add_edge(rv.id, r.id, rel="buffers", dependency=0.1)

    return WorldEnergyGraph(g)
