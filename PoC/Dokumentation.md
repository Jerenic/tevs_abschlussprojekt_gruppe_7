# Dokumentation - Loadbalanced Status Server (historische PoC-Notiz)

> Hinweis: Der produktive Code liegt inzwischen unter `backend/status_node/` und
> `frontend/`. Diese Notiz beschreibt den Architektur- und Ablaufstand, der aus dem
> PoC hervorgegangen ist.

Statt zwei direkt erreichbaren Nodes gibt es drei Statusnodes hinter einem NGINX Loadbalancer. Nutzer greifen nur noch ueber `http://localhost:8888` auf das System zu.

## Architektur

```text
Browser
  |
  v
NGINX Loadbalancer (:8888)
  |-- Frontend ausliefern
  |-- /api/status -> node-a / node-b / node-c

StatusNode A <-> StatusNode B
StatusNode A <-> StatusNode C
StatusNode B <-> StatusNode C
```

## Ablauf

1. Das Frontend sendet einen Status per `POST /api/status` an den Loadbalancer.
2. NGINX leitet den Request an eine der aktiven Statusnodes weiter.
3. Die Statusnode speichert lokal und repliziert den Datensatz per `POST /replicate` an ihre Peers.
4. `GET /api/status` liefert den aktuellen Feed ueber den Loadbalancer zurueck.
5. Wenn eine Node ausfaellt, verteilt NGINX Requests auf die verbleibenden Nodes.

## Persistenz, Bootstrap und Fehlertoleranz

- Jede Node speichert ihren Stand persistent in einer eigenen SQLite-Datei (kein Shared-DB).
- Beim Start zieht eine Node in einer Grace Period Snapshots der Peers und merged sie per Last-Writer-Wins.
- Schlaegt die Replikation an einen Peer fehl, wird sie eingereiht und durch einen Retry-Worker nachgeliefert.
- Konflikte werden deterministisch ueber `uhrzeit` (Last-Writer-Wins) aufgeloest; Deletes sind replizierte Tombstones.

## Weitere Dokumente

- `../docs/architecture-blueprint.md`
- `../docs/aufgabe-3-loadbalancer.md`
- `../docs/test-plan.md`
