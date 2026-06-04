# TEVS Abschlussprojekt - Gruppe 7

Verteiltes Commandcenter fuer die Lehrveranstaltung Technologien verteilter Systeme. Das System besteht aus mehreren gleichwertigen Statusnodes hinter einem NGINX-Loadbalancer. Clients setzen, aendern, lesen und loeschen Statusmeldungen mit Geodaten ueber eine zentrale URL. Die Nodes replizieren Schreiboperationen untereinander und halten die Daten eventual-consistent.

## Aktueller Stand

- NGINX Loadbalancer als Single Point of Access ueber **HTTPS/TLS** (`https://localhost:8443`)
- Drei gleichwertige Flask-Statusnodes (`node-a`, `node-b`, `node-c`)
- REST-Kommunikation zwischen Frontend, Loadbalancer und Statusnodes
- Push-Replikation zwischen den Statusnodes mit Last-Writer-Wins
- SQLite-Persistenz pro Node (eigene DB-Datei je Node, kein Shared-DB)
- Initial-Sync (Bootstrapping) mit Grace Period beim Node-Start
- Retry-Queue fuer fehlgeschlagene Replikation
- Delete als repliziertes Tombstone (keine Wiederauferstehung geloeschter Eintraege)
- Web-Frontend mit Leaflet-Kartenansicht: Status setzen/aendern/loeschen, globaler Feed, Marker fuer alle Meldungen, Koordinaten per Kartenklick

## Architektur in Kurzform

```text
Browser  --HTTPS-->  NGINX Loadbalancer (:8443)  --HTTP-->  node-a / node-b / node-c (Flask :5000)
                            |                                     \___ Peer-Replikation (REST) ___/
                            '-> liefert das Frontend (HTML + Leaflet)
```

Der Browser spricht den Loadbalancer ausschliesslich verschluesselt (TLS) an. Die
Replikation zwischen den Nodes laeuft im internen, nicht nach aussen exponierten
Docker-Netzwerk.

## Projektstruktur

```text
backend/
  status_node/        Flask StatusNode als Python-Paket
    app.py            Flask-App, Routes, Einstiegspunkt (python -m status_node.app)
    config.py         Env-/CLI-Konfiguration (Port, Peers, DB-Pfad, Intervalle)
    models.py         Validierung, Zeitstempel, Last-Writer-Wins-Vergleich
    storage.py        SQLite-Persistenz und In-Memory-Lesecache
    replication.py    Peer-Replikation, Pending-Queue, Retry-Worker
    bootstrap.py      Snapshot-Abruf, Initial-Sync, Grace-Period-Status
  requirements.txt
frontend/
  index.html          Web-Frontend (HTML + Leaflet-Karte), spricht nur /api/...
loadbalancer/
  nginx.conf          NGINX Upstream, TLS-Terminierung, Routing, Failover
  certs/              selbstsigniertes TLS-Zertifikat (Dev)
tests/
docs/
Dockerfile
docker-compose.yml
```

Der produktive Code liegt unter `backend/`.

### Replikation

Eine Node, die einen Client-Schreibzugriff (`POST`/`DELETE`) erhaelt, speichert lokal und schickt das Statusobjekt per `POST /replicate` an ihre Peers. Empfangende Nodes validieren das Update und uebernehmen es nur, wenn es gewinnt (siehe Konfliktaufloesung). Es wird keine externe Replikationsbibliothek verwendet, die Logik liegt vollstaendig in `backend/status_node/replication.py` und `models.py`.

### Konfliktaufloesung (Last-Writer-Wins)

Pro `username` existiert genau ein Eintrag. Bei konkurrierenden Updates gewinnt der juengere `uhrzeit`-Zeitstempel. Bei exakt gleichem Zeitstempel entscheidet deterministisch der `originNode`, damit alle Nodes unabhaengig von der Eintreffreihenfolge zum selben Ergebnis konvergieren. Aeltere Updates werden verworfen.

### Persistenz

Jede Node haelt einen In-Memory-Cache und spiegelt jeden Schreibvorgang in eine eigene lokale SQLite-Datei (`/data/status.db` im Container, eigenes Docker-Volume je Node). Nach einem Neustart laedt die Node ihren letzten Stand aus SQLite. Es gibt keine gemeinsame oder verteilte Datenbank.

