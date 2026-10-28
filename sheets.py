"""Read-only access to the public Weyland-Yutani extraction workbook."""

from __future__ import annotations

import csv
import io
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any

import requests

SPREADSHEET_ID = os.environ.get(
    "SPREADSHEET_ID", "1kKnoVzwH-ua29vyfNwk0OcqYyPDkRXe03sSHLRNgPGM"
)
SPREADSHEET_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
DATA_GID = os.environ.get("DATA_GID", "2076345475")
CONTROLS_GID = os.environ.get("CONTROLS_GID", "706373598")
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "45"))

_SESSION = requests.Session()
_SESSION.headers.update(
    {"User-Agent": "WeylandDashboard/1.0 (read-only reporting client)"}
)
_LOCK = threading.Lock()
_CACHE: dict[str, Any] = {"dataset": None, "monotonic": 0.0, "fetched_at": None}


class SheetError(RuntimeError):
    """Raised when the workbook cannot be read or parsed."""


def _csv_url(sheet_name: str, gid: str) -> str:
    return (
        f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq"
        f"?tqx=out:csv&sheet={requests.utils.quote(sheet_name)}&headers=1&gid={gid}"
    )


def _fallback_url(gid: str) -> str:
    return (
        f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export"
        f"?format=csv&gid={gid}"
    )


def _read_csv(sheet_name: str, gid: str) -> list[list[str]]:
    last_error = "unknown error"
    for url in (_fallback_url(gid), _csv_url(sheet_name, gid)):
        try:
            response = _SESSION.get(url, timeout=35)
            response.raise_for_status()
            text = response.content.decode("utf-8-sig", errors="replace")
            if text.lstrip().startswith("<"):
                raise ValueError("Google returned HTML instead of CSV")
            rows = list(csv.reader(io.StringIO(text)))
            if len(rows) < 2:
                raise ValueError("CSV did not contain a header and data rows")
            return rows
        except Exception as exc:  # pragma: no cover - network dependent
            last_error = f"{type(exc).__name__}: {exc}"
    raise SheetError(f"Could not read the {sheet_name} tab ({last_error})")


def _clean(value: Any) -> str:
    return str(value or "").replace("\u00a0", " ").strip()


def parse_number(value: Any, default: float | None = None) -> float | None:
    text = _clean(value).replace(",", "").replace("−", "-")
    if not text:
        return default
    percent = text.endswith("%")
    text = text.rstrip("%")
    try:
        number = float(text)
    except ValueError:
        return default
    return number / 100.0 if percent else number


def _pad(row: list[str], width: int = 16) -> list[str]:
    return [_clean(value) for value in row] + [""] * max(0, width - len(row))


def _parse_controls(rows: list[list[str]]) -> dict[str, Any]:
    grid = [_pad(row, 16) for row in rows]

    def norm(value: str) -> str:
        return re.sub(r"\s+", " ", _clean(value)).lower()

    def find_row(label: str, col: int = 0) -> int | None:
        target = norm(label)
        for index, row in enumerate(grid):
            if col < len(row) and norm(row[col]) == target:
                return index
        return None

    def value_for(label: str, label_col: int, value_col: int, default: Any = None) -> Any:
        index = find_row(label, label_col)
        if index is None:
            return default
        return grid[index][value_col] if value_col < len(grid[index]) else default

    controls: dict[str, Any] = {
        "window": {
            "start": value_for("Start date", 0, 1, ""),
            "end": value_for("End date", 0, 1, ""),
            "days": parse_number(value_for("Days in range", 0, 1, 0), 0),
            "active_mines": parse_number(value_for("Active mines", 0, 1, 0), 0),
        },
        "distribution": {
            "type": value_for("Distribution", 4, 6, "") or "Normal",
            "normal_mean": parse_number(value_for("Normal mean (× nominal)", 4, 6, 1.0), 1.0),
            "normal_std": parse_number(value_for("Normal std dev (×)", 4, 6, 0.0), 0.0),
            "uniform_min": parse_number(value_for("Uniform min (×)", 4, 6, 0.0), 0.0),
            "uniform_max": parse_number(value_for("Uniform max (×)", 4, 6, 1.0), 1.0),
        },
        "dynamics": {
            "mine_smoothing": parse_number(value_for("Mine noise smoothing", 8, 14, 0.0), 0.0),
            "common_smoothing": parse_number(value_for("Common noise smoothing", 8, 14, 0.0), 0.0),
            "common_volatility": parse_number(value_for("Common volatility (σ)", 8, 14, 0.0), 0.0),
            "annual_trend": parse_number(value_for("Annual trend", 8, 14, 0.0), 0.0),
            "seed": parse_number(value_for("Random seed", 8, 14, 0), 0),
            "base_utilization": parse_number(value_for("Base utilization", 8, 14, 0.0), 0.0),
            "horizon_days": parse_number(value_for("Model horizon (days)", 8, 14, 0), 0),
        },
        "weekday_factors": {},
        "events": [],
        "mines": [],
    }

    for row in grid:
        day = row[5]
        if day in {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}:
            factor = parse_number(row[6])
            if factor is not None:
                controls["weekday_factors"][day] = factor

    for row in grid:
        name = row[8]
        start_date = row[9]
        if not name or name.lower() == "event":
            continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", start_date or ""):
            continue
        controls["events"].append(
            {
                "name": name,
                "start": start_date,
                "duration": parse_number(row[10], 0),
                "magnitude": parse_number(row[11], 0.0),
                "probability": parse_number(row[12], 0.0),
                "mine": int(parse_number(row[13], 0) or 0),
            }
        )

    for row in grid:
        name = row[1]
        number = parse_number(row[2])
        if not name or name.lower() == "mine" or number is None:
            continue
        if row[0].lower() not in {"yes", "no"}:
            continue
        number_int = int(number)
        if number_int < 1:
            continue
        controls["mines"].append(
            {
                "number": number_int,
                "name": name,
                "active": row[0].lower().startswith("y"),
                "capacity": parse_number(row[3], 0.0),
            }
        )
        if len(controls["mines"]) >= 20:
            break

    return controls

