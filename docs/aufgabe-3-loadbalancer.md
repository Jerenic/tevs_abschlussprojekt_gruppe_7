# Aufgabe 3 - Loadbalancer-Implementierung

## Ziel

Der Statusserver wurde um einen Loadbalancer erweitert. Nutzer greifen nur noch über eine zentrale URL auf das System zu. Der Loadbalancer liefert das Frontend aus und verteilt API-Requests auf mehrere Statusnodes. Fällt eine Node aus, übernehmen die verbleibenden Nodes ohne Eingriff des Nutzers.

## Technologieentscheidung

Als Loadbalancer wird NGINX verwendet. NGINX ist passend, weil es leicht in Docker Compose integrierbar ist, statische Dateien ausliefert und HTTP-Requests per Upstream-Konfiguration auf mehrere Backends verteilt. Für den Pflichtteil reicht eine einfache Round-Robin-Konfiguration. Ist eine Node nicht erreichbar oder antwortet sie mit einem Fehler, leitet NGINX automatisch auf eine andere Node aus dem Upstream weiter.

## Konfiguration im Überblick

- `upstream status_nodes` bündelt `node-a`, `node-b`, `node-c` (jeweils Port 5000). `max_fails=1` und `fail_timeout=5s` sorgen für schnelles Failover.
- `location /api/` proxyt per HTTPS auf den Upstream und entfernt das `/api`-Präfix (`/api/status` -> `/status`).
- `proxy_next_upstream error timeout http_500 http_502 http_503 http_504 non_idempotent` leitet auch `POST`/`DELETE` auf eine andere Node um, wenn die erste Node ausfällt oder noch im Bootstrap (HTTP 503) ist. `proxy_next_upstream_tries 3` begrenzt die Versuche.
- `location = /lb-health` liefert einen einfachen `ok`-Healthcheck des Loadbalancers.
- `location /` liefert das Frontend (`index.html` inkl. Leaflet-Karte).
- Der Loadbalancer hat ausschließlich einen HTTPS-Listener (`listen 443 ssl`) mit selbstsigniertem Zertifikat aus `loadbalancer/certs/`; der Zugriff erfolgt also nur verschlüsselt.
- Die Statusnodes starten ebenfalls mit TLS-Zertifikat. Peer-Replikation, Bootstrap-Snapshots und Loadbalancer-Upstream laufen intern über HTTPS.

Das erneute Senden eines Schreibrequests an eine andere Node ist sicher, weil die Nodes Updates per Last-Writer-Wins idempotent übernehmen.

## Start

```bash
docker compose up --build
```

Danach ist die Anwendung erreichbar unter:

```text
https://localhost:8443
```

(Selbstsigniertes Zertifikat im Browser akzeptieren.) Der Port ist optional über `.env` konfigurierbar:

```text
LOADBALANCER_PORT=8443
```

## Demo-Ablauf

1. `docker compose up --build` starten.
2. Browser auf `https://localhost:8443` öffnen (Zertifikatswarnung akzeptieren).
3. Status im Formular absenden.
4. Im Feed prüfen, dass der Status sichtbar ist.
5. Mehrfach aktualisieren und auf "Letzte Backend-Antwort" achten (wechselnde Node).
6. Eine Node stoppen: `docker compose stop node-a`.
7. Weiterhin über dieselbe URL Status abrufen oder senden - NGINX nutzt die verbleibenden Nodes.
8. Node wieder starten: `docker compose start node-a`. Sie holt den aktuellen Stand per Initial-Sync nach.

## Erfüllte Pflichtpunkte

| Pflichtpunkt | Umsetzung |
|---|---|
| Loadbalancer-Technologie | NGINX |
| Single Point of Access | `https://localhost:8443` (TLS) |
| Traffic-Verteilung | NGINX Upstream `node-a`, `node-b`, `node-c` (Round-Robin) |
| Ausfallsicherheit einzelner Nodes | `proxy_next_upstream` leitet auf verbleibende Nodes um, inkl. Schreibrequests |
| Mehrere Statusserver-Nodes | Drei gleichartige Flask-Nodes mit eigener SQLite-Persistenz |
| TLS/SSL Bonus | HTTPS am Loadbalancer und auf den internen Node-Verbindungen |

## Zusammenspiel mit der Backend-Fehlertoleranz

Der Loadbalancer deckt den Ausfall auf der Zugriffsebene ab. Auf Datenebene ergänzen die Nodes das durch Persistenz (SQLite pro Node), Initial-Sync beim Neustart und eine Retry-Queue für fehlgeschlagene Replikation. Zusammen erfüllt das die Anforderung, dass ein Einzelausfall weder den Dienst stoppt noch zu Datenverlust führt.

## Grenzen des aktuellen Arbeitsstands

TLS ist am Loadbalancer und auf den Statusnodes aktiv (HTTPS mit
selbstsigniertem Zertifikat). Der Loadbalancer selbst ist noch nicht redundant
ausgelegt; das ist laut Aufgabe für den Pflichtteil erlaubt. Ein
hochverfügbares Aktiv/Passiv-Setup mit virtueller IP wäre der nächste
optionale Schritt.
