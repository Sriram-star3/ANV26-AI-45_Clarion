"""Automated test suite for Clarion Causal Reasoning Engine.

Asserts acceptance targets, determinism, backend equivalence across CSV and DuckDB,
Bayesian confidence bounds, signal suppression, robustness, and API endpoints.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import pytest
from starlette.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from adapters import build_registry
from engine import build_dossier, run_investigation, run_robustness
from generate_data import generate_scenario
from main import app


@pytest.fixture(scope="session")
def festival_data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate festival_deadlock scenario dataset in isolated temporary directory."""
    temp_dir = tmp_path_factory.mktemp("festival_data")
    generate_scenario(scenario="festival_deadlock", seed=42, out_dir=temp_dir)
    return temp_dir


@pytest.fixture(scope="session")
def gateway_data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate gateway_outage scenario dataset in isolated temporary directory."""
    temp_dir = tmp_path_factory.mktemp("gateway_data")
    generate_scenario(scenario="gateway_outage", seed=42, out_dir=temp_dir)
    return temp_dir


@pytest.fixture(scope="session")
def engine_config() -> dict:
    """Load engine config from workspace config.json."""
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)


def test_festival_deadlock_acceptance_targets(festival_data_dir: Path, engine_config: dict) -> None:
    """Verify all festival_deadlock mathematical targets and signal suppression."""
    reg = build_registry(festival_data_dir, backend="csv")
    result = run_investigation(reg, engine_config)

    # 1. Anomaly onset and drop %
    anomaly = result["anomaly"]
    assert "18:49" in anomaly["onset"], f"Expected onset at 18:49, got {anomaly['onset']}"
    assert 26.5 <= anomaly["drop_pct"] <= 30.5, f"Drop % {anomaly['drop_pct']} not in [26.5, 30.5]"

    # 2. Hypothesis rankings and Bayesian confidence
    ranked = result["ranked"]
    h_map = {r["id"]: r for r in ranked}

    # H3: Batching DB-Lock Deadlock
    assert ranked[0]["id"] == "H3", f"Expected H3 to be rank 1, got {ranked[0]['id']}"
    assert ranked[0]["verdict"] == "ROOT_CAUSE"
    assert 0.70 <= h_map["H3"]["confidence"] <= 0.85, f"H3 confidence {h_map['H3']['confidence']} not in [0.70, 0.85]"

    # H2: Weather/Rider Shortage
    assert 0.35 <= h_map["H2"]["confidence"] <= 0.55, f"H2 confidence {h_map['H2']['confidence']} not in [0.35, 0.55]"
    assert h_map["H2"]["verdict"] == "CONTRIBUTING"

    # H1: Payment Gateway Outage (Red herring suppressed)
    assert h_map["H1"]["confidence"] < 0.15, f"H1 confidence {h_map['H1']['confidence']} must be < 0.15"
    assert h_map["H1"]["verdict"] == "SUPPRESSED_NOISE"
    assert h_map["H1"]["recovered_pts"] < 1.5, f"H1 recovered_pts {h_map['H1']['recovered_pts']} must be < 1.5"

    # 3. Ground truth checks: capture success and polls after cancel
    cap_ev = next(e for e in h_map["H1"]["evidence"] if e["modality"] == "ledger_contradiction")
    assert cap_ev["lr"] == 0.25, f"Expected capture success LR 0.25, got {cap_ev['lr']}"

    poll_ev = next(e for e in h_map["H1"]["evidence"] if e["modality"] == "temporal_contradiction")
    assert poll_ev["lr"] == 0.50, f"Expected polls-after-cancel LR 0.50, got {poll_ev['lr']}"

    # 4. Naive alert metric
    naive = result["naive_alert"]
    assert naive["metric"] == "payment_502_count", f"Expected naive alert metric payment_502_count, got {naive['metric']}"
    assert naive["sigma"] > 50.0


def test_gateway_outage_acceptance_targets(gateway_data_dir: Path, engine_config: dict) -> None:
    """Verify gateway_outage negative control targets where H1 is root cause and H3 suppressed."""
    reg = build_registry(gateway_data_dir, backend="csv")
    result = run_investigation(reg, engine_config)

    ranked = result["ranked"]
    h_map = {r["id"]: r for r in ranked}

    # H1 must be rank 1 and ROOT_CAUSE
    assert ranked[0]["id"] == "H1", f"Expected H1 rank 1 in gateway_outage, got {ranked[0]['id']}"
    assert ranked[0]["verdict"] == "ROOT_CAUSE"
    assert ranked[0]["confidence"] > 0.80

    # H3 must be suppressed (< 0.15)
    assert h_map["H3"]["confidence"] < 0.15, f"H3 confidence {h_map['H3']['confidence']} must be < 0.15"
    assert h_map["H3"]["verdict"] == "SUPPRESSED_NOISE"


def test_backend_equivalence(festival_data_dir: Path, engine_config: dict) -> None:
    """Verify that CSV and DuckDB backends produce identical ranking and confidence results."""
    reg_csv = build_registry(festival_data_dir, backend="csv")
    reg_duck = build_registry(festival_data_dir, backend="duckdb")

    res_csv = run_investigation(reg_csv, engine_config)
    res_duck = run_investigation(reg_duck, engine_config)

    # Identical rankings and confidences
    csv_ranks = [(r["id"], r["confidence"], r["verdict"]) for r in res_csv["ranked"]]
    duck_ranks = [(r["id"], r["confidence"], r["verdict"]) for r in res_duck["ranked"]]
    assert csv_ranks == duck_ranks, f"Ranking mismatch between backends: {csv_ranks} vs {duck_ranks}"

    # Identical anomaly calculations
    assert res_csv["anomaly"]["drop_pct"] == res_duck["anomaly"]["drop_pct"]
    assert res_csv["anomaly"]["onset"] == res_duck["anomaly"]["onset"]
    assert res_csv["dossier_id"] == res_duck["dossier_id"], "Dossier IDs must be identical across backends"


def test_determinism_and_dossier_integrity(festival_data_dir: Path, engine_config: dict) -> None:
    """Verify that two separate runs on the same input produce identical dossier_id and fingerprints."""
    reg_1 = build_registry(festival_data_dir, backend="csv")
    res_1 = run_investigation(reg_1, engine_config)

    reg_2 = build_registry(festival_data_dir, backend="csv")
    res_2 = run_investigation(reg_2, engine_config)

    assert res_1["dossier_id"] == res_2["dossier_id"], "Dossier ID must be strictly deterministic"
    assert res_1["fingerprints"] == res_2["fingerprints"], "Fingerprints must match across runs"

    # Dossier markdown checks
    dossier_md = build_dossier(res_1)
    assert res_1["dossier_id"] in dossier_md
    for fp in res_1["fingerprints"].values():
        assert fp in dossier_md, f"Fingerprint {fp} missing from dossier markdown"
    assert "Executive Summary" in dossier_md
    assert "Method Statement" in dossier_md


def test_agent_trace_and_causal_graph(festival_data_dir: Path, engine_config: dict) -> None:
    """Verify agent trace events structure and causal graph completeness."""
    reg = build_registry(festival_data_dir, backend="csv")
    result = run_investigation(reg, engine_config)

    # Agent trace
    trace = result["trace"]
    assert len(trace) >= 12, f"Expected >= 12 trace steps, got {len(trace)}"
    for step in trace:
        assert "step" in step
        assert "hypothesis" in step
        assert "tool" in step
        assert "query" in step
        assert "result" in step
        assert step["result"] != "", "Step result should not be empty"
        assert "evidence_id" in step

    # Causal graph
    graph = result["graph"]
    assert len(graph["nodes"]) >= 10, f"Expected >= 10 nodes, got {len(graph['nodes'])}"
    assert len(graph["edges"]) >= 5, f"Expected >= 5 edges, got {len(graph['edges'])}"
    for node in graph["nodes"]:
        assert node["role"] in {"root", "anomaly", "noise", "refutes", "symptom", "operational"}
        assert node["polarity"] in {"supports", "refutes", "neutral"}


def test_monte_carlo_robustness(festival_data_dir: Path, engine_config: dict) -> None:
    """Verify robustness: true top cause holds in >= 95% of uniform +/- 30% perturbed runs."""
    reg = build_registry(festival_data_dir, backend="csv")
    rob = run_robustness(reg, engine_config, n=5000, seed=7)

    assert rob["n_runs"] == 5000
    assert rob["share_top_cause_holds"] >= 0.95, (
        f"Robustness share {rob['share_top_cause_holds']} fell below 0.95"
    )
    assert rob["target_met"] is True


def test_api_endpoints_smoke(monkeypatch: pytest.MonkeyPatch, festival_data_dir: Path) -> None:
    """Smoke test every API endpoint via TestClient."""
    # Point main.py DATA_DIR to test fixture directory
    monkeypatch.setattr("main.DATA_DIR", festival_data_dir)
    client = TestClient(app)

    # 1. Health
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

    # 2. Generate Data
    r = client.post("/api/generate-data?scenario=festival_deadlock&seed=42")
    assert r.status_code == 200
    assert r.json()["status"] == "success"

    # 3. Investigate CSV
    r = client.get("/api/investigate?scenario=festival_deadlock&backend=csv")
    assert r.status_code == 200
    res_json = r.json()
    assert "dossier_id" in res_json
    assert len(res_json["ranked"]) == 3

    # 4. Investigate DuckDB
    r = client.get("/api/investigate?scenario=festival_deadlock&backend=duckdb")
    assert r.status_code == 200
    assert r.json()["dossier_id"] == res_json["dossier_id"]

    # 5. Dossier JSON
    r = client.get("/api/dossier?scenario=festival_deadlock")
    assert r.status_code == 200
    assert "markdown" in r.json()

    # 6. Dossier Raw Markdown Download
    r = client.get("/api/dossier.md?scenario=festival_deadlock")
    assert r.status_code == 200
    assert "Clarion Causal Investigation Dossier" in r.text

    # 7. Robustness Endpoint
    r = client.get("/api/robustness?scenario=festival_deadlock")
    assert r.status_code == 200
    assert r.json()["target_met"] is True

    # 8. Static Web App Root
    r = client.get("/")
    assert r.status_code == 200
    assert "Clarion" in r.text
