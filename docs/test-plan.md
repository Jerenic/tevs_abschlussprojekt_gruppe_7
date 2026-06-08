# Testplan - Loadbalanced Statusserver

## Ziel

Die Tests zeigen, dass der Loadbalancer sinnvoll vor den Statusnodes arbeitet und dass die Nodes Replikation, Persistenz, TLS-Transportverschluesselung, Konfliktaufloesung und Fehlertoleranz korrekt umsetzen. Der wichtigste Punkt fuer Aufgabe 3 ist, dass der User nur eine URL braucht und Node-Ausfaelle nicht manuell behandeln muss.

## Automatisierte Tests

Ausfuehren:

```bash
python -m unittest discover -s tests
```

Abgedeckte Bereiche in `tests/test_status_node.py`:

| Bereich | Was geprueft wird |
|---|---|
| CRUD | `POST`/`GET`/`GET <user>`/`DELETE` funktionieren wie erwartet |
| Validierung | fehlender `username`/`statustext`, ungueltige Koordinaten, ungueltige `uhrzeit`, `deleted` auf `/status`, Nicht-Objekt-Payload -> HTTP 400 |
| Replikation | Schreibzugriff repliziert an konfigurierte Peers (`/replicate`) |
| Last-Writer-Wins | juengeres Update gewinnt, aelteres wird ignoriert, deterministischer Tiebreak bei gleichem `uhrzeit` |
| Tombstones | Delete erzeugt Tombstone und blendet Status aus, repliziert das Tombstone, verhindert Wiederauferstehung durch alte Updates |
| Persistenz | Status und Tombstone ueberleben das erneute Oeffnen der SQLite-Datei (Neustart-Simulation) |
| Bootstrapping | Peer-Snapshot wird per LWW gemerged, juengerer lokaler Stand wird nicht ueberschrieben |
| Grace Period | Client-Endpunkte liefern waehrend des Bootstraps HTTP 503, `/health` und `/replicate` bleiben erreichbar |
| Retry-Queue | fehlgeschlagene Replikation wird eingereiht, bei Erreichbarkeit nachgeliefert, Dedup behaelt das neueste Update |

Transportverschluesselung wird zusaetzlich ueber die Docker-Konfiguration
geprueft: Frontend -> Loadbalancer, Loadbalancer -> StatusNode und StatusNode
-> StatusNode nutzen HTTPS. Wegen selbstsignierter Dev-Zertifikate wird bei
internen Verbindungen die Zertifikatspruefung deaktiviert, nicht die
Verschluesselung.

## Manuelle Akzeptanztests (mit Docker)

### 1. Compose startet erfolgreich

```bash
docker compose up --build
```

Erwartung: `node-a`, `node-b`, `node-c` und `loadbalancer` starten ohne Fehler. Die Anwendung ist unter `https://localhost:8443` erreichbar (selbstsigniertes Zertifikat, daher bei `curl` das Flag `-k`).

### 2. Loadbalancer-Health pruefen

```bash
curl -k https://localhost:8443/lb-health
```

Erwartung: Antwort ist `ok`.

### 3. Status ueber zentrale API anlegen

```bash
curl -k -X POST https://localhost:8443/api/status ^
  -H "Content-Type: application/json" ^
  -d "{\"username\":\"RECON-01\",\"statustext\":\"Am Weg zum Einsatz\",\"latitude\":48.215,\"longitude\":16.385}"
```

Erwartung: HTTP 201 und JSON-Antwort mit `node`, `status` und `replication`.

### 4. Status ueber zentrale API abrufen

```bash
curl -k https://localhost:8443/api/status
```

Erwartung: Der vorher angelegte Status ist im Feed enthalten. Bei mehrfacher Ausfuehrung kann die Antwort von unterschiedlichen Nodes kommen (Header `X-Status-Node`).

### 5. Node-Ausfall simulieren

```bash
docker compose stop node-a
curl -k https://localhost:8443/api/status
```

Erwartung: Die URL bleibt gleich und der Request wird von einer verbleibenden Node beantwortet.

### 6. Initial-Sync nach Neustart pruefen

```bash
docker compose start node-a
curl -k https://localhost:8443/api/status
```

Erwartung: Node-A laedt waehrend der Grace Period den aktuellen Stand von den Peers und liefert danach dieselben Daten.

### 7. Persistenz pruefen

```bash
docker compose restart node-b
```

Erwartung: Nach dem Neustart enthaelt Node-B weiterhin die zuvor gespeicherten Statusmeldungen (SQLite-Volume).

### 8. Delete wird repliziert

```bash
curl -k -X DELETE https://localhost:8443/api/status/RECON-01
curl -k https://localhost:8443/api/status
```

Erwartung: Der Status wird aus dem sichtbaren Feed entfernt und bleibt auch nach Replikation und Neustart entfernt.

### 9. Frontend mit Karte pruefen

Browser auf `https://localhost:8443` oeffnen (Zertifikatswarnung akzeptieren).

Erwartung: Die Leaflet-Karte wird angezeigt. Ein Klick auf die Karte uebernimmt
Latitude/Longitude ins Formular. Nach dem Senden erscheint die Meldung als Marker
auf der Karte und im Feed. Ein Klick auf einen Feed-Eintrag fokussiert den Marker
und laedt den Eintrag zum Aendern ins Formular.

## Agentic-TDD-Hinweis

Fuer neue Features sollte zuerst ein Test fuer den gewuenschten Zustand formuliert werden, der anfangs rot sein darf. Danach wird genau so viel Code geschrieben, bis der Test gruen wird. Besonders wertvoll sind Tests fuer Replikation, Konfliktaufloesung und Fehlertoleranz, weil dort die Hauptbewertungspunkte liegen.
