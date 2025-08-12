import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import os
from typing import Optional, Dict, Any, List, Tuple, Union

app = FastAPI(debug=True)

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

DB_PATH = os.path.join(os.path.dirname(__file__), "vdot_data.db")

class SubmitPayload(BaseModel):
    value: str


def find_table_with_column(conn: sqlite3.Connection, column_name: str, preferred_table: str = "vdot_data") -> Optional[str]:
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    preferred = [t for t in tables if t.lower() == preferred_table.lower()]
    candidates = preferred + [t for t in tables if t not in preferred]
    for table in candidates:
        cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
        col_names = {c[1].lower() for c in cols}
        if column_name.lower() in col_names:
            return table
    return None


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


def detect_db_time_unit_seconds(conn: sqlite3.Connection, table: str, column: str) -> str:
    # Returns "seconds", "minutes", or "string" indicating storage style
    sample_rows = conn.execute(
        f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL LIMIT 20"
    ).fetchall()
    if not sample_rows:
        return "unknown"
    raw_values = [row[0] for row in sample_rows]
    if any(isinstance(v, str) and ":" in v for v in raw_values):
        return "string"  # time-like strings
    # If numeric (or numeric strings), look at median magnitude
    numeric_vals: List[float] = []
    for v in raw_values:
        try:
            numeric_vals.append(float(v))
        except Exception:
            continue
    if not numeric_vals:
        return "unknown"
    numeric_vals.sort()
    median = numeric_vals[len(numeric_vals)//2]
    return "seconds" if median >= 100 else "minutes"


def query_row_closest_by_race_5km(value: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(DB_PATH):
        return None

    target_seconds = parse_time_to_seconds(value)
    if target_seconds is None:
        return None

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        table = find_table_with_column(conn, column_name="race_5km", preferred_table="vdot_data")
        if not table:
            return None

        storage_style = detect_db_time_unit_seconds(conn, table, "race_5km")

        rows = conn.execute(f"SELECT * FROM {table} WHERE race_5km IS NOT NULL").fetchall()
        best: Tuple[float, Optional[sqlite3.Row]] = (float("inf"), None)
        for row in rows:
            raw = row["race_5km"]
            if storage_style == "string":
                seconds = try_parse_db_time_to_seconds(raw)
            elif storage_style == "minutes":
                try:
                    seconds = float(raw) * 60
                except Exception:
                    seconds = None
            elif storage_style == "seconds":
                try:
                    seconds = float(raw)
                except Exception:
                    seconds = None
            else:
                seconds = try_parse_db_time_to_seconds(raw)

            if seconds is None:
                continue
            dist = abs(seconds - target_seconds)
            if dist < best[0]:
                best = (dist, row)

        if best[1] is not None:
            return dict(best[1])
        return None
    finally:
        conn.close()


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
