import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
from typing import Optional, Dict, Any, List, Tuple, Union
from supabase import create_client, Client
from dotenv import load_dotenv
from pathlib import Path

app = FastAPI(debug=True)

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") # keep private

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Allow requests from Vite dev server and common local ports
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Supabase setup ---
# Load .env from the backend directory explicitly so it works regardless of cwd
_dotenv_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_dotenv_path)
# Read from env var key SUPABASE_URL, but default to your project URL as a fallback
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://uyowiwivczuuajwxrhme.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY") or ""
SUPABASE_TABLE_NAME = os.environ.get("SUPABASE_TABLE_NAME", "vdot_data")

supabase_client: Optional[Client] = None

def get_supabase() -> Optional[Client]:
    global supabase_client
    if supabase_client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            print("Supabase not configured: missing SUPABASE_URL or API key", flush=True)
            return None
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return supabase_client


# Print a small sample of Supabase data on startup
@app.on_event("startup")
def print_supabase_sample_on_startup() -> None:
    client = get_supabase()
    if client is None:
        print("Supabase not configured; skipping sample fetch.", flush=True)
        return
    try:
        response = client.table(SUPABASE_TABLE_NAME).select("*").limit(5).execute()
        rows: List[Dict[str, Any]] = getattr(response, "data", []) or []
        print(f"Fetched {len(rows)} sample row(s) from '{SUPABASE_TABLE_NAME}':", flush=True)
        for idx, row in enumerate(rows, start=1):
            print(f"[{idx}] {row}", flush=True)
    except Exception as e:
        print(f"Supabase startup sample fetch failed: {e}", flush=True)

class SubmitPayload(BaseModel):
    value: str


# --- Time parsing helpers ---

def parse_time_to_seconds(value: str) -> Optional[float]:
    # Accept formats: "25" (minutes), "25.5" (minutes), "mm:ss", "hh:mm:ss"
    s = value.strip()
    if not s:
        return None
    if ":" in s:
        parts = s.split(":")
        try:
            parts = [float(p) for p in parts]
        except ValueError:
            return None
        if len(parts) == 2:
            minutes, seconds = parts
            return minutes * 60 + seconds
        if len(parts) == 3:
            hours, minutes, seconds = parts
            return hours * 3600 + minutes * 60 + seconds
        return None
    # No colon: treat as minutes (allow float)
    try:
        minutes = float(s)
        return minutes * 60
    except ValueError:
        return None


def try_parse_db_time_to_seconds(raw: Union[str, int, float]) -> Optional[float]:
    if raw is None:
        return None
    # If string, try mm:ss or hh:mm:ss, otherwise try float minutes
    if isinstance(raw, str):
        if ":" in raw:
            return parse_time_to_seconds(raw)
        # string number: treat as minutes
        try:
            return float(raw) * 60
        except ValueError:
            return None
    # Numeric: decide likely unit by magnitude
    try:
        number = float(raw)
    except Exception:
        return None
    # Heuristic: typical 5k seconds 800-3600; minutes 13-60
    if number >= 100:  # likely seconds
        return number
    # else assume minutes
    return number * 60


def query_row_closest_by_race_5km(value: str) -> Optional[Dict[str, Any]]:
    # Convert the input to seconds
    target_seconds = parse_time_to_seconds(value)
    if target_seconds is None:
        return None

    client = get_supabase()
    if client is None:
        # Supabase environment is not configured
        return None

    # Fetch rows where race_5km is not null. Depending on your data size,
    # you may want to further restrict or paginate the query.
    try:
        # Fetch rows; we'll filter out null race_5km values in Python for simplicity
        response = client.table(SUPABASE_TABLE_NAME).select("*").limit(1000).execute()
    except Exception as e:
        print(f"Supabase query failed: {e}", flush=True)
        return None

    rows: List[Dict[str, Any]] = getattr(response, "data", []) or []
    if not rows:
        return None

    best: Tuple[float, Optional[Dict[str, Any]]] = (float("inf"), None)
    for row in rows:
        raw = row.get("race_5km")
        seconds = try_parse_db_time_to_seconds(raw)
        if seconds is None:
            continue
        dist = abs(seconds - target_seconds)
        if dist < best[0]:
            best = (dist, row)

    return best[1] if best[1] is not None else None


@app.post("/submit")
def submit(payload: SubmitPayload):
    def pick_first_existing(row: Dict[str, Any], keys: List[str]) -> Optional[Any]:
        for k in keys:
            if k in row and row[k] is not None:
                return row[k]
        return None

    def select_fields(row: Dict[str, Any]) -> Dict[str, Any]:
        # Normalize and expose only the requested fields
        return {
            "vdot": pick_first_existing(row, ["vdot", "VDOT"]),
            "race_half_marathon": pick_first_existing(
                row, ["race_half_marathon", "race_half", "half_marathon"]
            ),
            "easy_pace_per_mile": pick_first_existing(
                row, ["easy_pace_per_mile", "easy_per_mile", "easy_mile_pace"]
            ),
            # Keep the key spelling as requested: easy_pase_per_km (accept common variants from DB)
            "easy_pase_per_km": pick_first_existing(
                row,
                [
                    "easy_pase_per_km",
                    "easy_pace_per_km",
                    "easy_per_km",
                    "easy_km_pace",
                ],
            ),
            "marathon_pace_per_mile": pick_first_existing(
                row,
                [
                    "marathon_pace_per_mile",
                    "marathon_per_mile",
                    "marathon_mile_pace",
                ],
            ),
            "marathon_pace_per_km": pick_first_existing(
                row, ["marathon_pace_per_km", "marathon_per_km", "marathon_km_pace"]
            ),
            "threshold_pace_per_km": pick_first_existing(
                row, ["threshold_pace_per_km", "threshold_per_km", "threshold_km_pace"]
            ),
            "threshold_pace_per_mile": pick_first_existing(
                row,
                [
                    "threshold_pace_per_mile",
                    "threshold_per_mile",
                    "threshold_mile_pace",
                ],
            ),
        }

    row = query_row_closest_by_race_5km(payload.value)
    if row is None:
        print(f"No row found near race_5km ≈ {payload.value}", flush=True)
        return {"received": payload.value, "row": None}

    selected = select_fields(row)
    # Print only the requested fields in a readable form
    printable = (
        f"vdot={selected.get('vdot')}, "
        f"race_half_marathon={selected.get('race_half_marathon')}, "
        f"easy_pace_per_mile={selected.get('easy_pace_per_mile')}, "
        f"easy_pase_per_km={selected.get('easy_pase_per_km')}, "
        f"marathon_pace_per_mile={selected.get('marathon_pace_per_mile')}, "
        f"marathon_pace_per_km={selected.get('marathon_pace_per_km')}, "
        f"threshold_pace_per_km={selected.get('threshold_pace_per_km')}, "
        f"threshold_pace_per_mile={selected.get('threshold_pace_per_mile')}"
    )
    print(f"Closest row for race_5km ≈ {payload.value}: {printable}", flush=True)
    return {"received": payload.value, "row": selected}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
