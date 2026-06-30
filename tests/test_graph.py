"""Unit tests for the World Energy Knowledge Graph."""

import pytest

from geos.knowledge_graph import build_world_graph


@pytest.fixture
def graph():
    return build_world_graph()


def test_graph_structure(graph):
    stats = graph.stats()
    assert stats["suppliers"] == 8
    assert stats["refineries"] == 5
    assert stats["reserves"] == 3
    assert stats["nodes"] > stats["suppliers"]


def test_no_disruption_no_risk(graph):
    impact = graph.cascade()
    assert all(v == 0.0 for v in impact.values())


def test_hormuz_cascade_raises_risk(graph):
    impact = graph.cascade(disrupted_corridors=["cor_hormuz"])
    assert any(v > 0 for v in impact.values())
    assert all(0.0 <= v <= 1.0 for v in impact.values())


def test_vulnerability_ranking(graph):
    vuln = graph.systemic_vulnerability()
    assert len(vuln) > 0
    scores = list(vuln.values())
    assert scores == sorted(scores, reverse=True)


def test_cytoscape_serialization(graph):
    cy = graph.to_cytoscape()
    assert "nodes" in cy and "edges" in cy
    assert len(cy["nodes"]) == graph.stats()["nodes"]
