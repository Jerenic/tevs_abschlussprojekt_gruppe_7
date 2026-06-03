from __future__ import annotations

import datetime
import os
import sqlite3
import sys
import threading
import time
from typing import Any

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# In-memory read-cache: username -> latest status object, including delete tombstones.
# The cache mirrors the SQLite table so reads stay fast while writes are persisted.
statuses: dict[str, dict[str, Any]] = {}
PEER_URLS: list[str] = []
NODE_NAME = "Node"

# Bootstrap / grace-period state. A freshly started node first pulls a snapshot
# from its peers before it answers client traffic. Defaults to ready so that
# imports and unit tests are not gated; the __main__ entrypoint flips it.
READY = True
NODE_STATE = "ready"
BOOTSTRAP_TIMEOUT = float(os.environ.get("BOOTSTRAP_TIMEOUT", "8"))

# Failed peer replications are queued here and retried by a background worker,
# so a temporarily unreachable peer does not lose updates or break client writes.
pending_replications: list[dict[str, Any]] = []
_pending_lock = threading.Lock()
RETRY_INTERVAL = float(os.environ.get("RETRY_INTERVAL", "5"))

# SQLite persistence. Each node owns its own local database file (no shared DB).
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


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def parse_iso(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed
    except ValueError:
        return None


def normalize_status(data: Any, *, allow_deleted: bool = False) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(data, dict):
        return None, "Payload muss ein JSON-Objekt sein"

    username = str(data.get("username", "")).strip()
    if not username:
        return None, "username erforderlich"

    deleted = bool(data.get("deleted", False))
    statustext = data.get("statustext", "")
    if not deleted and (not isinstance(statustext, str) or not statustext.strip()):
        return None, "statustext erforderlich"
    if deleted and not allow_deleted:
        return None, "deleted ist fuer diesen Endpunkt nicht erlaubt"

    latitude = data.get("latitude")
    longitude = data.get("longitude")
    if not deleted:
        if not isinstance(latitude, (int, float)):
            return None, "latitude muss eine Zahl sein"
        if not isinstance(longitude, (int, float)):
            return None, "longitude muss eine Zahl sein"

    uhrzeit = data.get("uhrzeit") or now_iso()
    if parse_iso(uhrzeit) is None:
        return None, "uhrzeit muss im ISO-8601 Format sein"

    return {
        "username": username,
        "statustext": "" if deleted else statustext.strip(),
        "uhrzeit": uhrzeit,
        "latitude": None if deleted else float(latitude),
        "longitude": None if deleted else float(longitude),
        "deleted": deleted,
        "originNode": data.get("originNode") or NODE_NAME,
    }, None


def should_apply(incoming: dict[str, Any]) -> bool:
    """Last-Writer-Wins decision based on `uhrzeit`.

    Newer timestamp wins. On an exact timestamp tie we break deterministically
    by `originNode` so that every node converges to the same winner regardless
    of the order in which replicated updates arrive.
    """
    existing = statuses.get(incoming["username"])
    if not existing:
        return True

    existing_time = parse_iso(existing.get("uhrzeit"))
    incoming_time = parse_iso(incoming.get("uhrzeit"))
    if not existing_time or not incoming_time:
        return True

    if incoming_time > existing_time:
        return True
    if incoming_time < existing_time:
        return False

    return str(incoming.get("originNode", "")) >= str(existing.get("originNode", ""))


def apply_status(status: dict[str, Any]) -> bool:
    if not should_apply(status):
        return False
    statuses[status["username"]] = status
    _persist(status)
    return True


def _enqueue_pending(peer_url: str, status: dict[str, Any]) -> None:
    with _pending_lock:
        username = status["username"]
        # Keep only the newest pending update per peer+username (LWW also for retries).
        pending_replications[:] = [
            item for item in pending_replications
            if not (item["peer"] == peer_url and item["status"]["username"] == username)
        ]
        pending_replications.append({"peer": peer_url, "status": status})


def replicate_to_peers(status: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for peer_url in PEER_URLS:
        try:
            response = requests.post(f"{peer_url}/replicate", json=status, timeout=2)
            results.append({"peer": peer_url, "status": response.status_code, "ok": response.ok})
            if not response.ok:
                _enqueue_pending(peer_url, status)
        except requests.RequestException as exc:
            results.append({"peer": peer_url, "status": None, "ok": False, "error": str(exc)})
            _enqueue_pending(peer_url, status)
    return results


def process_pending() -> int:
    with _pending_lock:
        queued = list(pending_replications)
    flushed = 0
    for item in queued:
        try:
            response = requests.post(f"{item['peer']}/replicate", json=item["status"], timeout=2)
        except requests.RequestException:
            continue
        if not response.ok:
            continue
        with _pending_lock:
            if item in pending_replications:
                pending_replications.remove(item)
        flushed += 1
    return flushed


def retry_worker(interval: float | None = None) -> None:
    interval = RETRY_INTERVAL if interval is None else interval
    while True:
        time.sleep(interval)
        if pending_replications:
            process_pending()


def visible_statuses() -> list[dict[str, Any]]:
    return [status for status in statuses.values() if not status.get("deleted", False)]


def fetch_snapshot(peer_url: str, timeout: float = 3.0) -> list[dict[str, Any]] | None:
    # Snapshot includes tombstones so replicated deletes survive the initial sync.
    try:
        response = requests.get(f"{peer_url}/internal/snapshot", timeout=timeout)
        if not response.ok:
            return None
        data = response.json()
        return data.get("statuses", []) if isinstance(data, dict) else []
    except (requests.RequestException, ValueError):
        return None


def bootstrap_from_peers(peers: list[str] | None = None, timeout: float | None = None) -> int:
    """Initial sync: merge peer snapshots into the local store using LWW.

    Tries each peer until it answers or the timeout elapses. Returns the number
    of applied (won) status objects. Unreachable peers are simply skipped, so a
    first node without reachable peers proceeds with its own (persisted) data.
    """
    peers = PEER_URLS if peers is None else peers
    timeout = BOOTSTRAP_TIMEOUT if timeout is None else timeout
    if not peers:
        return 0

    deadline = time.monotonic() + timeout
    outstanding = set(peers)
    applied = 0

    while outstanding and time.monotonic() < deadline:
        for peer in list(outstanding):
            snapshot_data = fetch_snapshot(peer)
            if snapshot_data is None:
                continue
            for raw in snapshot_data:
                normalized, error = normalize_status(raw, allow_deleted=True)
                if error:
                    continue
                if apply_status(normalized):
                    applied += 1
            outstanding.discard(peer)
        if outstanding:
            time.sleep(0.5)

    return applied


def run_bootstrap() -> None:
    """Run the grace period: gate client traffic until the initial sync is done."""
    global READY, NODE_STATE
    READY = False
    NODE_STATE = "bootstrapping"
    try:
        count = bootstrap_from_peers()
        print(f"[{NODE_NAME}] Bootstrap abgeschlossen: {count} Status uebernommen")
    finally:
        READY = True
        NODE_STATE = "ready"


def _not_ready_response():
    return jsonify({
        "error": "Node befindet sich im Bootstrap (Grace Period)",
        "node": NODE_NAME,
        "state": NODE_STATE,
    }), 503


@app.after_request
def add_node_header(response):
    response.headers["X-Status-Node"] = NODE_NAME
    return response


@app.route("/status", methods=["POST"])
def post_status():
    if not READY:
        return _not_ready_response()
    status, error = normalize_status(request.get_json(silent=True), allow_deleted=False)
    if error:
        return jsonify({"error": error, "node": NODE_NAME}), 400

    applied = apply_status(status)
    replication = replicate_to_peers(status) if applied else []
    print(f"[{NODE_NAME}] Status verarbeitet: {status['username']} | applied={applied}")

    return jsonify({
        "message": "Status gespeichert" if applied else "Aelteres Update ignoriert",
        "node": NODE_NAME,
        "status": status,
        "applied": applied,
        "replication": replication,
    }), 201 if applied else 200


@app.route("/replicate", methods=["POST"])
def replicate():
    status, error = normalize_status(request.get_json(silent=True), allow_deleted=True)
    if error:
        return jsonify({"error": error, "node": NODE_NAME}), 400

    applied = apply_status(status)
    print(f"[{NODE_NAME}] Replikation empfangen: {status['username']} | applied={applied}")
    return jsonify({"message": "Replikation verarbeitet", "node": NODE_NAME, "applied": applied}), 200


@app.route("/status", methods=["GET"])
def get_all():
    if not READY:
        return _not_ready_response()
    return jsonify(visible_statuses()), 200


@app.route("/status/<username>", methods=["GET"])
def get_one(username):
    if not READY:
        return _not_ready_response()
    status = statuses.get(username)
    if not status or status.get("deleted", False):
        return jsonify({"error": "Nicht gefunden", "node": NODE_NAME}), 404
    return jsonify(status), 200


@app.route("/status/<username>", methods=["DELETE"])
def delete_one(username):
    if not READY:
        return _not_ready_response()
    tombstone = {
        "username": username.strip(),
        "statustext": "",
        "uhrzeit": now_iso(),
        "latitude": None,
        "longitude": None,
        "deleted": True,
        "originNode": NODE_NAME,
    }
    if not tombstone["username"]:
        return jsonify({"error": "username erforderlich", "node": NODE_NAME}), 400

    applied = apply_status(tombstone)
    replication = replicate_to_peers(tombstone) if applied else []
    print(f"[{NODE_NAME}] Status geloescht: {tombstone['username']} | applied={applied}")
    return jsonify({
        "message": "Status geloescht" if applied else "Aeltere Loeschung ignoriert",
        "node": NODE_NAME,
        "status": tombstone,
        "applied": applied,
        "replication": replication,
    }), 200


@app.route("/internal/snapshot", methods=["GET"])
def snapshot():
    return jsonify({"node": NODE_NAME, "statuses": list(statuses.values())}), 200


@app.route("/health", methods=["GET"])
def health():
    # Always 200 for container liveness; `ready`/`state` show grace-period status.
    return jsonify({
        "node": NODE_NAME,
        "status": "ok",
        "ready": READY,
        "state": NODE_STATE,
        "entries": len(visible_statuses()),
        "storedObjects": len(statuses),
        "peers": PEER_URLS,
        "pendingReplications": len(pending_replications),
    }), 200


def parse_peers(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [peer.strip().rstrip("/") for peer in raw.split(",") if peer.strip()]


# Ensure a usable (in-memory) database exists as soon as the module is imported,
# so the Flask app works in tests without an explicit init_db() call.
if _conn is None:
    init_db(DB_PATH)


if __name__ == "__main__":
    # Configuration is read from environment variables first (Docker Compose) and
    # falls back to positional CLI arguments for simple local runs.
    port = int(os.environ.get("PORT") or (sys.argv[1] if len(sys.argv) > 1 else "5000"))
    PEER_URLS = parse_peers(os.environ.get("PEERS") or (sys.argv[2] if len(sys.argv) > 2 else ""))
    NODE_NAME = os.environ.get("NODE_NAME") or (sys.argv[3] if len(sys.argv) > 3 else f"Node-{port}")
    db_path = os.environ.get("DB_PATH") or (sys.argv[4] if len(sys.argv) > 4 else f"{NODE_NAME}.db")

    init_db(db_path)
    print(f"[{NODE_NAME}] Starte auf Port {port} | Peers: {PEER_URLS or 'keine'} | DB: {db_path}")

    # Bootstrap runs in the background so /replicate, /internal/snapshot and
    # /health stay reachable for peers while client endpoints are gated.
    threading.Thread(target=run_bootstrap, daemon=True).start()
    threading.Thread(target=retry_worker, daemon=True).start()

    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
