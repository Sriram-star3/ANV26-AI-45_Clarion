"""SQLite database operations and transaction management for Clarion.

Manages incident history storage, operator feedback persistence, and adaptive prior calculations.
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any

DB_PATH = "clarion.db"


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Create and return a SQLite connection configured with Row factory and thread safety."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DB_PATH) -> None:
    """Initialize database tables for incident history and user feedback if not present."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS incident_history (
                    dossier_id TEXT PRIMARY KEY,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    root_cause TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dossier_id TEXT NOT NULL,
                    hypothesis_id TEXT NOT NULL,
                    feedback_type TEXT CHECK(feedback_type IN ('confirm', 'reject')),
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
    finally:
        conn.close()


def save_incident_history(
    dossier_id: str,
    root_cause: str,
    confidence: float,
    payload: dict | str,
    db_path: str = DB_PATH,
) -> None:
    """Save an incident history record, safely serializing dict payloads to JSON string."""
    if isinstance(payload, str):
        payload_json = payload
    else:
        payload_json = json.dumps(payload, default=str)

    init_db(db_path)
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO incident_history (dossier_id, root_cause, confidence, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (dossier_id, root_cause, float(confidence), payload_json),
            )
    finally:
        conn.close()


def get_incident_history(
    search_query: str | None = None,
    db_path: str = DB_PATH,
) -> list[dict[str, Any]]:
    """Fetch incident history records ordered by timestamp DESC with parsed payload_json."""
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        if search_query and search_query.strip():
            param = f"%{search_query.strip()}%"
            cursor.execute(
                """
                SELECT dossier_id, timestamp, root_cause, confidence, payload_json
                FROM incident_history
                WHERE dossier_id LIKE ? OR root_cause LIKE ?
                ORDER BY timestamp DESC
                """,
                (param, param),
            )
        else:
            cursor.execute(
                """
                SELECT dossier_id, timestamp, root_cause, confidence, payload_json
                FROM incident_history
                ORDER BY timestamp DESC
                """
            )
        rows = cursor.fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            record = dict(row)
            try:
                record["payload_json"] = json.loads(record["payload_json"])
            except (json.JSONDecodeError, TypeError):
                pass
            results.append(record)
        return results
    finally:
        conn.close()


def get_incident_by_id(dossier_id: str, db_path: str = DB_PATH) -> dict[str, Any] | None:
    """Fetch a single incident record by dossier_id with parsed payload_json."""
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT dossier_id, timestamp, root_cause, confidence, payload_json
            FROM incident_history
            WHERE dossier_id = ?
            """,
            (dossier_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        record = dict(row)
        try:
            record["payload_json"] = json.loads(record["payload_json"])
        except (json.JSONDecodeError, TypeError):
            pass
        return record
    finally:
        conn.close()


def save_feedback(
    dossier_id: str,
    hypothesis_id: str,
    feedback_type: str,
    db_path: str = DB_PATH,
) -> None:
    """Insert a feedback record ('confirm' or 'reject') for an incident hypothesis."""
    if feedback_type not in ("confirm", "reject"):
        raise ValueError(f"Invalid feedback_type '{feedback_type}'. Must be 'confirm' or 'reject'.")

    init_db(db_path)
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO feedback (dossier_id, hypothesis_id, feedback_type)
                VALUES (?, ?, ?)
                """,
                (dossier_id, hypothesis_id, feedback_type),
            )
    finally:
        conn.close()


def get_adjusted_priors(db_path: str = DB_PATH) -> dict[str, float]:
    """Read feedback grouped by hypothesis_id, counting confirm as +1.0 and reject as -1.0 with base 1.0."""
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT hypothesis_id,
                   SUM(CASE WHEN feedback_type = 'confirm' THEN 1.0
                            WHEN feedback_type = 'reject' THEN -1.0
                            ELSE 0.0 END) AS net_score
            FROM feedback
            GROUP BY hypothesis_id
            """
        )
        rows = cursor.fetchall()
        priors: dict[str, float] = {}
        for row in rows:
            hyp_id = row["hypothesis_id"]
            net_score = float(row["net_score"]) if row["net_score"] is not None else 0.0
            # Base of 1.0 adjusted by operator confirmation/rejection feedback
            priors[hyp_id] = max(0.01, 1.0 + net_score)
        return priors
    finally:
        conn.close()
