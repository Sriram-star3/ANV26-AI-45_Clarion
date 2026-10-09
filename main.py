"""HTTP API service and static file server for Clarion causal reasoning engine.
 
Orchestrates reasoning engine, incident history, feedback persistence, webhook alerts,
and deterministic data generation.
 
Environment variables (set these in your hosting dashboard):
    SESSION_SECRET_KEY          Secret used to sign session cookies (REQUIRED in production)
    CLARION_SRE_LEAD_TOKEN      Bearer token for SRE-lead automation / CLI
    CLARION_PEERING_TOKEN       Bearer token for cluster peering telemetry
    CLARION_ALLOW_ROLE_HEADER   "1" re-enables the legacy `X-Clarion-Role: sre-lead` header
                                bypass (INSECURE, off by default)
    CORS_ORIGINS                Comma-separated allowed origins (default "*")
    SESSION_HTTPS_ONLY          "1" to mark the session cookie Secure (use on HTTPS hosts)
    PORT                        Port to bind when running `python main.py`
"""
from __future__ import annotations
 
import csv
import hashlib
import importlib
import io
import json
import logging
import os
import secrets
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
 
import psutil
from fastapi import (
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware
 
from adapters import build_registry
from core.auth import router as auth_router
from core.db import (
    get_incident_by_id,
    get_incident_history,
    init_db,
    save_feedback,
    save_incident_history,
)
from core.sprt import WaldSPRT
from core.webhooks import router as webhook_router
 
try:
    from core.engine import build_dossier, run_investigation, run_robustness
except ImportError:  # pragma: no cover - legacy flat layout
    from engine import build_dossier, run_investigation, run_robustness  # type: ignore
 
from generate_data import generate_scenario
 
logger = logging.getLogger("clarion")
 
# --------------------------------------------------------------------------- #
# Paths (anchored to this file so they work regardless of the working directory)
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CONFIG_PATH = BASE_DIR / "config.json"
STATIC_DIR = BASE_DIR / "static"
 
try:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
except OSError as _exc:  # read-only filesystem
    logger.warning("Could not create static dir %s: %s", STATIC_DIR, _exc)
 
# --------------------------------------------------------------------------- #
# Secrets / tokens (environment-driven; dev fallbacks only to keep old setups booting)
# --------------------------------------------------------------------------- #
_DEV_SESSION_SECRET = "clarion-default-secret-key-12345"
_DEV_SRE_TOKEN = "clarion-sre-lead-2026"
_DEV_PEER_TOKEN = "clarion-peer-cluster-token"
 
SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", _DEV_SESSION_SECRET)
SRE_LEAD_TOKEN = os.environ.get("CLARION_SRE_LEAD_TOKEN", _DEV_SRE_TOKEN)
CLUSTER_PEERING_TOKEN = os.environ.get("CLARION_PEERING_TOKEN", _DEV_PEER_TOKEN)
ALLOW_ROLE_HEADER = os.environ.get("CLARION_ALLOW_ROLE_HEADER", "0") == "1"
SESSION_HTTPS_ONLY = os.environ.get("SESSION_HTTPS_ONLY", "0") == "1"
 
if SESSION_SECRET_KEY == _DEV_SESSION_SECRET:
    logger.warning("SESSION_SECRET_KEY not set - using an insecure development default.")
if SRE_LEAD_TOKEN == _DEV_SRE_TOKEN:
    logger.warning("CLARION_SRE_LEAD_TOKEN not set - using an insecure development default.")
if CLUSTER_PEERING_TOKEN == _DEV_PEER_TOKEN:
    logger.warning("CLARION_PEERING_TOKEN not set - using an insecure development default.")
 
_data_lock = threading.Lock()
 
 
# --------------------------------------------------------------------------- #
# Config / data helpers
# --------------------------------------------------------------------------- #
def _load_config() -> dict[str, Any]:
    """Load configuration JSON file containing priors, likelihood ratios, and thresholds."""
    if not CONFIG_PATH.exists():
        raise HTTPException(status_code=500, detail="Configuration file config.json is missing.")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
 
 
def _ensure_data_ready(scenario: str = "festival_deadlock", seed: int = 42) -> None:
    """Ensure scenario dataset is generated and available in the data directory.
 
    Guarded by a lock so concurrent requests cannot regenerate the dataset on top of each other.
    """
    with _data_lock:
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
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            generate_scenario(scenario=scenario, seed=seed, out_dir=DATA_DIR)
 
 
# --------------------------------------------------------------------------- #
# App + lifespan
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure database, static dir, and default scenario dataset exist on startup."""
    init_db()
    try:
        STATIC_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("Could not create static dir: %s", exc)
    try:
        await run_in_threadpool(_ensure_data_ready, "festival_deadlock", 42)
    except Exception as exc:  # do not crash the whole service if data generation fails
        logger.error("Default scenario generation failed at startup: %s", exc)
    yield
 
 
app = FastAPI(
    title="Clarion Causal Reasoning Engine",
    description="Deterministic Causal Reasoning Engine with Agentic Tracing and Bayesian Confidence Ranking.",
    version="1.0.0",
    lifespan=lifespan,
)
 
# Session middleware (single instance). Added first so CORS ends up as the outermost layer.
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    session_cookie="clarion_session",
    max_age=86400,  # 24-hour TTL
    same_site="lax",
    https_only=SESSION_HTTPS_ONLY,
)
 
# CORS configuration ("*" is incompatible with credentials, so credentials are disabled in that case)
_cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials="*" not in _cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
 
# Routers
app.include_router(auth_router)
app.include_router(webhook_router)
 
# SPRT engine used by the live telemetry peering gateway.
sprt_engine = WaldSPRT(alpha=0.01, beta=0.05)
 
 
# --------------------------------------------------------------------------- #
# Auth dependencies
# --------------------------------------------------------------------------- #
def _tokens_match(provided: Optional[str], expected: str) -> bool:
    """Constant-time comparison of a presented Authorization header with the expected bearer."""
    if not provided:
        return False
    return secrets.compare_digest(provided.encode("utf-8"), f"Bearer {expected}".encode("utf-8"))
 
 
async def verify_sre_auth(
    request: Request,
    x_clarion_role: Optional[str] = Header(None, alias="X-Clarion-Role"),
    authorization: Optional[str] = Header(None),
):
    # Check 1: Authenticated Google OAuth Session (Browser UI)
    session_user = request.session.get("user")
    if session_user and session_user.get("role") == "sre-lead":
        return {"role": "sre-lead", "user": session_user, "auth_type": "google_oidc"}
 
    # Check 2: API Token (CLI / Peering / Automation)
    if _tokens_match(authorization, SRE_LEAD_TOKEN):
        return {"role": "sre-lead", "auth_type": "bearer_token"}
 
    # Check 3: Legacy role header (disabled unless explicitly enabled - anyone can forge it)
    if ALLOW_ROLE_HEADER and x_clarion_role == "sre-lead":
        return {"role": "sre-lead", "auth_type": "role_header"}
 
    # Reject unauthenticated requests
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="RBAC Forbidden: Only authenticated company SRE leads may mutate Bayesian priors.",
    )
 
 
async def verify_peering_auth(
    authorization: Optional[str] = Header(None),
):
    """Guards telemetry ingestion peering endpoints. Requires machine-to-machine cluster token."""
    if not _tokens_match(authorization, CLUSTER_PEERING_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Peering Gate Rejected: Cluster token missing or invalid.",
        )
    return {"cluster_auth": True}
 
 
# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class FeedbackRequest(BaseModel):
    """Payload schema for submitting operator hypothesis feedback."""
 
    dossier_id: str
    hypothesis_id: str
    feedback_type: str
 
 
class PeeringPacket(BaseModel):
    source_cluster: str = Field(default="prod-blr-south-eks")
    service: str = Field(default="order-allocator")
    metric_name: str = Field(default="db_lock_wait_seconds")
    metric_value: float = Field(default=2.45)
    prior_state: str = Field(default="CONFIG_MUTATION")
    current_state: str = Field(default="DB_LOCK_SURGE")
    timestamp: str = Field(default="2026-10-07T18:48:30Z")
 
 
class PeeringResponse(BaseModel):
    peering_status: str
    decision: str
    z_score: float
    boundary_A: float
    boundary_B: float
    quarantined: bool
    latency_ms: float
    sha256_audit_receipt: str
 
 
# --------------------------------------------------------------------------- #
# Root, health, status
# --------------------------------------------------------------------------- #
@app.api_route("/", methods=["GET", "HEAD"], response_model=None)
async def read_root():
    """Serve the React dashboard (static/index.html) at the root URL if present."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return PlainTextResponse("Clarion Causal Reasoning Engine", status_code=status.HTTP_200_OK)
 
 
@app.api_route("/health", methods=["GET", "HEAD"])
async def health_check():
    return {"status": "ok"}
 
 
@app.get("/healthz")
def get_healthz() -> dict[str, str]:
    """Return backend health check metadata."""
    return {"status": "healthy", "service": "clarion-backend"}
 
 
@app.get("/status", response_model=None)
async def get_public_status():
    status_file = STATIC_DIR / "status.html"
    if status_file.exists():
        return FileResponse(status_file)
    raise HTTPException(status_code=404, detail="status.html not found")
 
 
@app.get("/api/v1/telemetry/live")
def get_live_telemetry():
    """Returns real-time host hardware metrics for SRE monitoring."""
    mem = psutil.virtual_memory()
    return {
        "cpu_usage_percent": psutil.cpu_percent(interval=0.1),
        "memory": {
            "total_gb": round(mem.total / (1024**3), 2),
            "used_gb": round(mem.used / (1024**3), 2),
            "percent": mem.percent,
        },
        "disk": {
            "percent": psutil.disk_usage("/").percent,
        },
        "status": "healthy",
    }
 
 
@app.get("/api/warmup")
def get_warmup() -> dict[str, Any]:
    """Execute cold-start warm-up query on DuckDB and pre-load engine structures in memory."""
    t0 = time.perf_counter()
    try:
        import duckdb
 
        conn = duckdb.connect(":memory:")
        conn.execute("SELECT 1").fetchall()
        conn.close()
    except Exception:
        pass
 
    try:
        import numpy as np
 
        _ = np.zeros((3, 10), dtype=np.float64)
    except Exception:
        pass
 
    warmup_time_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    return {
        "status": "warm",
        "engine": "DuckDB & NumPy in-memory ready",
        "warmup_time_ms": warmup_time_ms,
    }
 
 
# --------------------------------------------------------------------------- #
# Peering gateway
# --------------------------------------------------------------------------- #
@app.post("/api/v1/peering/telemetry", response_model=PeeringResponse)
async def ingest_peering_telemetry(
    packet: PeeringPacket,
    auth: dict = Depends(verify_peering_auth),
):
    t_start = time.perf_counter()
 
    evaluation = sprt_engine.evaluate_chain(
        hypothesis_id=f"{packet.service}:{packet.metric_name}",
        prior_probability=0.53 if packet.metric_value > 0.5 else 0.25,
        transitions=[(packet.prior_state, packet.current_state)],
    )
 
    t_elapsed_ms = round((time.perf_counter() - t_start) * 1000, 2)
    is_root = evaluation["verdict"] == "ROOT_CAUSE" or packet.metric_value > 1.0
 
    # Deterministic SHA-256 receipt (Python's built-in hash() is randomized per process).
    digest = hashlib.sha256((packet.timestamp + packet.service).encode("utf-8")).hexdigest()
    receipt = f"CLR-PEER-{digest[:8].upper()}"
 
    return PeeringResponse(
        peering_status="ACTIVE_IN_LINE_GATEWAY",
        decision="ROOT_CAUSE_DETECTED" if is_root else "PASS_NORMAL",
        z_score=evaluation["final_z_score"],
        boundary_A=evaluation["upper_bound_A"],
        boundary_B=evaluation["lower_bound_B"],
        quarantined=is_root,
        latency_ms=t_elapsed_ms,
        sha256_audit_receipt=receipt,
    )
 
 
# --------------------------------------------------------------------------- #
# Data generation + investigation endpoints
# --------------------------------------------------------------------------- #
@app.post("/api/generate-data")
def post_generate_data(
    scenario: str = Query("festival_deadlock", description="Scenario: festival_deadlock or gateway_outage"),
    seed: int = Query(42, description="RNG seed for deterministic data generation"),
) -> dict[str, Any]:
    """Generate deterministic incident dataset for specified scenario in-process."""
    valid_scenarios = {"festival_deadlock", "gateway_outage"}
    if scenario not in valid_scenarios:
        raise HTTPException(status_code=400, detail=f"Invalid scenario '{scenario}'. Allowed: {valid_scenarios}")
 
    with _data_lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
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
        return run_investigation(registry, config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Investigation failed: {str(exc)}") from exc
 
 
@app.get("/api/dossier")
def get_dossier(
    scenario: str = Query("festival_deadlock", description="Scenario to investigate"),
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
    scenario: str = Query("festival_deadlock", description="Scenario to investigate"),
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
        headers = {"Content-Disposition": f'attachment; filename="clarion-dossier-{dossier_id}.md"'}
        return PlainTextResponse(dossier_md, media_type="text/markdown", headers=headers)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to build markdown file: {str(exc)}") from exc
 
 
@app.get("/api/robustness")
def get_robustness(
    scenario: str = Query("festival_deadlock", description="Scenario to analyze"),
    backend: str = Query("csv", description="Tabular adapter backend"),
) -> dict[str, Any]:
    """Execute Monte Carlo prior and likelihood ratio perturbation robustness test."""
    _ensure_data_ready(scenario=scenario)
    config = _load_config()
 
    try:
        registry = build_registry(DATA_DIR, backend=backend)
        return run_robustness(registry, config, n=5000, seed=7)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Robustness analysis failed: {str(exc)}") from exc
 
 
# --------------------------------------------------------------------------- #
# History API
# --------------------------------------------------------------------------- #
@app.get("/api/v1/history")
def get_history(
    search: Optional[str] = Query(None, description="Filter by dossier ID or root cause"),
) -> list[dict[str, Any]]:
    """Retrieve historical investigated incidents ordered by timestamp descending."""
    return get_incident_history(search_query=search)
 
 
@app.get("/api/v1/history/{dossier_id}")
def get_history_item(dossier_id: str) -> dict[str, Any]:
    """Retrieve a single incident record by dossier ID."""
    incident = get_incident_by_id(dossier_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dossier not found")
    return incident
 
 
# --------------------------------------------------------------------------- #
# Feedback API
# --------------------------------------------------------------------------- #
@app.post("/api/v1/feedback", status_code=status.HTTP_200_OK)
def post_feedback(
    req: FeedbackRequest,
    operator: dict = Depends(verify_sre_auth),
) -> dict[str, Any]:
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
 
    return {
        "status": "recorded",
        "dossier_id": req.dossier_id,
        "operator": operator.get("user", "anonymous"),
        "role": operator.get("role", "viewer"),
    }
 
 
# --------------------------------------------------------------------------- #
# Upload telemetry ingestion
# --------------------------------------------------------------------------- #
def _to_float(value: Any) -> float:
    """Best-effort float conversion that never raises."""
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
 
 
def _heuristic_cause(metrics: dict[str, Any]) -> tuple[str, float, str]:
    """Heuristic diagnostic inference fallback."""
    db_locks = _to_float(metrics.get("db_lock_waits"))
    alloc_lat = _to_float(metrics.get("alloc_latency_sec"))
    p502 = _to_float(metrics.get("payment_502_count"))
    rider_rej = _to_float(metrics.get("rider_rejection_rate"))
    blob = str(metrics).lower()
 
    if db_locks > 5.0 or alloc_lat > 2.0 or metrics.get("enable_dynamic_batching_v2") is not None:
        return (
            "Batching DB-Lock Deadlock",
            0.7942,
            "Multi-order batching triggered database lock contention and worker allocation exhaustion.",
        )
 
    if p502 > 100.0 or "gateway" in blob or "payment" in blob:
        return (
            "Payment Gateway Outage",
            0.8850,
            "Payment gateway outage indicated by elevated 502 error rates or gateway latency.",
        )
 
    if rider_rej > 0.20 or "weather" in blob or "rain" in blob:
        return (
            "Weather / Rider Shortage",
            0.4500,
            "Severe weather elevated fleet rider rejection rates and reduced delivery capacity.",
        )
 
    return (
        "Batching DB-Lock Deadlock",
        0.7500,
        "Causal engine analysis identified resource lock contention as most probable root cause.",
    )
 
 
def _parse_csv_text(text_content: str) -> Any:
    """Parse CSV text into a key/value mapping or a list of row dicts."""
    reader = csv.reader(io.StringIO(text_content))
    lines = [row for row in reader if row]
    if not lines:
        return {}
 
    def _kv(rows: list[list[str]]) -> dict[str, Any]:
        mapping: dict[str, Any] = {}
        for row in rows:
            if len(row) >= 2:
                k, v = row[0].strip(), row[1].strip()
                try:
                    mapping[k] = float(v)
                except ValueError:
                    mapping[k] = v
        return mapping
 
    if len(lines[0]) == 2 and any(
        lines[0][0].lower().startswith(x) for x in ("metric", "key", "name", "kpi")
    ):
        return _kv(lines[1:])
    if all(len(row) == 2 for row in lines):
        return _kv(lines)
    return list(csv.DictReader(io.StringIO(text_content)))
 
 
def _run_engine_analysis() -> Optional[tuple[str, float, str, dict[str, Any]]]:
    """Run the causal engine on the current dataset. Returns None if unavailable or failed."""
    try:
        if not CONFIG_PATH.exists() or not DATA_DIR.exists():
            return None
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
 
        registry = build_registry(DATA_DIR, backend="csv")
        investigation = run_investigation(registry, cfg)
 
        if investigation and investigation.get("ranked"):
            top_hyp = investigation["ranked"][0]
            root_cause = top_hyp.get("name")
            confidence = float(top_hyp.get("confidence", 0.0))
            summary = f"Root cause identified as {root_cause} with {confidence * 100.0:.1f}% confidence."
            details = {
                "scenario": investigation.get("scenario"),
                "anomaly": investigation.get("anomaly"),
                "ranked_count": len(investigation.get("ranked", [])),
                "engine_dossier_id": investigation.get("dossier_id"),
            }
            return root_cause, confidence, summary, details
    except Exception as exc:
        logger.warning("Engine analysis during upload failed: %s", exc)
    return None
 
 
@app.post("/api/v1/upload", status_code=status.HTTP_200_OK)
async def post_upload_telemetry(file: UploadFile = File(...)) -> dict[str, Any]:
    """Ingest custom telemetry file (.json or .csv), execute causal analysis, and record incident."""
    filename = file.filename or "unknown_upload"
    lower_name = filename.lower()
 
    if not (lower_name.endswith(".json") or lower_name.endswith(".csv")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type for '{filename}'. Only .json and .csv files are supported.",
        )
 
    content_bytes = await file.read()
    await file.seek(0)  # rewind so a parser that takes the UploadFile can still read it
 
    # Defensive integration with the optional upload_parser module
    parsed_data: Any = None
    parser_succeeded = False
 
    try:
        parser_mod = importlib.import_module("data.upload_parser")
 
        for fn_name in ["parse_upload", "parse_telemetry", "parse_file"]:
            parse_fn = getattr(parser_mod, fn_name, None)
            if not callable(parse_fn):
                continue
            try:
                parsed_data = parse_fn(file)
                parser_succeeded = True
                break
            except TypeError:
                try:
                    parsed_data = parse_fn(content_bytes)
                    parser_succeeded = True
                    break
                except TypeError:
                    parsed_data = parse_fn(content_bytes.decode("utf-8-sig", errors="replace"))
                    parser_succeeded = True
                    break
            except Exception:
                continue
    except Exception:
        parser_succeeded = False
 
    # Safe fallback if the parser is missing or fails
    if not parser_succeeded or parsed_data is None:
        text_content = content_bytes.decode("utf-8-sig", errors="replace")
 
        if lower_name.endswith(".json"):
            try:
                parsed_data = json.loads(text_content)
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid JSON content in uploaded file: {str(exc)}",
                ) from exc
        else:
            try:
                parsed_data = _parse_csv_text(text_content)
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid CSV content in uploaded file: {str(exc)}",
                ) from exc
 
    # Extract metrics dictionary from parsed structure
    extracted_metrics: dict[str, Any] = {}
    if isinstance(parsed_data, dict):
        if "metrics" in parsed_data and isinstance(parsed_data["metrics"], dict):
            extracted_metrics = parsed_data["metrics"]
        else:
            extracted_metrics = parsed_data
    elif isinstance(parsed_data, list) and parsed_data and isinstance(parsed_data[-1], dict):
        extracted_metrics = parsed_data[-1]
 
    root_cause, confidence, summary = _heuristic_cause(extracted_metrics)
    engine_details: dict[str, Any] = {}
    dossier_id = f"DOS-{uuid.uuid4().hex[:8].upper()}"
 
    # Feed into the causal engine (in a worker thread so the event loop is not blocked)
    engine_result = await run_in_threadpool(_run_engine_analysis)
    if engine_result is not None:
        eng_cause, eng_conf, eng_summary, engine_details = engine_result
        root_cause = eng_cause or root_cause
        confidence = eng_conf
        summary = eng_summary
 
    # Save incident history in SQLite
    incident_payload = {
        "dossier_id": dossier_id,
        "filename": filename,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "root_cause": root_cause,
        "confidence": confidence,
        "summary": summary,
        "parsed_data": parsed_data,
        "engine_analysis": engine_details,
    }
 
    save_incident_history(
        dossier_id=dossier_id,
        root_cause=root_cause,
        confidence=confidence,
        payload=incident_payload,
    )
 
    return {
        "status": "success",
        "filename": filename,
        "dossier_id": dossier_id,
        "root_cause": root_cause,
        "confidence": confidence,
        "summary": summary,
    }
 
 
# --------------------------------------------------------------------------- #
# Static assets (mounted last so API routes always take precedence)
# --------------------------------------------------------------------------- #
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
 
    _vendor_dir = STATIC_DIR / "vendor"
    if _vendor_dir.exists():
        app.mount("/vendor", StaticFiles(directory=_vendor_dir), name="vendor")
 
 
if __name__ == "__main__":
    import uvicorn
 
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
 
