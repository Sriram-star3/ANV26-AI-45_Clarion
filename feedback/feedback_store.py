import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List

FEEDBACK_FILE_PATH = os.path.join(os.path.dirname(__file__), "feedback.json")
_LOCK = threading.Lock()

def _load_data() -> List[Dict[str, Any]]:
    if not os.path.exists(FEEDBACK_FILE_PATH):
        return []
    try:
        with open(FEEDBACK_FILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []

def record_feedback(item_id: str, decision: str, notes: str = "", metadata: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Appends user confirmations or rejections to local feedback.json fallback store.
    """
    if decision not in {"CONFIRMED", "REJECTED"}:
        raise ValueError("Decision must be either 'CONFIRMED' or 'REJECTED'")

    entry = {
        "item_id": item_id,
        "decision": decision,
        "notes": notes,
        "metadata": metadata or {},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    with _LOCK:
        entries = _load_data()
        entries.append(entry)
        with open(FEEDBACK_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2)

    return entry

def get_all_feedback() -> List[Dict[str, Any]]:
    """Retrieves all feedback entries recorded in the file fallback store."""
    with _LOCK:
        return _load_data()