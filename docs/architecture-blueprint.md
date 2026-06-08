# Architektur-Blueprint - Verteiltes Commandcenter

## Zielbild

Das Projekt entwickelt sich vom einfachen Zwei-Node-PoC zu einem verteilten Commandcenter mit mehreren gleichwertigen Statusnodes. Ein Client arbeitet ueber eine zentrale URL und muss keine Node manuell auswaehlen. Der Loadbalancer verteilt API-Requests auf die aktiven Statusnodes. Jede Statusnode speichert Statusmeldungen lokal und persistent und repliziert Schreiboperationen an ihre konfigurierten Peers.

## Aktueller Arbeitsstand

```mermaid
flowchart LR
    U[Browser / User] -->|HTTPS / TLS| LB[NGINX Loadbalancer<br/>localhost:8443]
    LB -->|Frontend HTML + Leaflet| FE[index.html]
    LB -->|/api/... HTTPS| A[StatusNode A<br/>Flask :5000<br/>SQLite]
    LB -->|/api/... HTTPS| B[StatusNode B<br/>Flask :5000<br/>SQLite]
    LB -->|/api/... HTTPS| C[StatusNode C<br/>Flask :5000<br/>SQLite]
    A <-->|HTTPS /replicate| B
    A <-->|HTTPS /replicate| C
    B <-->|HTTPS /replicate| C
```

Der Browser ruft nur den Loadbalancer auf, und zwar ausschliesslich ueber HTTPS (TLS-Terminierung am Loadbalancer). Das Frontend wird direkt vom Loadbalancer ausgeliefert und spricht ausschliesslich relative `/api/...`-Pfade an. NGINX verteilt die API-Requests per Round-Robin ueber HTTPS auf `node-a`, `node-b` und `node-c`. Die Statusnodes sind nicht am Host exposed, sondern nur im internen Docker-Netzwerk erreichbar.

## Komponenten

| Komponente | Technologie | Aufgabe |
|---|---|---|
| Loadbalancer | NGINX | Zentrale HTTPS-URL, TLS-Terminierung, Frontend-Auslieferung, Proxy und Failover auf Backend-Nodes |
| StatusNode A/B/C | Python + Flask (`backend/status_node/`) | CRUD-API, SQLite-Persistenz, Peer-Replikation, Bootstrap, Retry |
| Persistenz | SQLite (pro Node) | Lokaler, dauerhafter Speicher je Node, kein Shared-DB |
| Frontend | HTML + JavaScript + Leaflet (`frontend/index.html`) | Status erfassen/aendern/loeschen, Feed anzeigen, Kartenansicht mit Markern |
| Docker Compose | Docker | Gemeinsames Netzwerk, Healthchecks, Volumes, Service-Start |

### Backend-Module (`backend/status_node/`)

Die StatusNode ist in fachliche Module aufgeteilt, damit Replikation, Persistenz und Bootstrapping getrennt erklaerbar und testbar sind:

| Modul | Verantwortung |
|---|---|
| `app.py` | Flask-App, Routes, Start-Einstiegspunkt (`python -m status_node.app`) |
| `config.py` | Laufzeitkonfiguration aus Env/CLI (Port, Peers, DB-Pfad, Intervalle) |
| `models.py` | Validierung, Zeitstempel-Parsing, Last-Writer-Wins-Vergleich |
| `storage.py` | SQLite-Verbindung, Persistenz und In-Memory-Lesecache |
| `replication.py` | Peer-Replikation, Pending-Queue, Retry-Worker |
| `bootstrap.py` | Snapshot-Abruf, Initial-Sync, Grace-Period-Status |

## Kommunikationswege

| Weg | Protokoll | Zweck |
|---|---|---|
| Browser -> Loadbalancer | HTTPS/TLS | Single Point of Access, verschluesselt |
| Loadbalancer -> StatusNode | HTTPS/REST (internes Docker-Netz) | Verteilung von API-Requests, Failover |
| StatusNode -> StatusNode | HTTPS/REST (internes Docker-Netz) | Push-Replikation nach Schreiboperationen |
| StatusNode -> StatusNode | HTTPS/REST (internes Docker-Netz) | Snapshot-Abruf beim Initial-Sync (`/internal/snapshot`) |

