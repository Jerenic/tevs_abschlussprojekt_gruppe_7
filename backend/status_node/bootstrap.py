from __future__ import annotations

import time
from typing import Any

import requests
from urllib3.exceptions import InsecureRequestWarning

from status_node import config, models, storage

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

# Grace-period state. A freshly started node first pulls peer snapshots before
# it answers client traffic. Defaults to ready so imports/tests are not gated.
READY = True
NODE_STATE = "ready"


def fetch_snapshot(peer_url: str, timeout: float = 3.0) -> list[dict[str, Any]] | None:
    try:
        response = requests.get(
            f"{peer_url}/internal/snapshot",
            timeout=timeout,
            verify=config.PEER_TLS_VERIFY,
        )
        if not response.ok:
            return None
        data = response.json()
        return data.get("statuses", []) if isinstance(data, dict) else []
    except (requests.RequestException, ValueError):
        return None


def bootstrap_from_peers(peers: list[str] | None = None, timeout: float | None = None) -> int:
    """Initial sync: merge peer snapshots into the local store using LWW.

    Tries each peer until it answers or the timeout elapses. Returns the number
    of applied (won) status objects. Unreachable peers are skipped, so a first
    node without reachable peers proceeds with its own persisted data.
    """
    peers = config.PEER_URLS if peers is None else peers
    timeout = config.BOOTSTRAP_TIMEOUT if timeout is None else timeout
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
                normalized, error = models.normalize_status(
                    raw, allow_deleted=True, default_origin=config.NODE_NAME
                )
                if error:
                    continue
                if storage.apply_status(normalized):
                    applied += 1
            outstanding.discard(peer)
        if outstanding:
            time.sleep(0.5)

    return applied


def run_bootstrap() -> None:
    global READY, NODE_STATE
    READY = False
    NODE_STATE = "bootstrapping"
    try:
        count = bootstrap_from_peers()
        print(f"[{config.NODE_NAME}] Bootstrap abgeschlossen: {count} Status übernommen")
    finally:
        READY = True
        NODE_STATE = "ready"