def _parse_dataset(data_rows: list[list[str]], controls: dict[str, Any]) -> dict[str, Any]:
    header = [_clean(value) for value in data_rows[0]]
    if not header or header[0].lower() != "date":
        raise SheetError("The Data tab does not start with a Date column")
    if "Total output" not in header:
        raise SheetError("The Data tab is missing the Total output column")

    mine_columns: dict[int, int] = {}
    for index, label in enumerate(header):
        match = re.fullmatch(r"Mine\s+(\d+)", label, flags=re.IGNORECASE)
        if match:
            mine_columns[int(match.group(1))] = index

    mine_meta = {mine["number"]: mine for mine in controls.get("mines", [])}
    dates: list[str] = []
    totals: list[float] = []
    mine_values: dict[int, list[float]] = {number: [] for number in mine_columns}

    for row_index, row in enumerate(data_rows[1:], start=2):
        date_text = _clean(row[0] if row else "")
        if not date_text:
            continue
        try:
            datetime.strptime(date_text[:10], "%Y-%m-%d")
        except ValueError as exc:
            raise SheetError(f"Invalid date in Data row {row_index}: {date_text!r}") from exc
        total = parse_number(row[header.index("Total output")])
        if total is None:
            continue
        dates.append(date_text[:10])
        totals.append(total)
        for number, col in mine_columns.items():
            mine_values[number].append(parse_number(row[col] if col < len(row) else "", 0.0) or 0.0)

    if not dates:
        raise SheetError("The Data tab has no numeric output rows")

    mines = []
    for number in sorted(mine_values):
        meta = mine_meta.get(number, {})
        values = mine_values[number]
        mines.append(
            {
                "id": f"mine-{number}",
                "number": number,
                "name": meta.get("name") or f"Mine {number}",
                "active": bool(meta.get("active", any(value > 0 for value in values))),
                "capacity": meta.get("capacity", 0.0),
                "values": values,
            }
        )

    return {
        "dates": dates,
        "total": totals,
        "mines": mines,
        "controls": controls,
        "row_count": len(dates),
    }


def fetch_dataset(force: bool = False) -> dict[str, Any]:
    now = time.monotonic()
    with _LOCK:
        cached = _CACHE.get("dataset")
        if cached and not force and now - float(_CACHE["monotonic"]) < CACHE_TTL_SECONDS:
            return {**cached, "cache": "hit"}

    try:
        data_rows = _read_csv("Data", DATA_GID)
        control_rows = _read_csv("Controls", CONTROLS_GID)
        controls = _parse_controls(control_rows)
        dataset = _parse_dataset(data_rows, controls)
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        dataset.update(
            {
                "source": {
                    "spreadsheet_id": SPREADSHEET_ID,
                    "spreadsheet_url": SPREADSHEET_URL,
                    "fetched_at": fetched_at,
                    "access": "public CSV",
                },
                "cache": "miss" if not force else "refresh",
            }
        )
        with _LOCK:
            _CACHE["dataset"] = dataset
            _CACHE["monotonic"] = time.monotonic()
            _CACHE["fetched_at"] = fetched_at
        return dataset
    except Exception as exc:
        with _LOCK:
            stale = _CACHE.get("dataset")
        if stale:
            return {
                **stale,
                "cache": "stale",
                "warning": f"Live refresh failed; showing the previous snapshot. {exc}",
            }
        if isinstance(exc, SheetError):
            raise
        raise SheetError(str(exc)) from exc
