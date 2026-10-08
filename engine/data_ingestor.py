import os
import time
import pandas as pd
import duckdb

def stream_real_dataset(csv_filepath: str, playback_speed_sec: float = 2.0):
    if not os.path.exists(csv_filepath):
        print(f"Error: Dataset file not found at {csv_filepath}")
        return

    print(f"Loading real dataset from {csv_filepath}...")

    # Robust CSV reading
    try:
        df = pd.read_csv(
            csv_filepath,
            sep=None,
            engine='python',
            on_bad_lines='skip'
        )
    except Exception as e:
        print(f"Pandas failed to parse CSV: {e}. Falling back to DuckDB CSV parser...")
        con = duckdb.connect("telemetry.db")
        con.execute(f"""
            CREATE TABLE IF NOT EXISTS system_telemetry AS 
            SELECT * FROM read_csv_auto('{csv_filepath}', ignore_errors=true);
        """)
        print("Successfully loaded dataset directly into DuckDB via read_csv_auto!")
        return

    print(f"Loaded {len(df)} rows. Starting stream into DuckDB...")

    # Connect to DuckDB
    con = duckdb.connect("telemetry.db")
    con.execute("""
        CREATE TABLE IF NOT EXISTS system_telemetry (
            timestamp TIMESTAMP,
            gateway_name VARCHAR,
            capture_success_pct DOUBLE,
            compute_ms DOUBLE,
            anomaly_detected BOOLEAN
        )
    """)

    # Stream rows into DuckDB line-by-line using enumerate to prevent Tuple concatenation error
    for step_num, (index, row) in enumerate(df.iterrows(), start=1):
        now = time.strftime('%Y-%m-%d %H:%M:%S')

        # Fallback column extraction with standard defaults
        gateway = str(row.get('gateway', row.get('gateway_name', 'Clarion-US-East')))
        
        # Safe float conversion
        try:
            compute_ms = float(row.get('response_time', row.get('latency', row.get('compute_ms', 120.0))))
        except (ValueError, TypeError):
            compute_ms = 120.0

        try:
            capture_success_pct = float(row.get('success_rate', row.get('capture_success_pct', 98.5)))
        except (ValueError, TypeError):
            capture_success_pct = 98.5
        
        anomaly = bool(compute_ms > 500 or capture_success_pct < 80.0)

        con.execute(
            "INSERT INTO system_telemetry VALUES (?, ?, ?, ?, ?)",
            [now, gateway, capture_success_pct, compute_ms, anomaly]
        )

        print(f"[{now}] Streamed row {step_num}/{len(df)}: Latency={compute_ms}ms, Success={capture_success_pct}%")
        time.sleep(playback_speed_sec)

if __name__ == "__main__":
    stream_real_dataset("data/real_telemetry.csv", playback_speed_sec=2.0)