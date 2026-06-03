from __future__ import annotations

import threading

from flask import Flask, jsonify, request
from flask_cors import CORS

from status_node import bootstrap, config, models, replication, storage

app = Flask(__name__)
CORS(app)


def _not_ready_response():
    return jsonify({
        "error": "Node befindet sich im Bootstrap (Grace Period)",
        "node": config.NODE_NAME,
        "state": bootstrap.NODE_STATE,
    }), 503


@app.after_request
def add_node_header(response):
    response.headers["X-Status-Node"] = config.NODE_NAME
    return response


@app.route("/status", methods=["POST"])
def post_status():
    if not bootstrap.READY:
        return _not_ready_response()

    status, error = models.normalize_status(
        request.get_json(silent=True), allow_deleted=False, default_origin=config.NODE_NAME
    )
    if error:
        return jsonify({"error": error, "node": config.NODE_NAME}), 400

    applied = storage.apply_status(status)
    replication_result = replication.replicate_to_peers(status) if applied else []
    print(f"[{config.NODE_NAME}] Status verarbeitet: {status['username']} | applied={applied}")

    return jsonify({
        "message": "Status gespeichert" if applied else "Aelteres Update ignoriert",
        "node": config.NODE_NAME,
        "status": status,
        "applied": applied,
        "replication": replication_result,
    }), 201 if applied else 200


@app.route("/replicate", methods=["POST"])
def replicate():
    status, error = models.normalize_status(
        request.get_json(silent=True), allow_deleted=True, default_origin=config.NODE_NAME
    )
    if error:
        return jsonify({"error": error, "node": config.NODE_NAME}), 400

    applied = storage.apply_status(status)
    print(f"[{config.NODE_NAME}] Replikation empfangen: {status['username']} | applied={applied}")
    return jsonify({"message": "Replikation verarbeitet", "node": config.NODE_NAME, "applied": applied}), 200


@app.route("/status", methods=["GET"])
def get_all():
    if not bootstrap.READY:
        return _not_ready_response()
    return jsonify(storage.visible_statuses()), 200


@app.route("/status/<username>", methods=["GET"])
def get_one(username):
    if not bootstrap.READY:
        return _not_ready_response()
    status = storage.statuses.get(username)
    if not status or status.get("deleted", False):
        return jsonify({"error": "Nicht gefunden", "node": config.NODE_NAME}), 404
    return jsonify(status), 200


@app.route("/status/<username>", methods=["DELETE"])
def delete_one(username):
    if not bootstrap.READY:
        return _not_ready_response()

    cleaned = username.strip()
    if not cleaned:
        return jsonify({"error": "username erforderlich", "node": config.NODE_NAME}), 400

    tombstone = {
        "username": cleaned,
        "statustext": "",
        "uhrzeit": models.now_iso(),
        "latitude": None,
        "longitude": None,
        "deleted": True,
        "originNode": config.NODE_NAME,
    }
    applied = storage.apply_status(tombstone)
    replication_result = replication.replicate_to_peers(tombstone) if applied else []
    print(f"[{config.NODE_NAME}] Status geloescht: {tombstone['username']} | applied={applied}")

    return jsonify({
        "message": "Status geloescht" if applied else "Aeltere Loeschung ignoriert",
        "node": config.NODE_NAME,
        "status": tombstone,
        "applied": applied,
        "replication": replication_result,
    }), 200


@app.route("/internal/snapshot", methods=["GET"])
def snapshot():
    return jsonify({"node": config.NODE_NAME, "statuses": storage.snapshot()}), 200


@app.route("/health", methods=["GET"])
def health():
    # Always 200 for container liveness; `ready`/`state` reflect the grace period.
    return jsonify({
        "node": config.NODE_NAME,
        "status": "ok",
        "ready": bootstrap.READY,
        "state": bootstrap.NODE_STATE,
        "entries": len(storage.visible_statuses()),
        "storedObjects": len(storage.statuses),
        "peers": config.PEER_URLS,
        "pendingReplications": len(replication.pending_replications),
    }), 200


def main() -> None:
    config.load()
    storage.init_db(config.DB_PATH)
    print(f"[{config.NODE_NAME}] Starte auf Port {config.PORT} | "
          f"Peers: {config.PEER_URLS or 'keine'} | DB: {config.DB_PATH}")

    # Bootstrap and retry run in the background so /replicate, /internal/snapshot
    # and /health stay reachable for peers while client endpoints are gated.
    threading.Thread(target=bootstrap.run_bootstrap, daemon=True).start()
    threading.Thread(target=replication.retry_worker, daemon=True).start()

    app.run(host="0.0.0.0", port=config.PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()
