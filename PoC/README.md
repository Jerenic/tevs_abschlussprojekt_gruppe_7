# Status Server PoC

Der urspruengliche PoC wurde fuer Aufgabe 3 erweitert. Das Frontend spricht die Statusnodes nicht mehr direkt ueber einzelne Host-Ports an, sondern nutzt den zentralen Loadbalancer.

## Start

Vom Repository-Root aus starten:

```bash
docker compose up --build
```

Danach ist die Anwendung erreichbar unter:

```text
http://localhost:8888
```

## Komponenten

- `backend/node.py`: Flask StatusNode mit SQLite-Persistenz, Peer-Replikation, Initial-Sync und Retry-Queue
- `frontend/index.html`: statisches Frontend mit relativen `/api/...` Requests
- `../loadbalancer/nginx.conf`: NGINX Loadbalancer vor den Statusnodes
- `../docker-compose.yml`: Startet `node-a`, `node-b`, `node-c` und den Loadbalancer

## Hinweis

Direkter Zugriff auf einzelne Nodes ueber `localhost:5001` oder `localhost:5002` ist im aktuellen Aufgabe-3-Stand nicht mehr vorgesehen. Die zentrale URL ist der Loadbalancer.
