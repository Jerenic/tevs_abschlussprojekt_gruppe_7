# Status Server PoC (historisch)

> Hinweis: Dieser Ordner dokumentiert nur noch den urspruenglichen Proof of Concept.
> Der produktive Code liegt inzwischen unter `backend/` (Statusnode-Paket) und
> `frontend/` (Demo-Frontend). Gestartet wird das System ausschliesslich ueber das
> Repository-Root mit `docker compose up --build`.

## Was hier dokumentiert ist

Der PoC zeigte urspruenglich die Grundidee: ein Client sendet einen Status an eine
Node, die ihn lokal speichert und an eine zweite Node repliziert. Daraus wurde das
verteilte Commandcenter mit drei replizierenden Statusnodes hinter einem NGINX
Loadbalancer.

## Aktuelle Einstiegspunkte

- Anwendung starten: `docker compose up --build` (Root), danach `http://localhost:8888`
- Backend-Code: `backend/status_node/`
- Frontend: `frontend/index.html`
- Architektur und Details: `docs/architecture-blueprint.md`
