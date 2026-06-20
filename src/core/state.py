"""
Tiny local state store. Currently used to remember the Slack 'ts' cursor
of the last message processed by the hourly intake job, so re-running it
never double-logs the same message into the tracker.

Deliberately simple (a JSON file) — this is automation-script state, not
tracker data, so it doesn't belong in Sheets/Notion.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STATE_PATH = Path(__file__).resolve().parents[2] / "logs" / "state.json"


def _read() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _write(data: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get(key: str, default: Any = None) -> Any:
    return _read().get(key, default)


def set(key: str, value: Any) -> None:
    data = _read()
    data[key] = value
    _write(data)
