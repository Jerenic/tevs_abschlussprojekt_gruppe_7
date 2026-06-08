from __future__ import annotations

import os
import sys

# Runtime configuration as module-level attributes. Other modules read the
# current values via ``config.<NAME>`` so a later ``load()`` (or a test
# overriding an attribute) is seen everywhere without re-importing.
NODE_NAME = "Node"
PEER_URLS: list[str] = []
PORT = 5000
DB_PATH = ":memory:"
BOOTSTRAP_TIMEOUT = float(os.environ.get("BOOTSTRAP_TIMEOUT", "8"))
RETRY_INTERVAL = float(os.environ.get("RETRY_INTERVAL", "5"))
TLS_CERT_PATH = ""
TLS_KEY_PATH = ""
PEER_TLS_VERIFY = True


def parse_peers(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [peer.strip().rstrip("/") for peer in raw.split(",") if peer.strip()]


def parse_bool(raw: str | None, default: bool = True) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def load(argv: list[str] | None = None) -> None:
    """Read configuration from environment variables first, then positional CLI args.

    Env wins so Docker Compose stays declarative; the CLI fallback keeps simple
    local runs (``python -m status_node.app 5000 http://peer:5000 Node-A db``) working.
    """
    global NODE_NAME, PEER_URLS, PORT, DB_PATH, BOOTSTRAP_TIMEOUT, RETRY_INTERVAL
    global TLS_CERT_PATH, TLS_KEY_PATH, PEER_TLS_VERIFY
    argv = sys.argv if argv is None else argv

    PORT = int(os.environ.get("PORT") or (argv[1] if len(argv) > 1 else "5000"))
    PEER_URLS = parse_peers(os.environ.get("PEERS") or (argv[2] if len(argv) > 2 else ""))
    NODE_NAME = os.environ.get("NODE_NAME") or (argv[3] if len(argv) > 3 else f"Node-{PORT}")
    DB_PATH = os.environ.get("DB_PATH") or (argv[4] if len(argv) > 4 else f"{NODE_NAME}.db")
    BOOTSTRAP_TIMEOUT = float(os.environ.get("BOOTSTRAP_TIMEOUT", BOOTSTRAP_TIMEOUT))
    RETRY_INTERVAL = float(os.environ.get("RETRY_INTERVAL", RETRY_INTERVAL))
    TLS_CERT_PATH = os.environ.get("TLS_CERT_PATH", "")
    TLS_KEY_PATH = os.environ.get("TLS_KEY_PATH", "")
    PEER_TLS_VERIFY = parse_bool(os.environ.get("PEER_TLS_VERIFY"), True)
