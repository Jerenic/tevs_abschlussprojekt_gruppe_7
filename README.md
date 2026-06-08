# TEVS Abschlussprojekt - Gruppe 7

Dieses Repo enthält unser verteiltes Commandcenter für TEVS. Nutzer arbeiten über eine zentrale HTTPS-URL, dahinter verteilt NGINX die Requests auf drei gleichwertige Statusnodes. Jeder Status enthält Text, Username, Zeitstempel und Geokoordinaten. Schreibzugriffe werden zwischen den Nodes repliziert, damit ein Node-Ausfall nicht direkt zu Datenverlust oder einem Systemstopp führt.

## Aktueller Stand

- Zentrale URL über NGINX und HTTPS/TLS (`https://localhost:8443`)
- Drei Flask-Statusnodes: `node-a`, `node-b`, `node-c`
- HTTPS/REST zwischen Browser, Loadbalancer und Nodes
- Push-Replikation mit Last-Writer-Wins
- Eigene SQLite-Datei pro Node, keine gemeinsame Datenbank
- Initial-Sync beim Node-Start
- Retry-Queue für fehlgeschlagene Replikation
- Delete als Tombstone, damit gelöschte Einträge nicht wieder auftauchen
- Web-Frontend mit Leaflet-Karte, Status-Feed und Formular

## Architektur in Kurzform

```text
Browser  --HTTPS-->  NGINX Loadbalancer (:8443)  --HTTPS-->  node-a / node-b / node-c (Flask :5000)
                            |                                      \___ Peer-Replikation (HTTPS/REST) ___/
                            '-> liefert das Frontend (HTML + Leaflet)
```

Der Browser spricht den Loadbalancer ausschließlich verschlüsselt (TLS) an.
Auch Loadbalancer -> Node und Node -> Node laufen über HTTPS/TLS im internen,
nicht nach außen exponierten Docker-Netzwerk.

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

Eine Node, die einen Client-Schreibzugriff (`POST`/`DELETE`) erhält, speichert lokal und schickt das Statusobjekt per `POST /replicate` an ihre Peers. Empfangende Nodes validieren das Update und übernehmen es nur, wenn es gewinnt (siehe Konfliktauflösung). Es wird keine externe Replikationsbibliothek verwendet, die Logik liegt vollständig in `backend/status_node/replication.py` und `models.py`.

### Konfliktauflösung (Last-Writer-Wins)

Pro `username` existiert genau ein Eintrag. Bei konkurrierenden Updates gewinnt der jüngere `uhrzeit`-Zeitstempel. Bei exakt gleichem Zeitstempel entscheidet deterministisch der `originNode`, damit alle Nodes unabhängig von der Eintreffreihenfolge zum selben Ergebnis konvergieren. Ältere Updates werden verworfen.

### Persistenz

Jede Node hält einen In-Memory-Cache und spiegelt jeden Schreibvorgang in eine eigene lokale SQLite-Datei (`/data/status.db` im Container, eigenes Docker-Volume je Node). Nach einem Neustart lädt die Node ihren letzten Stand aus SQLite. Es gibt keine gemeinsame oder verteilte Datenbank.

### Initial-Sync / Bootstrapping

Beim Start ist eine Node in einer Grace Period (`state=bootstrapping`). Sie zieht Snapshots ihrer Peers (`GET /internal/snapshot`) und merged diese per Last-Writer-Wins in den eigenen Stand. Während der Grace Period antworten die Client-Endpunkte mit HTTP 503, während `/replicate`, `/internal/snapshot` und `/health` erreichbar bleiben. Danach wechselt die Node auf `state=ready`.

### Loadbalancer und Ausfallverhalten

Der Browser spricht ausschließlich den Loadbalancer an. NGINX verteilt `/api/...`-Requests per Round-Robin auf die Nodes. Fällt eine Node aus, markiert NGINX sie als nicht verfügbar und leitet auf die verbleibenden Nodes um (`proxy_next_upstream`, inkl. nicht-idempotenter Requests). Der Nutzer behält dieselbe URL. Schlägt die Peer-Replikation kurzzeitig fehl, bleibt der Client-Request trotzdem erfolgreich und das Update wird über die Retry-Queue nachgeliefert.

