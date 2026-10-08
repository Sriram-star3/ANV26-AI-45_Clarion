import json
import os
import pytest
from data.upload_parser import parse_custom_json

SCENARIOS = ["scenario_1.json", "scenario_2.json", "scenario_3.json"]

@pytest.mark.parametrize("scenario_file", SCENARIOS)
def test_scenario_execution_and_schema(scenario_file):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    scenario_path = os.path.join(base_dir, "data", "scenarios", scenario_file)

    if not os.path.exists(scenario_path):
        pytest.skip(f"Scenario file {scenario_file} not yet present in repository.")

    with open(scenario_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "scenario_id" in data
    assert "telemetry" in data
    assert len(data["telemetry"]) > 0

    # Ensure upload parser ingest works without infinite loops or runtime errors
    json_bytes = json.dumps(data["telemetry"]).encode("utf-8")
    conn = parse_custom_json(json_bytes, table_name="test_run")
    
    result = conn.execute("SELECT COUNT(*) FROM test_run").fetchone()
    assert result[0] == len(data["telemetry"])