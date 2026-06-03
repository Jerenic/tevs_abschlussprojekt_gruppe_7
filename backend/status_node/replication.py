from __future__ import annotations

import threading
import time
from typing import Any

import requests

from status_node import config

# Replications that failed are queued here and retried by a background worker,
# so a temporarily unreachable peer neither loses updates nor breaks the client write.
pending_replications: list[dict[str, Any]] = []
_pending_lock = threading.Lock()


def _enqueue_pending(peer_url: str, status: dict[str, Any]) -> None:
    with _pending_lock:
        username = status["username"]
        # Keep only the newest pending update per peer+username (LWW for retries too).
        pending_replications[:] = [
            item for item in pending_replications
            if not (item["peer"] == peer_url and item["status"]["username"] == username)
        ]
        pending_replications.append({"peer": peer_url, "status": status})


def replicate_to_peers(status: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for peer_url in config.PEER_URLS:
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
    interval = config.RETRY_INTERVAL if interval is None else interval
    while True:
        time.sleep(interval)
        if pending_replications:
            process_pending()
