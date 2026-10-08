import io
import json
from typing import Any, Dict, List, Optional
import duckdb
import pandas as pd

REQUIRED_COLUMNS = {"timestamp", "metric_name", "value", "event_type"}

def validate_dataframe_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Validates that required columns exist in the DataFrame."""
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Uploaded data is missing required columns: {sorted(list(missing))}")
    return df[list(REQUIRED_COLUMNS)]

def parse_custom_csv(file_bytes: bytes, table_name: str = "custom_telemetry", conn: Optional[duckdb.DuckDBPyConnection] = None) -> duckdb.DuckDBPyConnection:
    """
    Parses and validates a CSV byte stream, then registers it as a table in DuckDB.
    """
    try:
        df = pd.read_csv(io.BytesIO(file_bytes))
    except Exception as e:
        raise ValueError(f"Failed to decode CSV: {str(e)}")

    validated_df = validate_dataframe_schema(df)
    
    if conn is None:
        conn = duckdb.connect(database=":memory:")

    conn.register(f"{table_name}_view", validated_df)
    conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM {table_name}_view")
    return conn

def parse_custom_json(file_bytes: bytes, table_name: str = "custom_telemetry", conn: Optional[duckdb.DuckDBPyConnection] = None) -> duckdb.DuckDBPyConnection:
    """
    Parses and validates a JSON byte stream (records or nested objects), registering it in DuckDB.
    """
    try:
        raw_data = json.loads(file_bytes.decode("utf-8"))
    except Exception as e:
        raise ValueError(f"Failed to decode JSON: {str(e)}")

    if isinstance(raw_data, dict):
        if "data" in raw_data and isinstance(raw_data["data"], list):
            records = raw_data["data"]
        elif "telemetry" in raw_data and isinstance(raw_data["telemetry"], list):
            records = raw_data["telemetry"]
        else:
            records = [raw_data]
    elif isinstance(raw_data, list):
        records = raw_data
    else:
        raise ValueError("Invalid JSON format: expected list of records or telemetry object.")

    df = pd.DataFrame(records)
    validated_df = validate_dataframe_schema(df)

    if conn is None:
        conn = duckdb.connect(database=":memory:")

    conn.register(f"{table_name}_view", validated_df)
    conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM {table_name}_view")
    return conn 