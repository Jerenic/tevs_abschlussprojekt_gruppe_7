# Dokumentation – Proof of Concept: Verteilter Status-Server

## Ziel des PoC

Der Proof of Concept zeigt in vereinfachter Form, wie die Kernanforderung des Abschlussprojekts umsetzbar ist: ein Client sendet eine Statusmeldung an einen Server-Node, der diese lokal speichert und anschließend an einen zweiten Node repliziert. Damit ist der grundlegende Kommunikationsweg – Client zu Node, Node zu Node – demonstriert, ohne bereits alle komplexen Anforderungen (Fehlertoleranz, Persistenz, TLS, Konfliktauflösung) zu implementieren.

---

## Architektur

```
┌─────────────┐        POST /status        ┌──────────────────────────┐
│             │ ─────────────────────────► │  Node A  (Port 5001)     │
│   Frontend  │                            │  - speichert lokal        │
│  (Browser)  │        GET /status         │  - leitet weiter ──────► │ POST /replicate
│             │ ◄───────────────────────── │                          │ ──────────────►
└─────────────┘                            └──────────────────────────┘                │
       │                                                                                ▼
       │               GET /status         ┌──────────────────────────┐
       └─────────────────────────────────► │  Node B  (Port 5002)     │
                                           │  - speichert replizierte │
                                           │    Daten lokal           │
                                           └──────────────────────────┘
```

Das System besteht aus drei Komponenten:

| Komponente | Technologie | Aufgabe |
|------------|-------------|---------|
| Frontend   | HTML + JavaScript (fetch API) | Benutzeroberfläche zum Senden und Anzeigen von Statusmeldungen |
| Node A     | Python + Flask | Empfängt Status vom Client, speichert ihn, repliziert an Node B |
| Node B     | Python + Flask | Empfängt replizierte Daten von Node A, speichert sie lokal |

---

## Das Status-Objekt

Jede Statusmeldung besteht aus folgenden Feldern:

```json
{
  "username":   "RECON-01",
  "statustext": "Am Weg zum Einsatz",
  "uhrzeit":    "2026-04-27T10:00:00",
  "latitude":   48.2150,
  "longitude":  16.3850
}
```

Der `username` dient gleichzeitig als eindeutiger Schlüssel – jeder User hat genau einen aktiven Status. Wird ein Status mit einem bereits vorhandenen Username gesendet, wird der alte überschrieben. Die `uhrzeit` wird serverseitig gesetzt, falls der Client keine mitschickt.

---

## Kommunikationsfluss im Detail

### 1. Client sendet einen Status

```
POST http://localhost:5001/status
Content-Type: application/json

{
  "username": "RECON-01",
  "statustext": "Am Weg zum Einsatz",
  "latitude": 48.2150,
  "longitude": 16.3850
}
```

Das Frontend schickt diesen Request direkt an Node A.

### 2. Node A verarbeitet den Request

- Der eingehende Status wird in einem Python-Dictionary (`statuses`) gespeichert. Der `username` ist der Schlüssel, das gesamte Objekt der Wert.
- Anschließend schickt Node A den gleichen Datensatz per `POST /replicate` an Node B weiter. Ist Node B nicht erreichbar, wird eine Warnung in der Konsole ausgegeben – der Client bekommt trotzdem eine Erfolgsantwort, da der eigene Speichervorgang erfolgreich war.

### 3. Node B repliziert den Status

- Node B empfängt den Request auf `/replicate` und speichert den Datensatz ebenfalls in seinem lokalen Dictionary.
- Damit halten beide Nodes denselben Stand.

### 4. Client liest die Daten aus

- Das Frontend kann `GET /status` sowohl auf Node A (Port 5001) als auch auf Node B (Port 5002) aufrufen.
- Beide liefern dieselbe Antwort – die Replikation ist sichtbar.

---

## Endpunkte

Jeder Node stellt folgende HTTP-Endpunkte bereit:

| Methode | Pfad             | Beschreibung                                      |
|---------|------------------|---------------------------------------------------|
| POST    | `/status`        | Neuen Status empfangen, speichern, weiterleiten   |
| POST    | `/replicate`     | Replizierten Status von einem anderen Node empfangen |
| GET     | `/status`        | Liste aller gespeicherten Statuses zurückgeben    |
| GET     | `/status/<user>` | Status eines bestimmten Users zurückgeben         |
| GET     | `/health`        | Gibt an, ob der Node läuft und wie viele Einträge er hat |

---

## Warum REST?

REST (HTTP) wurde für den PoC aus folgenden Gründen gewählt:

- **Einfachheit:** Kein zusätzliches Protokoll-Overhead, direkte Request-Response-Kommunikation.
- **Testbarkeit:** Endpunkte lassen sich mit einem Browser, curl oder Postman sofort prüfen.
- **Transparenz:** Der Kommunikationsweg ist klar nachvollziehbar – ideal für eine Demonstration.
- **Bekannt:** HTTP ist in jedem Team vertraut und braucht keine Einarbeitung.

Im Abschlussprojekt kann dasselbe Prinzip beibehalten oder durch effizientere Protokolle (z.B. WebSocket für Push-Benachrichtigungen) ergänzt werden.

---

## Was der PoC bewusst weglässt

Der PoC ist keine vollständige Implementierung. Folgende Punkte sind im Abschlussprojekt zu ergänzen:

| Thema | Status im PoC | Plan für Abschlussprojekt |
|-------|--------------|--------------------------|
| Persistenz | In-Memory (geht bei Neustart verloren) | SQLite pro Node |
| Konfliktauflösung | Letzter Request gewinnt (kein Zeitvergleich) | Last-Writer-Wins via `uhrzeit` |
| Fehlertoleranz | Node B-Ausfall wird geloggt, kein Retry | Retry-Mechanismus, Grace Period |
| Mehr als 2 Nodes | Fest verdrahtet (A → B) | Dynamisch konfigurierbare Node-Liste |
| TLS / HTTPS | Kein TLS | Selbstsignierte Zertifikate |
| Bootstrapping | Kein initialer Sync | Neue Node lädt Daten von aktiven Nodes nach |
| Validierung | Keine Zeitprüfung bei Replikation | Nur neuere Updates werden übernommen |

---

## Zusammenfassung

Der PoC zeigt den grundlegenden Mechanismus eines verteilten Status-Servers: Ein Client schickt Daten an einen Node, der sie lokal hält und sie gleichzeitig an einen zweiten Node weitergibt. Beide Nodes halten damit denselben Zustand – das Grundprinzip der Replikation ist demonstriert. Die Kommunikation erfolgt ausschließlich über HTTP/REST, was den Ablauf leicht nachvollziehbar und testbar macht.
