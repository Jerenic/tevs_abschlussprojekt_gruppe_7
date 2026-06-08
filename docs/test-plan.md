# Testplan - Loadbalanced Statusserver

## Ziel

Die Tests zeigen, dass der Loadbalancer sinnvoll vor den Statusnodes arbeitet und dass die Nodes Replikation, Persistenz, TLS-Transportverschlüsselung, Konfliktauflösung und Fehlertoleranz korrekt umsetzen. Der wichtigste Punkt für Aufgabe 3 ist, dass der User nur eine URL braucht und Node-Ausfälle nicht manuell behandeln muss.

## Automatisierte Tests

Ausführen:

```bash
python -m unittest discover -s tests
```

Abgedeckte Bereiche in `tests/test_status_node.py`:

| Bereich | Was geprüft wird |
|---|---|
| CRUD | `POST`/`GET`/`GET <user>`/`DELETE` funktionieren wie erwartet |
| Validierung | fehlender `username`/`statustext`, ungültige Koordinaten, ungültige `uhrzeit`, `deleted` auf `/status`, Nicht-Objekt-Payload -> HTTP 400 |
| Replikation | Schreibzugriff repliziert an konfigurierte Peers (`/replicate`) |
| Last-Writer-Wins | jüngeres Update gewinnt, älteres wird ignoriert, deterministischer Tiebreak bei gleichem `uhrzeit` |
| Tombstones | Delete erzeugt Tombstone und blendet Status aus, repliziert das Tombstone, verhindert Wiederauferstehung durch alte Updates |
| Persistenz | Status und Tombstone überleben das erneute Öffnen der SQLite-Datei (Neustart-Simulation) |
| Bootstrapping | Peer-Snapshot wird per LWW gemerged, jüngerer lokaler Stand wird nicht überschrieben |
| Grace Period | Client-Endpunkte liefern während des Bootstraps HTTP 503, `/health` und `/replicate` bleiben erreichbar |
| Retry-Queue | fehlgeschlagene Replikation wird eingereiht, bei Erreichbarkeit nachgeliefert, Dedup behält das neueste Update |

Transportverschlüsselung wird zusätzlich über die Docker-Konfiguration
geprüft: Frontend -> Loadbalancer, Loadbalancer -> StatusNode und StatusNode
-> StatusNode nutzen HTTPS. Wegen selbstsignierter Dev-Zertifikate wird bei
internen Verbindungen die Zertifikatsprüfung deaktiviert, nicht die
Verschlüsselung.

## Manuelle Akzeptanztests (mit Docker)

### 1. Compose startet erfolgreich

```bash
docker compose up --build
```

Erwartung: `node-a`, `node-b`, `node-c` und `loadbalancer` starten ohne Fehler. Die Anwendung ist unter `https://localhost:8443` erreichbar (selbstsigniertes Zertifikat, daher bei `curl` das Flag `-k`).

### 2. Loadbalancer-Health prüfen

```bash
curl -k https://localhost:8443/lb-health
```

Erwartung: Antwort ist `ok`.

### 3. Status über zentrale API anlegen

```bash
curl -k -X POST https://localhost:8443/api/status ^
  -H "Content-Type: application/json" ^
  -d "{\"username\":\"RECON-01\",\"statustext\":\"Am Weg zum Einsatz\",\"latitude\":48.215,\"longitude\":16.385}"
```

Erwartung: HTTP 201 und JSON-Antwort mit `node`, `status` und `replication`.

### 4. Status über zentrale API abrufen

```bash
curl -k https://localhost:8443/api/status
```

Erwartung: Der vorher angelegte Status ist im Feed enthalten. Bei mehrfacher Ausführung kann die Antwort von unterschiedlichen Nodes kommen (Header `X-Status-Node`).

### 5. Node-Ausfall simulieren

```bash
docker compose stop node-a
curl -k https://localhost:8443/api/status
```

Erwartung: Die URL bleibt gleich und der Request wird von einer verbleibenden Node beantwortet.

### 6. Initial-Sync nach Neustart prüfen

```bash
docker compose start node-a
curl -k https://localhost:8443/api/status
```

Erwartung: Node-A lädt während der Grace Period den aktuellen Stand von den Peers und liefert danach dieselben Daten.

### 7. Persistenz prüfen

```bash
docker compose restart node-b
```

Erwartung: Nach dem Neustart enthält Node-B weiterhin die zuvor gespeicherten Statusmeldungen (SQLite-Volume).

### 8. Delete wird repliziert

```bash
curl -k -X DELETE https://localhost:8443/api/status/RECON-01
curl -k https://localhost:8443/api/status
```

Erwartung: Der Status wird aus dem sichtbaren Feed entfernt und bleibt auch nach Replikation und Neustart entfernt.

### 9. Frontend mit Karte prüfen

Browser auf `https://localhost:8443` öffnen (Zertifikatswarnung akzeptieren).

Erwartung: Die Leaflet-Karte wird angezeigt. Ein Klick auf die Karte übernimmt
Latitude/Longitude ins Formular. Nach dem Senden erscheint die Meldung als Marker
auf der Karte und im Feed. Ein Klick auf einen Feed-Eintrag fokussiert den Marker
und lädt den Eintrag zum Ändern ins Formular.