### Initial-Sync / Bootstrapping

Beim Start ist eine Node in einer Grace Period (`state=bootstrapping`). Sie zieht Snapshots ihrer Peers (`GET /internal/snapshot`) und merged diese per Last-Writer-Wins in den eigenen Stand. Waehrend der Grace Period antworten die Client-Endpunkte mit HTTP 503, waehrend `/replicate`, `/internal/snapshot` und `/health` erreichbar bleiben. Danach wechselt die Node auf `state=ready`.

### Loadbalancer und Ausfallverhalten

Der Browser spricht ausschliesslich den Loadbalancer an. NGINX verteilt `/api/...`-Requests per Round-Robin auf die Nodes. Faellt eine Node aus, markiert NGINX sie als nicht verfuegbar und leitet auf die verbleibenden Nodes um (`proxy_next_upstream`, inkl. nicht-idempotenter Requests). Der Nutzer behaelt dieselbe URL. Schlaegt die Peer-Replikation kurzzeitig fehl, bleibt der Client-Request trotzdem erfolgreich und das Update wird ueber die Retry-Queue nachgeliefert.

### Transportverschluesselung (TLS)

Der Loadbalancer terminiert TLS und ist nur ueber HTTPS erreichbar (ein
einzelner HTTPS-Listener, kein HTTP). Verwendet wird ein selbstsigniertes
Zertifikat unter `loadbalancer/certs/` (Details und Neuerzeugung siehe
`loadbalancer/certs/README.md`). Browser zeigen dafuer eine erwartbare
Sicherheitswarnung; bei `curl` wird `-k` benoetigt. Frontend <-> Loadbalancer
sowie alle REST-Schnittstellen laufen damit verschluesselt. Die
Node-zu-Node-Replikation laeuft im internen, nicht exponierten Docker-Netzwerk.

## Start

```bash
docker compose up --build
```

Anwendung: `https://localhost:8443` (selbstsigniertes Zertifikat im Browser akzeptieren)

Loadbalancer-Health:

```bash
curl -k https://localhost:8443/lb-health
```

Der Loadbalancer-Port ist optional ueber `.env` (`LOADBALANCER_PORT`) konfigurierbar.

### Eine Node lokal ohne Docker starten

```bash
pip install -r backend/requirements.txt
cd backend
python -m status_node.app 5000 "" Node-A node-a.db
```

Die Argumente sind optional: `Port`, `Peers` (kommagetrennt), `NodeName`, `DB-Pfad`. Alternativ koennen `PORT`, `PEERS`, `NODE_NAME` und `DB_PATH` als Umgebungsvariablen gesetzt werden.

## Demo-Ablauf

1. `docker compose up --build` starten.
2. Browser auf `https://localhost:8443` oeffnen und das selbstsignierte Zertifikat akzeptieren.
3. Status absenden (Koordinaten per Kartenklick setzbar) und im Feed sowie als Marker auf der Karte pruefen.
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
| `loadbalancer/nginx.conf` | NGINX Upstream, TLS-Terminierung, Routing und Failover |
| `loadbalancer/certs/` | Selbstsigniertes TLS-Zertifikat (Dev) |
| `backend/status_node/` | Flask StatusNode in Modulen (siehe unten) |
| `backend/requirements.txt` | Python-Abhaengigkeiten der Statusnode |
| `frontend/index.html` | Web-Frontend mit Leaflet-Karte (spricht nur `/api/...`) |
| `tests/test_status_node.py` | Unit- und Verhaltenstests |
| `docs/architecture-blueprint.md` | Architektur-Blueprint |
| `docs/aufgabe-3-loadbalancer.md` | Aufgabe-3-Dokumentation |
| `docs/test-plan.md` | Test- und Akzeptanzplan |
| `docs/frontend-konzept.md` | Frontend-Konzept und Umsetzung |

## Optionale Erweiterungen (kein Pflichtteil)

- Hochverfuegbarer Loadbalancer (Aktiv/Passiv), um den letzten SPoF zu eliminieren
- TLS auch fuer die Node-zu-Node-Replikation (aktuell internes Docker-Netz)
