# Clarion: Deterministic Causal Reasoning Engine with Agentic Tracing

> **100% Offline | Zero Hallucination Guarantee | Fully Reproducible Mathematical Inference**

Clarion is a deterministic causal reasoning engine designed for Site Reliability Engineers (SREs) and system architects. It investigates complex business anomalies across heterogeneous observational sources (telemetry, transaction ledgers, fleet logistics, support tickets, and system audit logs), systematically isolates and suppresses noisy red-herring symptoms using counterfactual reasoning, ranks candidate root causes via Bayesian likelihood fusion, and emits cryptographically fingerprinted, human-auditable incident dossiers.

---

## Key Capabilities & Architectural Principles

- **Zero Probabilistic Hallucination**: Operates purely on deterministic mathematics (likelihood ratios, Bayesian log-odds updating, counterfactual rate isolation, and DAG topological constraints). Contains no Large Language Models, no neural nets, and no external runtime network dependencies.
- **Counterfactual Signal Suppression**: Suppresses high-volume red-herring alarms (e.g. client-side payment polling 502 error spikes) by testing temporal ordering against cancellation events and verifying ground-truth banking switch success rates.
- **Agentic Execution Tracing**: Orchestrates structured hypothesis playbooks through a dedicated tool registry (`detect_onset`, `query_audit_log`, `check_temporal_order`, `ledger_query`, `ledger_counterfactual`, `search_tickets`, `fleet_query`), generating a live audit trail of analytical actions.
- **Dual Analytical Backends**: Supports both in-memory micro-batch CSV ingestion and DuckDB SQL pushdown queries with identical mathematical results and cryptographic dossiers.
- **Cryptographic Auditability**: SHA-256 fingerprinting across all raw evidence inputs, tied directly to an immutable Dossier ID.

---

## Directory Structure

```text
clarion/
├── config.json              # Priors, likelihood ratio constants, thresholds, ROI benchmarks
├── requirements.txt         # Permitted dependencies (fastapi, uvicorn, pandas, numpy, pytest, httpx, duckdb)
├── generate_data.py         # Deterministic multi-modal incident dataset generator
├── adapters.py              # BaseAdapter, CsvAdapter, DuckDBAdapter, build_registry()
├── engine.py                # 7-step pipeline, Bayesian reasoning, causal DAG, dossier, robustness
├── main.py                  # Thin FastAPI HTTP service and static file server
├── pytest.ini               # Test configuration
├── scripts/
│   └── setup_vendor.py      # Standard-library script downloading offline React 18 & Tailwind bundles
├── static/
│   ├── index.html           # Projector-readable dark-mode web dashboard
│   └── vendor/              # Offline vendor assets (react.js, react-dom.js, babel.js, tailwind.js)
├── tests/
│   └── test_engine.py       # Comprehensive pytest suite validating acceptance targets & determinism
└── data/                    # Generated scenario datasets (CSV files + manifest.json)
```

---

## Installation & Setup

Clarion runs on Python 3.10+ and is cross-platform (Windows, macOS, Linux).

### 1. Create and Activate Virtual Environment

```bash
# On Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1

# On macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Fetch Offline Web Assets

Run the standard-library vendor setup script to download and unpack React 18, Babel standalone, and Tailwind CSS into `static/vendor/`:

```bash
python scripts/setup_vendor.py
```
*Note: Once this one-time setup step completes, Clarion requires zero internet connectivity and operates completely offline.*

### 4. Generate Incident Data

```bash
# Generate primary incident scenario (festival_deadlock)
python generate_data.py --scenario festival_deadlock --seed 42 --out data

