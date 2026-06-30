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
from geos.api.copilot import Copilot
from geos.data import seed_data as sd
from geos.data.events import list_events
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
ORCH = SupervisorOrchestrator()
COPILOT = Copilot(ORCH)
SIM = WarGameSimulator()

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
