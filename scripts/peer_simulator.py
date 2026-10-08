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

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "scenario_3.json"


def run_simulation(interval: float = 0.8):
    if not DATA_PATH.exists():
        print(f"[ERROR] Could not find scenario file at: {DATA_PATH}")
        sys.exit(1)

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        scenario = json.load(f)

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