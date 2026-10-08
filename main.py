"""HTTP API service and static file server for Clarion causal reasoning engine.

Orchestrates reasoning engine, incident history, feedback persistence, webhook alerts,
and deterministic data generation.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import json
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from adapters import build_registry
from core.db import get_incident_by_id, get_incident_history, init_db, save_feedback
from core.webhooks import router as webhook_router
from engine import build_dossier, run_investigation, run_robustness
from generate_data import generate_scenario

DATA_DIR = Path("data")
CONFIG_PATH = Path("config.json")
STATIC_DIR = Path("static")


class FeedbackRequest(BaseModel):
    """Payload schema for submitting operator hypothesis feedback."""

    dossier_id: str
    hypothesis_id: str
    feedback_type: str


def _load_config() -> dict[str, Any]:
    """Load configuration JSON file containing priors, likelihood ratios, and thresholds."""
    if not CONFIG_PATH.exists():
        raise HTTPException(status_code=500, detail="Configuration file config.json is missing.")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _ensure_data_ready(scenario: str = "festival_deadlock", seed: int = 42) -> None:
    """Ensure scenario dataset is generated and available in the data directory."""
    manifest_path = DATA_DIR / "manifest.json"
    needs_generation = False

    if not DATA_DIR.exists() or not manifest_path.exists():
        needs_generation = True
    else:
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            if manifest.get("scenario") != scenario:
                needs_generation = True
        except Exception:
            needs_generation = True

    if needs_generation:
        generate_scenario(scenario=scenario, seed=seed, out_dir=DATA_DIR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure database, static dir, and default scenario dataset exist on startup."""
    init_db()
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_data_ready(scenario="festival_deadlock", seed=42)
    yield


app = FastAPI(
    title="Clarion Causal Reasoning Engine",
    description="Deterministic Causal Reasoning Engine with Agentic Tracing and Bayesian Confidence Ranking.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include webhook routers
app.include_router(webhook_router)


@app.get("/healthz")
def get_healthz() -> dict[str, str]:
    """Return backend health check metadata."""
    return {"status": "healthy", "service": "clarion-backend"}


@app.get("/api/health")
def get_health() -> dict[str, str]:
    """Return service health status and version metadata."""
    return {"status": "ok", "service": "Clarion", "version": "1.0.0"}


@app.get("/", response_class=FileResponse)
def get_root() -> Response:
    """Serve frontend dashboard index.html at root if present."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return PlainTextResponse("Clarion Causal Reasoning Engine", status_code=status.HTTP_200_OK)


@app.post("/api/generate-data")
def post_generate_data(
    scenario: str = Query("festival_deadlock", description="Scenario: festival_deadlock or gateway_outage"),
    seed: int = Query(42, description="RNG seed for deterministic data generation"),
) -> dict[str, Any]:
    """Generate deterministic incident dataset for specified scenario in-process."""
    valid_scenarios = {"festival_deadlock", "gateway_outage"}
    if scenario not in valid_scenarios:
        raise HTTPException(status_code=400, detail=f"Invalid scenario '{scenario}'. Allowed: {valid_scenarios}")

    counts = generate_scenario(scenario=scenario, seed=seed, out_dir=DATA_DIR)
    return {
        "status": "success",
        "scenario": scenario,
        "seed": seed,
        "counts": counts,
    }


@app.get("/api/investigate")
def get_investigate(
    scenario: str = Query("festival_deadlock", description="Incident scenario to investigate"),
    backend: str = Query("csv", description="Tabular adapter backend: csv or duckdb"),
) -> dict[str, Any]:
    """Run full 7-step causal investigation pipeline and return result payload."""
    valid_backends = {"csv", "duckdb"}
    if backend.lower() not in valid_backends:
        raise HTTPException(status_code=400, detail=f"Invalid backend '{backend}'. Allowed: {valid_backends}")

    _ensure_data_ready(scenario=scenario)
    config = _load_config()

    try:
        registry = build_registry(DATA_DIR, backend=backend)
        result = run_investigation(registry, config)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Investigation failed: {str(exc)}") from exc


@app.get("/api/dossier")
def get_dossier(
    scenario: str = Query("festival_deadlock", description="Incident scenario to investigate"),
    backend: str = Query("csv", description="Tabular adapter backend"),
) -> dict[str, Any]:
    """Generate auditable incident dossier with markdown text and cryptographic digest."""
    _ensure_data_ready(scenario=scenario)
    config = _load_config()

    try:
        registry = build_registry(DATA_DIR, backend=backend)
        result = run_investigation(registry, config)
        dossier_md = build_dossier(result)
        return {
            "dossier_id": result.get("dossier_id"),
            "fingerprints": result.get("fingerprints"),
            "markdown": dossier_md,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate dossier: {str(exc)}") from exc


@app.get("/api/dossier.md")
def get_dossier_file(
    scenario: str = Query("festival_deadlock", description="Incident scenario to investigate"),
    backend: str = Query("csv", description="Tabular adapter backend"),
) -> Response:
    """Download auditable incident dossier as raw markdown document."""
    _ensure_data_ready(scenario=scenario)
    config = _load_config()

    try:
        registry = build_registry(DATA_DIR, backend=backend)
        result = run_investigation(registry, config)
        dossier_md = build_dossier(result)
        dossier_id = result.get("dossier_id", "audit")
        headers = {
            "Content-Disposition": f'attachment; filename="clarion-dossier-{dossier_id}.md"'
        }
        return PlainTextResponse(dossier_md, media_type="text/markdown", headers=headers)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to build markdown file: {str(exc)}") from exc


@app.get("/api/robustness")
def get_robustness(
    scenario: str = Query("festival_deadlock", description="Incident scenario to analyze"),
    backend: str = Query("csv", description="Tabular adapter backend"),
) -> dict[str, Any]:
    """Execute Monte Carlo prior and likelihood ratio perturbation robustness test."""
    _ensure_data_ready(scenario=scenario)
    config = _load_config()

    try:
        registry = build_registry(DATA_DIR, backend=backend)
        robustness_result = run_robustness(registry, config, n=5000, seed=7)
        return robustness_result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Robustness analysis failed: {str(exc)}") from exc


# History API endpoints
@app.get("/api/v1/history")
def get_history(search: Optional[str] = Query(None, description="Filter by dossier ID or root cause")) -> list[dict[str, Any]]:
    """Retrieve historical investigated incidents ordered by timestamp descending."""
    return get_incident_history(search_query=search)


@app.get("/api/v1/history/{dossier_id}")
def get_history_item(dossier_id: str) -> dict[str, Any]:
    """Retrieve a single incident record by dossier ID."""
    incident = get_incident_by_id(dossier_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dossier not found",
        )
    return incident


# Feedback API endpoint
@app.post("/api/v1/feedback", status_code=status.HTTP_200_OK)
def post_feedback(req: FeedbackRequest) -> dict[str, str]:
    """Record operator confirmation or rejection feedback for an incident hypothesis."""
    if req.feedback_type not in ["confirm", "reject"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid feedback_type '{req.feedback_type}'. Must be 'confirm' or 'reject'.",
        )
    save_feedback(
        dossier_id=req.dossier_id,
        hypothesis_id=req.hypothesis_id,
        feedback_type=req.feedback_type,
    )
    return {"status": "recorded", "dossier_id": req.dossier_id}


# Mount static assets
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    vendor_dir = STATIC_DIR / "vendor"
    if vendor_dir.exists():
        app.mount("/vendor", StaticFiles(directory=vendor_dir), name="vendor")
