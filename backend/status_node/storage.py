from __future__ import annotations

import os
import sqlite3
import threading
from typing import Any

from status_node import models

# In-memory read cache (username -> status incl. tombstones) mirroring the
# SQLite table, so reads stay fast while every write is persisted.
statuses: dict[str, dict[str, Any]] = {}

DB_PATH = ":memory:"
_conn: sqlite3.Connection | None = None
_db_lock = threading.Lock()

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS statuses (
    username   TEXT PRIMARY KEY,
    statustext TEXT NOT NULL DEFAULT '',
    uhrzeit    TEXT NOT NULL,
    latitude   REAL,
    longitude  REAL,
    deleted    INTEGER NOT NULL DEFAULT 0,
    originNode TEXT
)
"""


def _status_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "username": row["username"],
        "statustext": row["statustext"],
        "uhrzeit": row["uhrzeit"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "deleted": bool(row["deleted"]),
        "originNode": row["originNode"],
    }


def _load_cache_locked() -> None:
    # Caller must hold _db_lock.
    statuses.clear()
    assert _conn is not None
    for row in _conn.execute("SELECT * FROM statuses"):
        status = _status_from_row(row)
        statuses[status["username"]] = status


def init_db(path: str) -> None:
    # Re-opening yields a clean, isolated store, which the tests rely on.
    global _conn, DB_PATH
    with _db_lock:
        if _conn is not None:
            _conn.close()
        DB_PATH = path
        parent = os.path.dirname(path)
        if path != ":memory:" and parent:
            os.makedirs(parent, exist_ok=True)
        _conn = sqlite3.connect(path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        journal_mode = os.getenv("SQLITE_JOURNAL_MODE", "").strip().upper()
        if journal_mode:
            allowed_modes = {"DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL", "OFF"}
            if journal_mode not in allowed_modes:
                raise ValueError(f"Unsupported SQLite journal mode: {journal_mode}")
            _conn.execute(f"PRAGMA journal_mode={journal_mode}")
        _conn.execute(_CREATE_TABLE_SQL)
        _conn.commit()
        _load_cache_locked()


def _persist(status: dict[str, Any]) -> None:
    with _db_lock:
        if _conn is None:
            return
        _conn.execute(
            "INSERT INTO statuses "
            "(username, statustext, uhrzeit, latitude, longitude, deleted, originNode) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(username) DO UPDATE SET "
            "statustext=excluded.statustext, uhrzeit=excluded.uhrzeit, "
            "latitude=excluded.latitude, longitude=excluded.longitude, "
            "deleted=excluded.deleted, originNode=excluded.originNode",
            (
                status["username"],
                status["statustext"],
                status["uhrzeit"],
                status["latitude"],
                status["longitude"],
                1 if status["deleted"] else 0,
                status["originNode"],
            ),
        )
        _conn.commit()


def apply_status(status: dict[str, Any]) -> bool:
    """Apply a status only if it wins Last-Writer-Wins; persist on apply."""
    if not models.is_newer(status, statuses.get(status["username"])):
        return False
    statuses[status["username"]] = status
    _persist(status)
    return True


def visible_statuses() -> list[dict[str, Any]]:
    return [status for status in statuses.values() if not status.get("deleted", False)]


def snapshot() -> list[dict[str, Any]]:
    # Includes tombstones so replicated deletes survive a peer's initial sync.
    return list(statuses.values())


# Provide a usable in-memory store on import so the app works in tests without
# an explicit init_db(); the entrypoint re-inits with the configured DB_PATH.
init_db(DB_PATH)
