"""HTTP API service and static file server for Clarion causal reasoning engine.

Thin FastAPI application wiring HTTP endpoints to adapters, reasoning engine,
and deterministic data generation.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from adapters import build_registry
from engine import build_dossier, run_investigation, run_robustness
from generate_data import generate_scenario

DATA_DIR = Path("data")
CONFIG_PATH = Path("config.json")
STATIC_DIR = Path("static")


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
    """Ensure data directory and default festival_deadlock scenario exist on startup."""
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_data_ready(scenario="festival_deadlock", seed=42)
    yield


app = FastAPI(
    title="Clarion Causal Reasoning Engine",
    description="Deterministic Causal Reasoning Engine with Agentic Tracing and Bayesian Confidence Ranking.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/api/health")
def get_health() -> dict[str, str]:
    """Return service health status and version metadata."""
    return {"status": "ok", "service": "Clarion", "version": "1.0.0"}


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


# Serve static web dashboard
if not STATIC_DIR.exists():
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
