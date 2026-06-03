# Frontend-Konzept - Verteiltes Commandcenter

## Ziel

Das aktuelle HTML-Frontend reicht fuer Aufgabe 3, weil dort der Loadbalancer im Vordergrund steht. Fuer das finale Projekt soll daraus aber ein richtiges Web-Frontend werden. Das Ziel ist ein Commandcenter-Interface mit Karte als Hauptansicht, einem rechten Bedienpanel und einem globalen Status-Feed. Das Frontend spricht weiterhin nur den Loadbalancer an und kennt keine einzelnen Backend-Nodes direkt.

## Visuelle Richtung

Das Frontend soll sich konzeptionell an einem Commandcenter orientieren:

- grosse Kartenansicht als zentrale Arbeitsflaeche
- rechte Sidebar fuer Eingaben, Node-Status und Feed
- Statusmeldungen als Marker auf der Karte
- dunkles, ruhiges Bedienpanel
- helle, reduzierte Karte im Hintergrund
- klare technische Optik, aber nicht ueberladen

Das Beispielbild ist keine 1:1 Vorlage, sondern zeigt die Richtung: Map-first Layout, rechts ein kompaktes Control Panel und darunter ein Feed mit aktuellen Meldungen.

## Vorgeschlagener Tech-Stack

| Bereich | Technologie | Grund |
|---|---|---|
| Frontend-App | React + Vite | Schnell, uebersichtlich, gut wartbar |
| Karte | Leaflet | Erfuellt Kartenanforderung ohne grossen Overhead |
| API | Fetch oder kleines API-Modul | Frontend bleibt einfach |
| Styling | CSS Modules oder normale CSS-Datei | Kein schweres UI-Framework noetig |

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

## Geplante Komponenten

```text
frontend/
  src/
    api/
      statusApi.ts
    components/
      CommandPanel.tsx
      NodeStatus.tsx
      StatusForm.tsx
      StatusFeed.tsx
      StatusMap.tsx
      UnitTypePicker.tsx
    App.tsx
    main.tsx
    styles.css
```

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

## Umsetzungsschritte

1. `frontend/` als Vite React App anlegen.
2. Leaflet installieren und Karte mit Wien als Startposition anzeigen.
3. API-Modul fuer `/api/status` schreiben.
4. Statusformular und Feed bauen.
5. Marker fuer Statusmeldungen anzeigen.
6. Klick auf Karte setzt Koordinaten.
7. Edit/Delete im Feed umsetzen.
8. Docker/NGINX so anpassen, dass das gebaute Frontend ausgeliefert wird.
9. Akzeptanztests fuer API-Flows und grundlegendes Rendering ergaenzen.

## Wichtig fuer die Architektur

Das Frontend darf nicht direkt einzelne Nodes wie `node-a`, `localhost:5001` oder `localhost:5002` ansprechen. Der Loadbalancer bleibt der einzige Einstiegspunkt. Dadurch passt das Frontend zur Aufgabe 3 und spaeter auch zur finalen Architektur mit mehreren replizierenden Statusnodes.
