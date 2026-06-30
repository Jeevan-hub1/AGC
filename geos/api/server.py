"""FastAPI application for Project Phoenix / GEOS.

Exposes the engines behind a clean REST API and serves the command-center SPA.
The orchestrator and knowledge graph are built once at startup and reused, so
every request is fast and the demo never stalls.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from geos import __version__, config
from geos.agents import SupervisorOrchestrator
from geos.analytics import DetectionBenchmark
from geos.api.copilot import Copilot
from geos.data import seed_data as sd
from geos.data.events import get_event, list_events
from geos.data.live_feed import get_feed
from geos.ml import GNNCascade, get_risk_model
from geos.optim import ProcurementGame, ReserveDP
from geos.scenario import WarGameSimulator

app = FastAPI(
    title="Project Phoenix - GEOS",
    description="Autonomous Geopolitical Energy Operating System for India",
    version=__version__,
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# --- shared singletons (built once) ---
# Use the live market Brent price as the dynamic model baseline when available,
# so scenarios project from *today's* real price. Falls back to config baseline.
try:
    _LIVE = get_feed().get()
    _LIVE_BRENT = _LIVE.prices.get("brent") if _LIVE.source != "fallback" else None
except Exception:
    _LIVE_BRENT = None

ORCH = SupervisorOrchestrator(baseline_brent=_LIVE_BRENT)
COPILOT = Copilot(ORCH)
SIM = WarGameSimulator()
BENCH = DetectionBenchmark()

# Warm the ML foundation model at import so the first request is fast.
try:
    get_risk_model()
except Exception:  # pragma: no cover - never block startup on warmup
    pass

WEB_DIR = Path(__file__).resolve().parents[2] / "web"


# ------------------------------------------------------------------ #
# Request models
# ------------------------------------------------------------------ #
class ScenarioRequest(BaseModel):
    event_id: str = Field(..., examples=["hormuz_partial"])
    sim_runs: Optional[int] = Field(None, ge=100, le=50000)


class BlackSwanRequest(BaseModel):
    event_ids: List[str] = Field(..., min_length=2)
    sim_runs: Optional[int] = Field(None, ge=100, le=50000)


class CopilotRequest(BaseModel):
    question: str = Field(..., min_length=3)


# ------------------------------------------------------------------ #
# API routes
# ------------------------------------------------------------------ #
@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "agents": len(ORCH.pipeline)}


@app.get("/api/events")
def events() -> dict:
    return {"events": list_events()}


@app.get("/api/agents")
def agents() -> dict:
    return {"roster": ORCH.roster()}


@app.get("/api/neri/baseline")
def neri_baseline() -> dict:
    return ORCH.neri.compute().to_dict()


@app.get("/api/worldmodel")
def world_model() -> dict:
    """Geospatial + structural snapshot for the map and digital twin."""
    return {
        "center": sd.INDIA_CENTER,
        "suppliers": [
            {"id": s.id, "name": s.name, "country": s.country, "coords": s.coords,
             "share": s.share, "grade": s.grade, "via_hormuz": s.via_hormuz,
             "reliability": s.reliability, "lead_time_days": s.lead_time_days}
            for s in sd.SUPPLIERS
        ],
        "corridors": [
            {"id": c.id, "name": c.name, "waypoints": c.waypoints,
             "base_risk": c.base_risk, "throughput": c.daily_throughput_mbpd}
            for c in sd.CORRIDORS
        ],
        "refineries": [
            {"id": r.id, "name": r.name, "coords": r.coords,
             "capacity": r.capacity_mbpd, "grades": r.compatible_grades}
            for r in sd.REFINERIES
        ],
        "reserves": [
            {"id": r.id, "name": r.name, "coords": r.coords,
             "capacity": r.capacity_mmbbl, "fill_pct": r.fill_pct}
            for r in sd.RESERVES
        ],
        "graph_stats": ORCH.graph.stats(),
    }


@app.get("/api/graph")
def graph() -> dict:
    return ORCH.graph.to_cytoscape()


@app.get("/api/graph/vulnerability")
def vulnerability() -> dict:
    vuln = ORCH.graph.systemic_vulnerability()
    return {"vulnerability": [
        {"node": ORCH.graph.node_attrs(n).get("name", n), "score": round(v, 4)}
        for n, v in list(vuln.items())[:10]
    ]}


@app.post("/api/scenario")
def scenario(req: ScenarioRequest) -> dict:
    """The headline endpoint: inject an event, get a full national response."""
    try:
        return ORCH.respond_to_id(req.event_id, sim_runs=req.sim_runs)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/blackswan")
def black_swan(req: BlackSwanRequest) -> dict:
    try:
        return ORCH.respond_black_swan(req.event_ids, sim_runs=req.sim_runs)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/copilot")
def copilot(req: CopilotRequest) -> dict:
    return COPILOT.ask(req.question)


# ------------------------------------------------------------------ #
# Advanced ML / optimization endpoints
# ------------------------------------------------------------------ #
@app.get("/api/forecast")
def forecast(event_id: Optional[str] = None) -> dict:
    """Geopolitical Risk Foundation Model: per-corridor disruption forecast."""
    model = get_risk_model()
    event = get_event(event_id) if event_id else None
    preds = model.predict_corridors(event)
    return {
        "model_auc": round(model.auc_, 3),
        "feature_importance": model.feature_importance(),
        "corridor_forecast": [p.to_dict() for p in preds],
    }


@app.get("/api/gnn-cascade")
def gnn_cascade(event_id: Optional[str] = None) -> dict:
    """GNN attention message-passing cascade over the knowledge graph."""
    gnn = GNNCascade(ORCH.graph)
    if event_id:
        ev = get_event(event_id)
        return gnn.cascade(disrupted_suppliers=ev.affected_suppliers,
                           disrupted_corridors=ev.affected_corridors)
    return gnn.cascade(disrupted_corridors=["cor_hormuz"])


@app.post("/api/equilibrium")
def equilibrium(req: ScenarioRequest) -> dict:
    """Cournot-Nash spot-price equilibrium for the event's shortfall."""
    ev = get_event(req.event_id)
    disrupted = list(ev.affected_suppliers)
    if "cor_hormuz" in ev.affected_corridors and ev.hormuz_closure_prob > 0.4:
        disrupted += [s.id for s in sd.SUPPLIERS if s.via_hormuz]
    shortfall = sum(s.share for s in sd.SUPPLIERS if s.id in set(disrupted)) \
        * max(ev.hormuz_closure_prob, 0.5) * config.DAILY_CRUDE_DEMAND_MBPD
    return ProcurementGame().solve(
        disrupted_ids=list(set(disrupted)), shortfall_mbpd=shortfall).to_dict()


