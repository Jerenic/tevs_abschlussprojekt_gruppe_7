# Frontend-Konzept - Verteiltes Commandcenter

> Umsetzungsstand: Das Frontend ist umgesetzt als **eine statische HTML-Datei
> (`frontend/index.html`) mit Leaflet-Karte**. Bewusst kein React/Build-Step, um
> die Loesung einfach und gut erklaerbar zu halten (die Karte wird ausschliesslich
> ueber Leaflet-Library-Aufrufe gebaut). Dieser Abschnitt beschreibt Ziel,
> Layout und Funktionsumfang dieser Umsetzung.

## Ziel

Das Frontend ist ein Commandcenter-Interface mit Karte als Hauptansicht, einem Bedienpanel (Formular) und einem globalen Status-Feed. Es spricht ausschliesslich den Loadbalancer ueber HTTPS an (`/api/...`) und kennt keine einzelnen Backend-Nodes direkt.

## Visuelle Richtung

Das Frontend soll sich konzeptionell an einem Commandcenter orientieren:

- grosse Kartenansicht als zentrale Arbeitsflaeche
- rechte Sidebar fuer Eingaben, Node-Status und Feed
- Statusmeldungen als Marker auf der Karte
- dunkles, ruhiges Bedienpanel
- helle, reduzierte Karte im Hintergrund
- klare technische Optik, aber nicht ueberladen

Das Beispielbild ist keine 1:1 Vorlage, sondern zeigt die Richtung: Map-first Layout, rechts ein kompaktes Control Panel und darunter ein Feed mit aktuellen Meldungen.

## Tech-Stack (umgesetzt)

| Bereich | Technologie | Grund |
|---|---|---|
| Frontend-App | Statisches HTML + Vanilla JavaScript | Kein Build-Step, einfach auszuliefern und zu erklaeren |
| Karte | Leaflet (per CDN) | Erfuellt Kartenanforderung ohne grossen Overhead, reine Library-Aufrufe |
| API | `fetch` gegen `/api/...` | Frontend bleibt einfach |
| Styling | Inline-CSS im `<style>`-Block | Kein schweres UI-Framework noetig |

## Architektur

```text
Browser / React Frontend
  |
  | /api/status
  v
NGINX Loadbalancer
  |
  v
StatusNode A / StatusNode B / StatusNode C
```

Das Frontend sendet alle Requests relativ an `/api/...`. Dadurch funktioniert es lokal und im Container ueber dieselbe zentrale URL. Welche Node eine Anfrage beantwortet, kann optional ueber den Header `X-Status-Node` angezeigt werden.

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

Die Karte wird ueber Leaflet aufgebaut: ein `L.map`, ein OpenStreetMap-Tile-Layer
und eine `L.layerGroup` fuer die Status-Marker. Ein Klick auf die Karte
uebernimmt die Koordinaten ins Formular (`map.on("click", ...)`).

## Funktionsumfang

| Feature | Beschreibung |
|---|---|
| Status setzen | Username, Statustext, Latitude, Longitude erfassen |
| Status aendern | Bestehenden Status im Feed auswaehlen und Formular befuellen |
| Status loeschen | Delete-Button im Feed, API `DELETE /status/<username>` |
| Alle Status anzeigen | Feed und Karte zeigen alle aktiven Statusmeldungen |
| Karte | Marker fuer alle Statusmeldungen |
| Koordinaten setzen | Klick auf Karte setzt Latitude und Longitude im Formular |
| Node-Anzeige | Letzte antwortende Backend-Node anzeigen |
| Refresh | Feed/Karte regelmaessig oder per Button aktualisieren |

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
| `DELETE` | `/api/status/<username>` | Status loeschen |
| `GET` | `/api/health` | Optional: Backend-Health ueber Loadbalancer |

## UX-Details

- Die Karte bleibt immer sichtbar und ist die Hauptarbeitsflaeche.
- Das Panel rechts bleibt kompakt und dient als Kontrollzentrum.
- Feed-Eintraege enthalten Username, Statustext, Uhrzeit und Koordinaten.
- Klick auf einen Feed-Eintrag fokussiert den Marker auf der Karte.
- Klick auf einen Marker zeigt Details und kann den Feed-Eintrag markieren.
- Nach dem Senden wird der Feed neu geladen und der Marker aktualisiert.
- Bei Backend-Fehlern bleibt das Frontend bedienbar und zeigt eine kurze Fehlermeldung.

## Umsetzungsschritte (erledigt)

1. Leaflet per CDN eingebunden, Karte mit Wien als Startposition.
2. API-Aufrufe per `fetch` gegen `/api/status`.
3. Statusformular und Feed gebaut.
4. Marker fuer alle Statusmeldungen auf der Karte.
5. Klick auf Karte setzt Koordinaten; "Mein Standort" nutzt die Geolocation.
6. Klick auf Feed-Eintrag fokussiert Marker und laedt den Eintrag zum Aendern.
7. Delete-Button je Feed-Eintrag.
8. NGINX liefert `frontend/index.html` direkt aus (kein Build-Step noetig).

## Wichtig fuer die Architektur

Das Frontend darf nicht direkt einzelne Nodes wie `node-a`, `localhost:5001` oder `localhost:5002` ansprechen. Der Loadbalancer bleibt der einzige Einstiegspunkt. Dadurch passt das Frontend zur Aufgabe 3 und spaeter auch zur finalen Architektur mit mehreren replizierenden Statusnodes.
