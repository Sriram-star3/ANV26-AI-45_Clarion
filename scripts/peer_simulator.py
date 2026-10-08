import json
import time
import sys
from pathlib import Path
from datetime import datetime

try:
    import httpx
except ImportError:
    print("[!] httpx is not installed. Run: pip install httpx")
    sys.exit(1)

BASE_URL = "http://localhost:8000"
TELEMETRY_ENDPOINT = f"{BASE_URL}/api/v1/peering/telemetry"
ALERT_ENDPOINT = f"{BASE_URL}/api/v1/webhook/alert"

# Built-in fallback so the script NEVER crashes if the file is missing
FALLBACK_SCENARIO = {
    "scenario_id": "scenario_3",
    "title": "Redis Cache Eviction Surge causing Darkstore Inventory Stockouts",
    "metadata": {
        "severity": "CRITICAL",
        "affected_services": ["redis-cache-cluster", "inventory-service", "order-dispatch"],
        "time_window": "2026-10-08T14:00:00Z to 2026-10-08T15:30:00Z"
    },
    "telemetry": [
        {"timestamp": "2026-10-08T14:05:00Z", "metric_name": "redis_memory_usage_ratio", "value": 0.96, "event_type": "threshold_breach"},
        {"timestamp": "2026-10-08T14:10:00Z", "metric_name": "evicted_keys_per_second", "value": 14200.0, "event_type": "spike"},
        {"timestamp": "2026-10-08T14:15:00Z", "metric_name": "inventory_db_connection_pool_saturation", "value": 99.4, "event_type": "exhaustion"},
        {"timestamp": "2026-10-08T14:20:00Z", "metric_name": "darkstore_stockout_order_reject_rate", "value": 38.7, "event_type": "incident_impact"}
    ],
    "audit_logs": [
        {"timestamp": "2026-10-08T14:02:11Z", "service": "cache-manager", "level": "WARN", "message": "Memory limit reached on redis-node-03; maxmemory-policy volatile-lru active."},
        {"timestamp": "2026-10-08T14:08:45Z", "service": "inventory-sync", "level": "ERROR", "message": "Cache miss storm on key 'store_084:item_catalog'; falling back to direct Postgres read replica."},
        {"timestamp": "2026-10-08T14:18:22Z", "service": "dispatch-router", "level": "CRITICAL", "message": "Stock reconciliation failure for Darkstore DS-BLR-04: reserved items unavailable on physical shelf."}
    ]
}


def find_scenario_file() -> Path | None:
    # 1. Check common relative locations
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent

    search_candidates = [
        project_root / "data" / "scenario_3.json",
        project_root / "data" / "scenarips" / "scenario_3.json",
        project_root / "scenario_3.json",
        current_dir / "scenario_3.json"
    ]

    for path in search_candidates:
        if path.is_file() and path.stat().st_size > 0:
            return path

    # 2. Dynamic recursive search across the project root
    for matched_file in project_root.rglob("*scenario_3*.json"):
        if matched_file.is_file() and matched_file.stat().st_size > 0:
            return matched_file

    return None


def run_simulation(interval: float = 0.8):
    target_file = find_scenario_file()

    if target_file:
        print(f"[LOADED] Using scenario file: {target_file}")
        with open(target_file, "r", encoding="utf-8") as f:
            scenario = json.load(f)
    else:
        print("[NOTICE] scenario_3.json not found on disk. Falling back to built-in scenario payload.")
        scenario = FALLBACK_SCENARIO

    scenario_id = scenario.get("scenario_id", "scenario_3")
    title = scenario.get("title", "Telemetry Simulation")
    telemetry_events = scenario.get("telemetry", [])
    audit_logs = scenario.get("audit_logs", [])

    print("=" * 68)
    print("CLARION PEERING EMITTER - LIVE SIMULATION")
    print(f"Scenario ID : {scenario_id}")
    print(f"Title       : {title}")
    print(f"Severity    : {scenario.get('metadata', {}).get('severity', 'UNKNOWN')}")
    print(f"Target      : {BASE_URL}")
    print("=" * 68)

    client = httpx.Client(timeout=5.0)

    # 1. Stream Telemetry metric batches
    print("\n[Phase 1] Streaming Telemetry Metric Batches...")
    for idx, item in enumerate(telemetry_events, start=1):
        payload = {
            "scenario_id": scenario_id,
            "stream_type": "telemetry",
            "index": idx,
            "emitted_at": datetime.utcnow().isoformat() + "Z",
            "metric_name": item.get("metric_name"),
            "value": item.get("value"),
            "event_type": item.get("event_type"),
            "original_timestamp": item.get("timestamp")
        }

        try:
            res = client.post(TELEMETRY_ENDPOINT, json=payload)
            tag = f"[{res.status_code} OK]" if res.status_code < 400 else f"[{res.status_code} ERR]"
            print(f" {tag} Metric {idx}/{len(telemetry_events)} -> {item.get('metric_name')} = {item.get('value')} ({item.get('event_type')})")
        except httpx.ConnectError:
            print(f" [CONNECT_FAIL] Could not reach {TELEMETRY_ENDPOINT}. Is Clarion running on port 8000?")
        except Exception as e:
            print(f" [ERROR] {e}")

        time.sleep(interval)

    # 2. Stream Audit Logs / Alerts
    print("\n[Phase 2] Emitting Critical Audit Alerts...")
    for idx, log in enumerate(audit_logs, start=1):
        payload = {
            "scenario_id": scenario_id,
            "stream_type": "alert",
            "index": idx,
            "service": log.get("service"),
            "level": log.get("level"),
            "message": log.get("message"),
            "original_timestamp": log.get("timestamp")
        }

        try:
            res = client.post(ALERT_ENDPOINT, json=payload)
            tag = f"[{res.status_code} OK]" if res.status_code < 400 else f"[{res.status_code} ERR]"
            print(f" {tag} Alert {idx}/{len(audit_logs)} [{log.get('level')}] {log.get('service')}: {log.get('message')[:50]}...")
        except httpx.ConnectError:
            print(f" [CONNECT_FAIL] Could not reach {ALERT_ENDPOINT}")
        except Exception as e:
            print(f" [ERROR] {e}")

        time.sleep(interval)

    print("\n" + "=" * 68)
    print("Simulation finished: All batches streamed into Clarion.")
    print("=" * 68)


if __name__ == "__main__":
    run_simulation()