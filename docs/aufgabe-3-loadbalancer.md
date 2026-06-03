# Aufgabe 3 - Loadbalancer-Implementierung

## Ziel

Der Statusserver wurde um einen Loadbalancer erweitert. Nutzer greifen nur noch ueber eine zentrale URL auf das System zu. Der Loadbalancer liefert das Frontend aus und verteilt API-Requests auf mehrere Statusnodes. Faellt eine Node aus, uebernehmen die verbleibenden Nodes ohne Eingriff des Nutzers.

## Technologieentscheidung

Als Loadbalancer wird NGINX verwendet. NGINX ist passend, weil es leicht in Docker Compose integrierbar ist, statische Dateien ausliefert und HTTP-Requests per Upstream-Konfiguration auf mehrere Backends verteilt. Fuer den Pflichtteil reicht eine einfache Round-Robin-Konfiguration. Ist eine Node nicht erreichbar oder antwortet sie mit einem Fehler, leitet NGINX automatisch auf eine andere Node aus dem Upstream weiter.

## Konfiguration im Ueberblick

- `upstream status_nodes` buendelt `node-a`, `node-b`, `node-c` (jeweils Port 5000). `max_fails=1` und `fail_timeout=5s` sorgen fuer schnelles Failover.
- `location /api/` proxyt auf den Upstream und entfernt das `/api`-Praefix (`/api/status` -> `/status`).
- `proxy_next_upstream error timeout http_500 http_502 http_503 http_504 non_idempotent` leitet auch `POST`/`DELETE` auf eine andere Node um, wenn die erste Node ausfaellt oder noch im Bootstrap (HTTP 503) ist. `proxy_next_upstream_tries 3` begrenzt die Versuche.
- `location = /lb-health` liefert einen einfachen `ok`-Healthcheck des Loadbalancers.
- `location /` liefert das statische Frontend (`index.html`).

Das erneute Senden eines Schreibrequests an eine andere Node ist sicher, weil die Nodes Updates per Last-Writer-Wins idempotent uebernehmen.

## Start

```bash
docker compose up --build
```

Danach ist die Anwendung erreichbar unter:

```text
http://localhost:8888
```

Der Port ist optional ueber `.env` konfigurierbar:

```text
LOADBALANCER_PORT=8888
```

## Demo-Ablauf

1. `docker compose up --build` starten.
2. Browser auf `http://localhost:8888` oeffnen.
3. Status im Formular absenden.
4. Im Feed pruefen, dass der Status sichtbar ist.
5. Mehrfach aktualisieren und auf "Letzte Backend-Antwort" achten (wechselnde Node).
6. Eine Node stoppen: `docker compose stop node-a`.
7. Weiterhin ueber dieselbe URL Status abrufen oder senden - NGINX nutzt die verbleibenden Nodes.
8. Node wieder starten: `docker compose start node-a`. Sie holt den aktuellen Stand per Initial-Sync nach.

## Erfuellte Pflichtpunkte

| Pflichtpunkt | Umsetzung |
|---|---|
| Loadbalancer-Technologie | NGINX |
| Single Point of Access | `http://localhost:8888` |
| Traffic-Verteilung | NGINX Upstream `node-a`, `node-b`, `node-c` (Round-Robin) |
| Ausfallsicherheit einzelner Nodes | `proxy_next_upstream` leitet auf verbleibende Nodes um, inkl. Schreibrequests |
| Mehrere Statusserver-Nodes | Drei gleichartige Flask-Nodes mit eigener SQLite-Persistenz |

## Zusammenspiel mit der Backend-Fehlertoleranz

Der Loadbalancer deckt den Ausfall auf der Zugriffsebene ab. Auf Datenebene ergaenzen die Nodes das durch Persistenz (SQLite pro Node), Initial-Sync beim Neustart und eine Retry-Queue fuer fehlgeschlagene Replikation. Zusammen erfuellt das die Anforderung, dass ein Einzelausfall weder den Dienst stoppt noch zu Datenverlust fuehrt.

## Grenzen des aktuellen Arbeitsstands

Der Loadbalancer selbst ist noch nicht redundant ausgelegt; das ist laut Aufgabe fuer den Pflichtteil erlaubt. TLS am Loadbalancer ist als Bonuspunkt vorgesehen und noch nicht aktiviert. Ein hochverfuegbares Aktiv/Passiv-Setup mit virtueller IP waere der naechste Bonus-Schritt.
