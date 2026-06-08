# Frontend-Konzept - Verteiltes Commandcenter

Das Frontend liegt bewusst als statische HTML-Datei vor (`frontend/index.html`).
Es braucht keinen Build-Step und ist damit für die Demo leicht zu starten. Die
Karte kommt über Leaflet; eigene Kartenlogik bauen wir nicht nach.

## Ziel

Das Frontend ist das Bedienfenster für den Statusserver: Formular, Status-Feed
und Karte auf einer Seite. Es spricht nur den Loadbalancer über `/api/...` an
und kennt keine einzelnen Backend-Nodes.

## Visuelle Richtung

Die Oberfläche orientiert sich grob an einem Commandcenter:

- große Kartenansicht als zentrale Arbeitsfläche
- rechte Sidebar für Eingaben, Node-Status und Feed
- Statusmeldungen als Marker auf der Karte
- dunkles, ruhiges Bedienpanel
- helle, reduzierte Karte im Hintergrund
- klare technische Optik, aber nicht überladen

Das Beispielbild war nur die Richtung: Karte im Mittelpunkt, daneben ein
kompaktes Bedienpanel mit den aktuellen Meldungen.

## Tech-Stack (umgesetzt)

| Bereich | Technologie | Grund |
|---|---|---|
| Frontend-App | Statisches HTML + Vanilla JavaScript | Startet direkt über NGINX, kein Build nötig |
| Karte | Leaflet (per CDN) | Kleine, etablierte Kartenbibliothek |
| API | `fetch` gegen `/api/...` | Das Frontend bleibt unabhängig von einzelnen Nodes |
| Styling | Inline-CSS im `<style>`-Block | Für diesen Umfang ausreichend |

## Architektur

```text
Browser / HTML + Leaflet Frontend
  |
  | /api/status
  v
NGINX Loadbalancer
  |
  v
StatusNode A / StatusNode B / StatusNode C
```

Alle Requests gehen relativ an `/api/...`. Dadurch funktioniert dieselbe Seite
lokal und im Container. Über den Header `X-Status-Node` zeigen wir an, welche
Node zuletzt geantwortet hat.

## Layout-Skizze

```text
+---------------------------------------------------------------+
| Map / Einsatzgebiet                                           |
|                                                               |
|   o RECON-01        o COMMAND-HQ         o DRONE-X2            |
|                                                               |
|                                             +----------------+ |
|                                             | Command Center | |
|                                             | Node Status    | |
|                                             |                | |
|                                             | Transmission   | |
|                                             | Username       | |
|                                             | Statustext     | |
|                                             | Koordinaten    | |
|                                             | [Senden]       | |
|                                             |                | |
|                                             | Global Feed    | |
|                                             | Statuskarten   | |
|                                             +----------------+ |
+---------------------------------------------------------------+
```

## Aufbau (umgesetzt)

```text
frontend/
  index.html   HTML-Struktur, CSS und JavaScript in einer Datei
               - Formular (Username, Statustext, Lat/Lon)
               - Leaflet-Karte mit Markern (Funktionen renderMarkers/setCoords)
               - globaler Feed (renderStatuses)
               - API-Aufrufe per fetch gegen /api/...
```

Die Karte besteht aus `L.map`, einem OpenStreetMap-Tile-Layer und einer
`L.layerGroup` für die Status-Marker. Klickt man auf die Karte, werden die
Koordinaten direkt ins Formular übernommen.

## Funktionsumfang

| Feature | Beschreibung |
|---|---|
| Status setzen | Username, Statustext, Latitude, Longitude erfassen |
| Status ändern | Bestehenden Status im Feed auswählen und Formular befüllen |
| Status löschen | Delete-Button im Feed, API `DELETE /status/<username>` |
| Alle Status anzeigen | Feed und Karte zeigen alle aktiven Statusmeldungen |
| Karte | Marker für alle Statusmeldungen |
| Koordinaten setzen | Klick auf Karte setzt Latitude und Longitude im Formular |
| Node-Anzeige | Letzte antwortende Backend-Node anzeigen |
| Refresh | Feed/Karte regelmäßig oder per Button aktualisieren |

## Datenmodell im Frontend

```ts
type Status = {
  username: string;
  statustext: string;
  uhrzeit: string;
  latitude: number;
  longitude: number;
  deleted?: boolean;
  originNode?: string;
};
```

## API-Vertrag

Das Frontend nutzt nur diese Endpunkte:

| Methode | Pfad | Zweck |
|---|---|---|
| `GET` | `/api/status` | Alle aktiven Statusmeldungen laden |
| `POST` | `/api/status` | Status erstellen oder aktualisieren |
| `GET` | `/api/status/<username>` | Einzelnen Status laden |
| `DELETE` | `/api/status/<username>` | Status löschen |
| `GET` | `/api/health` | Optional: Backend-Health über Loadbalancer |

## UX-Details

- Die Karte bleibt immer sichtbar und ist die Hauptarbeitsfläche.
- Das Panel rechts bleibt kompakt und dient als Kontrollzentrum.
- Feed-Einträge enthalten Username, Statustext, Uhrzeit und Koordinaten.
- Klick auf einen Feed-Eintrag fokussiert den Marker auf der Karte.
- Klick auf einen Marker zeigt Details und kann den Feed-Eintrag markieren.
- Nach dem Senden wird der Feed neu geladen und der Marker aktualisiert.
- Bei Backend-Fehlern bleibt das Frontend bedienbar und zeigt eine kurze Fehlermeldung.

## Umsetzungsschritte (erledigt)

1. Leaflet per CDN eingebunden, Karte mit Wien als Startposition.
2. API-Aufrufe per `fetch` gegen `/api/status`.
3. Statusformular und Feed gebaut.
4. Marker für alle Statusmeldungen auf der Karte.
5. Klick auf Karte setzt Koordinaten; "Mein Standort" nutzt die Geolocation.
6. Klick auf Feed-Eintrag fokussiert Marker und lädt den Eintrag zum Ändern.
7. Delete-Button je Feed-Eintrag.
8. NGINX liefert `frontend/index.html` direkt aus (kein Build-Step nötig).

## Wichtig für die Architektur

Das Frontend spricht nie direkt einzelne Nodes wie `node-a` oder
`localhost:5001` an. Der Loadbalancer bleibt der einzige Einstiegspunkt. Genau
dadurch passt die Oberfläche zur Loadbalancer-Aufgabe und zur finalen
Architektur mit replizierenden Statusnodes.
