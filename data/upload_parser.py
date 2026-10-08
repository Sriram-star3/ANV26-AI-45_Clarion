python
import pandas as pd
import io
import json

def parse_custom_log(file_bytes: bytes, filename: str = "") -> list[dict]:
    """
    Parses uploaded CSV or JSON log bytes into engine-compatible record dictionaries.
    """
    try:
        if filename.endswith(".json"):
            data = json.loads(file_bytes.decode("utf-8"))
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                return [data]
        
        # Default CSV parsing
        df = pd.read_csv(io.BytesIO(file_bytes))
        return df.to_dict(orient="records")
    except Exception as e:
        return [{"error": f"Failed to parse log file: {str(e)}"}]