# Or generate negative control scenario (gateway_outage)
python generate_data.py --scenario gateway_outage --seed 42 --out data
```

---

## Running the Application

Start the local server using Uvicorn:

```bash
python -m uvicorn main:app --port 8000
```

Open your browser to:
[http://localhost:8000](http://localhost:8000)

---

## Running the Automated Test Suite

Clarion includes a rigorous test suite validating all mathematical acceptance targets, confidence bounds, backend equivalence, determinism, and API endpoints:

```bash
pytest -q
```

---

## Interactive Demo Walkthrough

1. **Anomaly Injection**:
   - On the web dashboard, select `festival_deadlock (DB-Lock Issue)` and click **Inject Anomaly**.
2. **Phase 1: Naive Alert Board (~3s)**:
   - A critical red alert flashes displaying the naive symptom alert: `Payment Gateway 502 Surge detected (+223.0σ anomaly)`. This models standard threshold monitoring firing on high-volume symptoms.
3. **Phase 2: Agentic Trace & DAG Construction**:
   - The engine streams analytical checks step-by-step in the terminal panel, validating onset timestamps, querying audit logs, executing counterfactual simulations, and testing banking capture rates.
   - Concurrently, the interactive causal DAG lights up node-by-node.
4. **Phase 3: Causal Verdict & Split View**:
   - **Red Herring Box**: `Payment Gateway Outage` is suppressed to `0.065` confidence (`SUPPRESSED_NOISE`) because UPI capture success remained at `98.6%`, 502 errors post-dated order cancellation, and counterfactual share was `< 0.5%`.
   - **Root Cause Box**: `Batching DB-Lock Deadlock` is elevated to `0.794` confidence (`ROOT_CAUSE`) because configuration flag `enable_dynamic_batching_v2` preceded onset by 4 minutes, DB lock waits and allocation latency surged, and counterfactual isolation proves it accounts for `88%` of excess cancellations.
5. **Phase 4: Audit Dossier Export**:
   - Click **Export Clarion Audit Report**.
   - Review the complete markdown report with input SHA-256 fingerprints, or click **Print / Save PDF** or **Download .md**.

---

## Evidence & Result Schemas

### 1. Evidence Item Schema

Each verification rule evaluated during the investigation emits an evidence item:

```json
{
  "id": "EV-H1-04",
  "hypothesis": "H1",
  "text": "UPI capture success remains high at 98.6% (>= 95%), refuting gateway outage",
  "modality": "ledger_contradiction",
  "lr": 0.25
}
```

- `id`: Unique identifier formatted as `EV-<HYPOTHESIS_ID>-<STEP_NUM>`.
- `hypothesis`: Target hypothesis key (`H1`, `H2`, `H3`).
- `text`: Human-readable factual observation computed from underlying data.
- `modality`: Diagnostic channel (`telemetry`, `audit`, `tickets`, `fleet`, `temporal`, `counterfactual`, `ledger_contradiction`, `temporal_contradiction`).
- `lr`: Multiplicative likelihood ratio applied to the hypothesis odds ($LR > 1.0$ supports, $LR < 1.0$ refutes).

### 2. Investigation Result JSON Schema

`GET /api/investigate?scenario=festival_deadlock&backend=csv` returns:

```json
{
  "engine": "Clarion Deterministic Causal Reasoning Engine v1.0",
  "scenario": "festival_deadlock",
  "dossier_id": "cd4687d83f5236eb",
  "anomaly": {
    "drop_pct": 28.44,
    "baseline": 0.946,
    "incident": 0.677,
    "onset": "2026-10-07 18:49:00",
    "window": {
      "baseline": "18:30-18:44",
      "incident": "18:49-21:30"
    }
  },
  "naive_alert": {
    "metric": "payment_502_count",
    "label": "Payment Gateway 502 Surge",
    "sigma": 223.0,
    "onset": "2026-10-07 18:50:00",
    "severity": "CRITICAL"
  },
  "ranked": [
    {
      "id": "H3",
      "name": "Batching DB-Lock Deadlock",
      "confidence": 0.7942,
      "prior": 0.20,
      "verdict": "ROOT_CAUSE",
      "explained_share": 0.8804,
      "recovered_pts": 23.84,
      "evidence": [...]
    },
    ...
  ],
  "trace": [
    {
      "step": 1,
      "hypothesis": "H1",
      "tool": "detect_onset",
      "query": {"metric": "payment_502_count"},
      "result": "Breach detected at 2026-10-07 18:50:00 (baseline mean: 1.93, std: 0.46)",
      "evidence_id": "EV-H1-01"
    },
    ...
  ],
  "graph": {
    "nodes": [
      {
        "id": "node_config_batching",
        "label": "Dynamic Batching v2 Enabled",
        "ts": "2026-10-07 18:45:00",
        "source": "audit",
        "entity": "ops-automation",
        "polarity": "supports",
        "role": "root",
        "detail": "Batch size ceiling raised to 5-6 without row-level lock sharding"
      },
      ...
    ],
    "edges": [
      {"src": "node_config_batching", "dst": "node_db_locks", "type": "causes"},
      ...
    ]
  },
  "remediation": [
    {
      "priority": 1,
      "action": "Roll back dynamic multi-order batching feature flag",
      "target": "enable_dynamic_batching_v2=false",
      "advisory": "Advisory only - requires human SRE approval before execution"
    },
    ...
  ],
  "roi": {
    "manual_s": 16200,
    "e2e_s": 90,
    "reduction_pct": 99.44,
    "compute_ms": 42.15,
    "note": "both MTTR figures are assumptions from config.json; measured compute time: shown above"
  },
  "fingerprints": {
    "telemetry": "3a18e0...",
    "ledger": "57b112...",
    "fleet": "9cf14e...",
    "tickets": "b723a1...",
    "audit": "a190ef..."
  }
}
```

---

## How to Extend Clarion

Clarion uses strict module contracts to enable parallel development across data sources, reasoning logic, and user interfaces.

### 1. Adding a New Data Adapter

1. Open `adapters.py`.
2. Subclass `BaseAdapter` and implement:
   - `load() -> pd.DataFrame`: return DataFrame with a timezone-naive `ts` datetime column.
   - `fingerprint() -> str`: return a deterministic SHA-256 hash string of the data payload.
3. Update `build_registry(data_dir, backend)` to map the new adapter key.

```python
class ParquetAdapter(BaseAdapter):
    """Adapter loading local Parquet files."""

    def __init__(self, filename: Path | str, name: str) -> None:
        super().__init__(name)
        self.path = Path(filename)

    def load(self) -> pd.DataFrame:
        df = pd.read_parquet(self.path)
        df["ts"] = pd.to_datetime(df["ts"]).dt.tz_localize(None)
        return df

    def fingerprint(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()
```

### 2. Adding a New Hypothesis

1. Add the hypothesis configuration to `config.json` under `hypotheses`:
   ```json
   "H4": {
     "name": "Third-Party Inventory Sync Failure",
     "cancel_reason": "STOCKOUT",
     "playbook": [
       {"tool": "detect_onset", "query": {"metric": "stockout_rate"}},
       {"tool": "search_tickets", "query": {"pattern": "out of stock|unavailable"}},
       {"tool": "ledger_counterfactual", "query": {"hypothesis": "H4"}}
     ]
   }
   ```
2. Set the prior in `config.json` under `priors`: `"H4": 0.15`.
3. Add likelihood ratio rules under `lr_rules.H4`.

### 3. Adding a New Diagnostic Tool

1. In `engine.py`, add the tool handler inside `_execute_agent_trace`:
   ```python
   elif tool == "check_disk_io":
       disk_metric = q["metric"]
       # Evaluate condition deterministically
       ...
       result_str = f"Disk IOPS {disk_metric} stayed normal"
   ```
2. Reference the new tool in any hypothesis playbook in `config.json`.

### 4. Adding a New UI Panel

1. Open `static/index.html`.
2. Add a React component or section within `ClarionApp`.
3. Style using standard Tailwind CSS classes.
4. Ensure no external web resources or network fonts are imported.

---

## Method Statement & Honesty Guarantees

- **No Learning / No LLMs**: Clarion contains no hidden neural networks, LLMs, or stochastic weights.
- **Assumed Benchmark Notice**: All MTTR figures (Manual MTTR 4.5 h, Clarion E2E 90 s) are explicitly labeled as benchmark assumptions defined in `config.json`. The compute time (e.g. ~40 ms) is locally measured on every request.
- **Deterministic Reproducibility**: Given the same input data files, Clarion produces the exact same rankings, confidences, evidence items, and Dossier ID on any machine.
