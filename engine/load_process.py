import pandas as pd
import duckdb
import requests
import io
import time

# 1. Connect to DuckDB Database
con = duckdb.connect("telemetry.db")

# 2. Create Schema for Process Investigator Engine
con.execute("""
CREATE TABLE IF NOT EXISTS process_investigation_ledger (
    timestamp TIMESTAMP,
    case_id VARCHAR,
    activity_name VARCHAR,
    resource_id VARCHAR,
    duration_ms DOUBLE,
    status VARCHAR,
    is_anomaly BOOLEAN
)
""")

def fetch_and_ingest_process_data():
    # Example URL: Using a publicly accessible process log dataset
    url = "https://raw.githubusercontent.com/pm4py/pm4py-core/main/tests/compressed/running-example.csv"
    
    print("Downloading business process dataset...")
    response = requests.get(url)
    if response.status_code != 200:
        print("Failed to download dataset. Using fallback local structure.")
        return

    # Load CSV into Pandas
    df = pd.read_csv(io.StringIO(response.content.decode('utf-8')), sep=';')
    print(f"Loaded {len(df)} process activity records.")

    # Ingest directly into DuckDB
    for idx, row in df.iterrows():
        now = time.strftime('%Y-%m-%d %H:%M:%S')
        case_id = str(row.get('case:concept:name', f"CASE_{idx}"))
        activity = str(row.get('concept:name', 'Process Step'))
        resource = str(row.get('org:resource', 'Automated Engine'))
        
        # Calculate simulated duration or extract latency
        duration = float(row.get('duration', 150.0))
        status = "COMPLETED" if duration < 500 else "DEGRADED"
        is_anomaly = duration > 500

        con.execute(
            "INSERT INTO process_investigation_ledger VALUES (?, ?, ?, ?, ?, ?, ?)",
            [now, case_id, activity, resource, duration, status, is_anomaly]
        )
        print(f"[{now}] Process Ingested: Case={case_id} | Step={activity} | Latency={duration}ms")
        time.sleep(1) # Replay stream

if __name__ == "__main__":
    fetch_and_ingest_process_data()