@app.post("/api/reserve/optimize")
def reserve_optimize(req: ScenarioRequest) -> dict:
    """DP-optimal SPR drawdown schedule (finite-horizon MDP)."""
    available = sum(r.capacity_mmbbl * r.fill_pct for r in sd.RESERVES)
    ev = get_event(req.event_id)
    daily_gap = ev.hormuz_closure_prob * config.HORMUZ_TRANSIT_SHARE * 0.5 \
        * config.DAILY_CRUDE_DEMAND_MBPD
    return ReserveDP(total_reserve_mmbbl=available, horizon_days=30).solve(
        daily_gap_mmbbl=max(0.1, daily_gap)).to_dict()


@app.get("/api/livefeed")
def livefeed(force: bool = False) -> dict:
    """Live market data (Brent/WTI/NatGas/USD-INR) with cache + fallback."""
    snap = get_feed().get(force=force)
    return {**snap.to_dict(), "model_baseline_brent": ORCH.causal.baseline_brent}


@app.get("/api/benchmark")
def benchmark(episodes: int = 600) -> dict:
    """PHOENIX compound detection vs single-sensor baseline metrics."""
    episodes = max(100, min(episodes, 5000))
    return BENCH.run(episodes=episodes).to_dict()


# ------------------------------------------------------------------ #
# Static command-center SPA
# ------------------------------------------------------------------ #
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(str(WEB_DIR / "index.html"))


def main() -> None:  # pragma: no cover
    import uvicorn
    uvicorn.run("geos.api.server:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":  # pragma: no cover
    main()
