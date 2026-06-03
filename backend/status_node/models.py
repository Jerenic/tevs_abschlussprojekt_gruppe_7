from __future__ import annotations

import datetime
from typing import Any


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


def normalize_status(
    data: Any,
    *,
    allow_deleted: bool = False,
    default_origin: str = "Node",
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate raw input and return a canonical status dict, or an error message.

    ``allow_deleted`` is only set for replication/bootstrap so a client cannot
    push a tombstone directly via ``POST /status``.
    """
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
        "originNode": data.get("originNode") or default_origin,
    }, None


def is_newer(incoming: dict[str, Any], existing: dict[str, Any] | None) -> bool:
    """Last-Writer-Wins comparison based on ``uhrzeit``.

    Newer timestamp wins. On an exact tie we break deterministically by
    ``originNode`` so every node converges to the same winner regardless of the
    order in which replicated updates arrive. Unparseable timestamps are treated
    as "apply" to avoid silently dropping data.
    """
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
