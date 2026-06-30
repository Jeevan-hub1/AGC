"""Agent base classes and the shared Blackboard.

GEOS uses a *blackboard* multi-agent pattern: a supervisor activates
specialist agents in dependency order; each reads the shared blackboard,
contributes its analysis, and writes structured findings back. This keeps
agents decoupled (no point-to-point messaging), avoids deadlocks/loops, and
makes the whole reasoning chain auditable - every agent emits an explainable
``AgentReport`` with a confidence score.

The design maps cleanly onto LangGraph / CrewAI / AutoGen for production; here
it is implemented dependency-free so the demo is deterministic and fast.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class AgentReport:
    agent: str
    headline: str
    confidence: float                       # 0-1
    findings: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "agent": self.agent,
            "headline": self.headline,
            "confidence": round(self.confidence, 3),
            "findings": self.findings,
            "recommendations": self.recommendations,
            "elapsed_ms": round(self.elapsed_ms, 2),
        }


class Blackboard:
    """Shared, append-only working memory for the agent swarm."""

    def __init__(self, context: Dict[str, Any] | None = None) -> None:
        self.context: Dict[str, Any] = context or {}
        self.reports: List[AgentReport] = []

    def write(self, key: str, value: Any) -> None:
        self.context[key] = value

    def read(self, key: str, default: Any = None) -> Any:
        return self.context.get(key, default)

    def post(self, report: AgentReport) -> None:
        self.reports.append(report)


class Agent:
    """Base specialist agent. Subclasses implement ``analyze``."""

    name: str = "agent"
    role: str = "generic"
    depends_on: List[str] = []

    def analyze(self, board: Blackboard) -> AgentReport:  # pragma: no cover
        raise NotImplementedError

    def run(self, board: Blackboard) -> AgentReport:
        start = time.perf_counter()
        report = self.analyze(board)
        report.elapsed_ms = (time.perf_counter() - start) * 1000
        board.write(self.name, report.findings)
        board.post(report)
        return report