### Transportverschlüsselung (TLS)

Der Loadbalancer und die Statusnodes nutzen HTTPS mit selbstsigniertem
Zertifikat aus `loadbalancer/certs/` (Details und Neuerzeugung siehe
`loadbalancer/certs/README.md`). Browser zeigen dafür eine erwartbare
Sicherheitswarnung; bei `curl` wird `-k` benötigt. Frontend <-> Loadbalancer,
Loadbalancer <-> StatusNode und StatusNode <-> StatusNode laufen damit
verschlüsselt. Im Compose-Setup ist die Zertifikatsprüfung für interne
Self-Signed-Verbindungen deaktiviert (`PEER_TLS_VERIFY=false`,
`proxy_ssl_verify off`), die Transportverschlüsselung bleibt aktiv.

## Start

```bash
docker compose up --build
```

Anwendung: `https://localhost:8443` (selbstsigniertes Zertifikat im Browser akzeptieren)

Loadbalancer-Health:

```bash
curl -k https://localhost:8443/lb-health
```

Der Loadbalancer-Port ist optional über `.env` (`LOADBALANCER_PORT`) konfigurierbar.

### Eine Node lokal ohne Docker starten

```bash
pip install -r backend/requirements.txt
cd backend
python -m status_node.app 5000 "" Node-A node-a.db
```

Die Argumente sind optional: `Port`, `Peers` (kommagetrennt), `NodeName`, `DB-Pfad`. Alternativ können `PORT`, `PEERS`, `NODE_NAME` und `DB_PATH` als Umgebungsvariablen gesetzt werden.

## Demo-Ablauf

1. `docker compose up --build` starten.
2. Browser auf `https://localhost:8443` öffnen und das selbstsignierte Zertifikat akzeptieren.
3. Status absenden (Koordinaten per Kartenklick setzbar) und im Feed sowie als Marker auf der Karte prüfen.
4. Anzeige "Letzte Backend-Antwort" beobachten (wechselnde Node).
5. Eine Node stoppen: `docker compose stop node-a`.
6. Weiter über dieselbe URL arbeiten - NGINX nutzt die verbleibenden Nodes.
7. Node wieder starten: `docker compose start node-a`. Sie holt sich den aktuellen Stand per Initial-Sync.

## Tests

```bash
python -m unittest discover -s tests
```

Die Suite deckt CRUD, Validierung, Last-Writer-Wins (inkl. Tiebreak), Tombstones, SQLite-Persistenz, Bootstrapping und die Retry-Queue ab.

## Wichtige Dateien

| Datei | Zweck |
|---|---|
| `Dockerfile` | Image für eine Statusnode |
| `docker-compose.yml` | Drei Nodes plus Loadbalancer, Volumes pro Node |
| `loadbalancer/nginx.conf` | NGINX Upstream, TLS-Terminierung, Routing und Failover |
| `loadbalancer/certs/` | Selbstsigniertes TLS-Zertifikat (Dev) |
| `backend/status_node/` | Flask StatusNode in Modulen (siehe unten) |
| `backend/requirements.txt` | Python-Abhängigkeiten der Statusnode |
| `frontend/index.html` | Web-Frontend mit Leaflet-Karte (spricht nur `/api/...`) |
| `tests/test_status_node.py` | Unit- und Verhaltenstests |
| `docs/architecture-blueprint.md` | Architektur-Blueprint |
| `docs/architecture-summary.pdf` | Kurze Architektur-Beschreibung als PDF für die Abgabe |
| `docs/aufgabe-3-loadbalancer.md` | Aufgabe-3-Dokumentation |
| `docs/test-plan.md` | Test- und Akzeptanzplan |
| `docs/frontend-konzept.md` | Frontend-Konzept und Umsetzung |

## Optionale Erweiterungen (kein Pflichtteil)

- Hochverfügbarer Loadbalancer (Aktiv/Passiv), um den letzten SPoF zu eliminieren
- Optional härtere Zertifikatsprüfung für interne TLS-Verbindungen mit eigener CA/SAN-Zertifikaten
