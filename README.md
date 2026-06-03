# TEVS Abschlussprojekt - Gruppe 7

Verteiltes Commandcenter fuer die Lehrveranstaltung Technologien verteilter Systeme. Das System besteht aus mehreren gleichwertigen Statusnodes hinter einem NGINX-Loadbalancer. Clients setzen, aendern, lesen und loeschen Statusmeldungen mit Geodaten ueber eine zentrale URL. Die Nodes replizieren Schreiboperationen untereinander und halten die Daten eventual-consistent.

## Aktueller Stand

- NGINX Loadbalancer als Single Point of Access (`http://localhost:8888`)
- Drei gleichwertige Flask-Statusnodes (`node-a`, `node-b`, `node-c`)
- REST-Kommunikation zwischen Frontend, Loadbalancer und Statusnodes
- Push-Replikation zwischen den Statusnodes mit Last-Writer-Wins
- SQLite-Persistenz pro Node (eigene DB-Datei je Node, kein Shared-DB)
- Initial-Sync (Bootstrapping) mit Grace Period beim Node-Start
- Retry-Queue fuer fehlgeschlagene Replikation
- Delete als repliziertes Tombstone (keine Wiederauferstehung geloeschter Eintraege)
- Statisches Demo-Frontend (das finale React/Leaflet-Frontend ist offener Arbeitspunkt)

## Architektur in Kurzform

```text
Browser  ->  NGINX Loadbalancer (:8888)  ->  node-a / node-b / node-c (Flask :5000)
                     |                              \___ Peer-Replikation (REST) ___/
                     '-> liefert statisches Frontend
```

### Replikation

Eine Node, die einen Client-Schreibzugriff (`POST`/`DELETE`) erhaelt, speichert lokal und schickt das Statusobjekt per `POST /replicate` an ihre Peers. Empfangende Nodes validieren das Update und uebernehmen es nur, wenn es gewinnt (siehe Konfliktaufloesung). Es wird keine externe Replikationsbibliothek verwendet, die Logik liegt vollstaendig in `node.py`.

### Konfliktaufloesung (Last-Writer-Wins)

Pro `username` existiert genau ein Eintrag. Bei konkurrierenden Updates gewinnt der juengere `uhrzeit`-Zeitstempel. Bei exakt gleichem Zeitstempel entscheidet deterministisch der `originNode`, damit alle Nodes unabhaengig von der Eintreffreihenfolge zum selben Ergebnis konvergieren. Aeltere Updates werden verworfen.

### Persistenz

Jede Node haelt einen In-Memory-Cache und spiegelt jeden Schreibvorgang in eine eigene lokale SQLite-Datei (`/data/status.db` im Container, eigenes Docker-Volume je Node). Nach einem Neustart laedt die Node ihren letzten Stand aus SQLite. Es gibt keine gemeinsame oder verteilte Datenbank.

### Initial-Sync / Bootstrapping

Beim Start ist eine Node in einer Grace Period (`state=bootstrapping`). Sie zieht Snapshots ihrer Peers (`GET /internal/snapshot`) und merged diese per Last-Writer-Wins in den eigenen Stand. Waehrend der Grace Period antworten die Client-Endpunkte mit HTTP 503, waehrend `/replicate`, `/internal/snapshot` und `/health` erreichbar bleiben. Danach wechselt die Node auf `state=ready`.

### Loadbalancer und Ausfallverhalten

Der Browser spricht ausschliesslich den Loadbalancer an. NGINX verteilt `/api/...`-Requests per Round-Robin auf die Nodes. Faellt eine Node aus, markiert NGINX sie als nicht verfuegbar und leitet auf die verbleibenden Nodes um (`proxy_next_upstream`, inkl. nicht-idempotenter Requests). Der Nutzer behaelt dieselbe URL. Schlaegt die Peer-Replikation kurzzeitig fehl, bleibt der Client-Request trotzdem erfolgreich und das Update wird ueber die Retry-Queue nachgeliefert.

## Start

```bash
docker compose up --build
```

Anwendung: `http://localhost:8888`

Loadbalancer-Health:

```bash
curl http://localhost:8888/lb-health
```

Der Loadbalancer-Port ist optional ueber `.env` (`LOADBALANCER_PORT`) konfigurierbar.

## Aufgabe-3-Demo

1. `docker compose up --build` starten.
2. Browser auf `http://localhost:8888` oeffnen.
3. Status absenden und im Feed pruefen.
4. Anzeige "Letzte Backend-Antwort" beobachten (wechselnde Node).
5. Eine Node stoppen: `docker compose stop node-a`.
6. Weiter ueber dieselbe URL arbeiten - NGINX nutzt die verbleibenden Nodes.
7. Node wieder starten: `docker compose start node-a`. Sie holt sich den aktuellen Stand per Initial-Sync.

## Tests

```bash
python -m unittest discover -s tests
```

Die Suite deckt CRUD, Validierung, Last-Writer-Wins (inkl. Tiebreak), Tombstones, SQLite-Persistenz, Bootstrapping und die Retry-Queue ab.

## Wichtige Dateien

| Datei | Zweck |
|---|---|
| `Dockerfile` | Image fuer eine Statusnode |
| `docker-compose.yml` | Drei Nodes plus Loadbalancer, Volumes pro Node |
| `loadbalancer/nginx.conf` | NGINX Upstream, Routing und Failover |
| `PoC/backend/node.py` | Flask StatusNode (CRUD, Replikation, Persistenz, Bootstrap, Retry) |
| `PoC/frontend/index.html` | Statisches Demo-Frontend (spricht nur `/api/...`) |
| `tests/test_status_node.py` | Unit- und Verhaltenstests |
| `docs/architecture-blueprint.md` | Architektur-Blueprint |
| `docs/aufgabe-3-loadbalancer.md` | Aufgabe-3-Dokumentation |
| `docs/test-plan.md` | Test- und Akzeptanzplan |
| `docs/frontend-konzept.md` | Konzept fuer das finale Frontend |

## Noch offen fuer das finale Projekt

- Finales React/Leaflet-Frontend mit Kartenansicht (eigener Arbeitspunkt)
- TLS am Loadbalancer (Bonuspunkt laut Aufgabe 3)
- Optional: hochverfuegbarer Loadbalancer (Aktiv/Passiv)
