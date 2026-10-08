import os
import json
from typing import Optional, Dict, Any
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from data.upload_parser import parse_custom_csv, parse_custom_json
from feedback.feedback_store import record_feedback, get_all_feedback

app = FastAPI(title="Clarion Engine")

# --- Scenario Loader ---
@app.get("/api/scenario/{scenario_id}")
def get_scenario_data(scenario_id: str):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, "data", "scenarios", f"{scenario_id}.json")
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")
        
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

# --- Upload Parser API ---
@app.post("/api/upload")
async def upload_telemetry(file: UploadFile = File(...)):
    try:
        content = await file.read()
        name = file.filename.lower()
        if name.endswith(".csv"):
            conn = parse_custom_csv(content)
        elif name.endswith(".json"):
            conn = parse_custom_json(content)
        else:
            raise HTTPException(status_code=400, detail="Only CSV or JSON supported")
        
        count = conn.execute("SELECT COUNT(*) FROM custom_telemetry").fetchone()[0]
        return {"status": "success", "rows_ingested": count}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- Feedback Models & APIs ---
class FeedbackRequest(BaseModel):
    item_id: str
    decision: str
    notes: Optional[str] = ""
    metadata: Optional[Dict[str, Any]] = None

@app.post("/api/feedback")
def submit_feedback(payload: FeedbackRequest):
    try:
        entry = record_feedback(
            item_id=payload.item_id,
            decision=payload.decision,
            notes=payload.notes,
            metadata=payload.metadata
        )
        return {"status": "recorded", "entry": entry}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/feedback")
def retrieve_feedback():
    return {"feedback": get_all_feedback()}

# Mount static dashboard assets
app.mount("/", StaticFiles(directory="static", html=True), name="static")