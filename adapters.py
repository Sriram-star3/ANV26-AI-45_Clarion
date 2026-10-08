"""Data source adapters for Clarion causal reasoning engine.

Provides uniform tabular loading and cryptographic content fingerprinting across
CSV and DuckDB analytical backends.
"""

from __future__ import annotations

import abc
import hashlib
from pathlib import Path
from typing import Any
import pandas as pd

__all__ = [
    "BaseAdapter",
    "CsvAdapter",
    "JsonAdapter",
    "DuckDBAdapter",
    "build_registry",
]


class BaseAdapter(abc.ABC):
    """Abstract base adapter for loading tabular evidence sources."""

    def __init__(self, name: str) -> None:
        """Initialize adapter with logical source name."""
        self._name = name

    @property
    def name(self) -> str:
        """Return logical name of data source."""
        return self._name

    @abc.abstractmethod
    def load(self) -> pd.DataFrame:
        """Load tabular data returning DataFrame with timezone-naive 'ts' column."""
        raise NotImplementedError

    @abc.abstractmethod
    def fingerprint(self) -> str:
        """Compute SHA-256 cryptographic digest of underlying source."""
        raise NotImplementedError


class CsvAdapter(BaseAdapter):
    """Adapter reading local CSV files with datetime parsing and byte hashing."""

    def __init__(self, filename: str | Path, time_cols: list[str] | None = None, name: str | None = None) -> None:
        """Initialize CSV adapter with path, optional datetime columns, and name."""
        self.file_path = Path(filename)
        source_name = name or self.file_path.stem
        super().__init__(source_name)
        self.time_cols = time_cols or ["ts"]

    def load(self) -> pd.DataFrame:
        """Read CSV into pandas DataFrame and normalize time columns to tz-naive."""
        if not self.file_path.exists():
            raise FileNotFoundError(f"Source file not found: {self.file_path}")
        df = pd.read_csv(self.file_path)
        for col in self.time_cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col])
                if hasattr(df[col].dt, "tz") and df[col].dt.tz is not None:
                    df[col] = df[col].dt.tz_localize(None)
        return df

    def fingerprint(self) -> str:
        """Compute SHA-256 checksum of raw CSV file bytes."""
        if not self.file_path.exists():
            return hashlib.sha256(b"").hexdigest()
        content = self.file_path.read_bytes()
        return hashlib.sha256(content).hexdigest()


class JsonAdapter(BaseAdapter):
    """Adapter reading local JSON tabular or record files."""

    def __init__(self, filename: str | Path, name: str | None = None) -> None:
        """Initialize JSON adapter with file path and name."""
        self.file_path = Path(filename)
        source_name = name or self.file_path.stem
        super().__init__(source_name)

    def load(self) -> pd.DataFrame:
        """Read JSON file into pandas DataFrame normalizing 'ts' if present."""
        if not self.file_path.exists():
            raise FileNotFoundError(f"Source file not found: {self.file_path}")
        df = pd.read_json(self.file_path)
        if "ts" in df.columns:
            df["ts"] = pd.to_datetime(df["ts"])
            if hasattr(df["ts"].dt, "tz") and df["ts"].dt.tz is not None:
                df["ts"] = df["ts"].dt.tz_localize(None)
        return df

    def fingerprint(self) -> str:
        """Compute SHA-256 checksum of JSON file bytes."""
        if not self.file_path.exists():
            return hashlib.sha256(b"").hexdigest()
        content = self.file_path.read_bytes()
        return hashlib.sha256(content).hexdigest()


class DuckDBAdapter(BaseAdapter):
    """Adapter executing SQL query in DuckDB to push down data loading."""

    def __init__(self, sql: str, name: str, source_path: str | Path | None = None) -> None:
        """Initialize DuckDB adapter with analytical SQL query and source name."""
        super().__init__(name)
        self.sql = sql
        self.source_path = Path(source_path) if source_path is not None else None

    def load(self) -> pd.DataFrame:
        """Execute SQL query using DuckDB and return DataFrame with tz-naive 'ts'."""
        try:
            import duckdb
        except ImportError as exc:
            raise ImportError("DuckDB is required for DuckDBAdapter but is not installed.") from exc

        con = duckdb.connect(database=":memory:")
        try:
            df = con.execute(self.sql).df()
        finally:
            con.close()

        # Normalize any time columns
        for col in ["ts", "checkout_cancelled_at", "poll_502_ts"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col])
                if hasattr(df[col].dt, "tz") and df[col].dt.tz is not None:
                    df[col] = df[col].dt.tz_localize(None)
        return df

    def fingerprint(self) -> str:
        """Compute SHA-256 digest of SQL query and resulting frame bytes."""
        df = self.load()
        # Serialize normalized data bytes for deterministic hashing
        frame_bytes = df.to_csv(index=False).encode("utf-8")
        payload = self.sql.encode("utf-8") + b"|" + frame_bytes
        return hashlib.sha256(payload).hexdigest()


def build_registry(data_dir: str | Path, backend: str = "csv") -> dict[str, BaseAdapter]:
    """Construct evidence adapter registry keyed by source name for csv or duckdb."""
    p = Path(data_dir)
    files = {
        "telemetry": p / "telemetry.csv",
        "ledger": p / "payment_ledger.csv",
        "fleet": p / "fleet_events.csv",
        "tickets": p / "support_tickets.csv",
        "audit": p / "audit_log.csv",
    }

    registry: dict[str, BaseAdapter] = {}
    if backend.lower() == "csv":
        for key, filepath in files.items():
            time_cols = ["ts"]
            if key == "ledger":
                time_cols = ["ts", "checkout_cancelled_at", "poll_502_ts"]
            registry[key] = CsvAdapter(filename=filepath, time_cols=time_cols, name=key)
    elif backend.lower() == "duckdb":
        for key, filepath in files.items():
            posix_path = filepath.resolve().as_posix()
            sql = f"SELECT * FROM read_csv_auto('{posix_path}')"
            registry[key] = DuckDBAdapter(sql=sql, name=key, source_path=filepath)
    else:
        raise ValueError(f"Unsupported adapter backend: {backend}. Use 'csv' or 'duckdb'.")

    return registry