## Statusmodell

```json
{
  "username": "RECON-01",
  "statustext": "Am Weg zum Einsatz",
  "uhrzeit": "2026-06-02T12:00:00+00:00",
  "latitude": 48.215,
  "longitude": 16.385,
  "deleted": false,
  "originNode": "Node-A"
}
```

`username` ist der fachliche Key. Pro Username gibt es genau einen aktiven Status. Delete wird als Tombstone (`deleted: true`) gespeichert und repliziert, damit geloeschte Eintraege nicht durch alte Replikate wieder auftauchen.

## Konsistenz und Konfliktaufloesung

Das System strebt Eventual Consistency an. Die Konfliktregel ist Last-Writer-Wins anhand von `uhrzeit`:

- Ist ein eingehendes Update juenger, wird es uebernommen.
- Ist es aelter, wird es ignoriert (auch bei Replikation und Bootstrap).
- Bei exakt gleichem `uhrzeit` entscheidet deterministisch der `originNode` (lexikografisch), damit alle Nodes unabhaengig von der Reihenfolge konvergieren.

Diese Regel gilt einheitlich fuer Client-Schreibzugriffe, fuer empfangene Replikate und fuer den Initial-Sync.

## Persistenz

Jede Node haelt einen In-Memory-Cache fuer schnelle Lesezugriffe und spiegelt jeden Schreibvorgang in eine eigene SQLite-Datei. Beim Start laedt die Node den Cache aus SQLite. Im Container liegt die Datei unter `/data/status.db` auf einem Docker-Volume pro Node. Dadurch ueberlebt der Datenstand einen Container-Neustart, und es gibt keine gemeinsame oder verteilte Datenbank (Vorgabe der Angabe).

## Initial-Sync / Bootstrapping

Beim Start befindet sich eine Node in einer Grace Period:

1. `state=bootstrapping`, Client-Endpunkte antworten mit HTTP 503.
2. Die Node fragt nacheinander die Peer-Snapshots (`GET /internal/snapshot`) ab.
3. Jeder erhaltene Status wird per Last-Writer-Wins gemerged (inklusive Tombstones).
4. Nach erfolgreichem Sync oder Timeout wechselt die Node auf `state=ready`.

`/replicate`, `/internal/snapshot` und `/health` bleiben waehrend der Grace Period erreichbar, damit Peers weiterarbeiten koennen.

## Sicherheit / Transportverschluesselung

Der Loadbalancer und die Statusnodes nutzen HTTPS/TLS mit selbstsigniertem
Zertifikat (`loadbalancer/certs/`, laut Angabe erlaubt). Damit laufen Frontend
<-> Loadbalancer, Loadbalancer <-> StatusNode und StatusNode <-> StatusNode
verschluesselt. Die Statusnodes sind am Host nicht exposed; ihre Replikation
laeuft im internen, isolierten Docker-Netzwerk und ist von aussen nicht
erreichbar. Fuer die internen Self-Signed-Verbindungen ist die
Zertifikatspruefung in Docker Compose deaktiviert (`PEER_TLS_VERIFY=false`,
`proxy_ssl_verify off`), nicht aber die Transportverschluesselung.

## Fehlertoleranz

- Faellt eine Node aus, leitet NGINX den Traffic auf die verbleibenden Nodes (Failover ohne URL-Wechsel).
- Schlaegt die Peer-Replikation fehl, bleibt der Client-Request erfolgreich; das Update wandert in eine Retry-Queue und wird durch einen Hintergrund-Worker nachgeliefert.
- Eine neu gestartete oder zuvor ausgefallene Node holt sich den aktuellen Stand ueber den Initial-Sync.

## Optionale Erweiterungen (kein Pflichtteil)

- Hochverfuegbarer Loadbalancer (Aktiv/Passiv), um den letzten SPoF zu eliminieren.
- Strengere interne Zertifikatspruefung mit eigener CA und SAN-Zertifikaten fuer `node-a`, `node-b`, `node-c`.
