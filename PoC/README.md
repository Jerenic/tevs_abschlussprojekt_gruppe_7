# Status Server – Proof of Concept

Demonstriert die Grundidee: Client sendet einen Status an **Node A**, Node A speichert ihn lokal und leitet ihn per REST an **Node B** weiter.

```
Client → POST /status → Node A (5001)
                              └─ POST /replicate → Node B (5002)
```

## Starten

### 1. Abhängigkeiten installieren

```bash
cd PoC/backend
pip install -r requirements.txt
```

### 2. Node B starten (kein Peer, empfängt nur Replikationen)

```bash
python node.py 5002 "" "Node-B"
```

### 3. Node A starten (leitet an Node B weiter)

```bash
python node.py 5001 http://localhost:5002 "Node-A"
```

### 4. Frontend öffnen

`PoC/frontend/index.html` direkt im Browser öffnen (Doppelklick genügt).

## Demonstration

1. Im Frontend einen Status eingeben und auf **Senden** klicken.
2. Der Status erscheint sofort bei **Node A**.
3. Durch Klick auf **Aktualisieren** bei Node B sieht man, dass der gleiche Eintrag repliziert wurde.

## Endpunkte (pro Node)

| Methode | Pfad               | Beschreibung                        |
|---------|--------------------|-------------------------------------|
| POST    | `/status`          | Neuen Status speichern (+ Replik.)  |
| POST    | `/replicate`       | Replikations-Endpunkt (Node → Node) |
| GET     | `/status`          | Alle Statuses abrufen               |
| GET     | `/status/<user>`   | Status eines Users abrufen          |
| GET     | `/health`          | Node-Status prüfen                  |

## Status-Objekt

```json
{
  "username":   "RECON-01",
  "statustext": "Am Weg zum Einsatz",
  "uhrzeit":    "2026-04-27T10:00:00",
  "latitude":   48.2150,
  "longitude":  16.3850
}
```
