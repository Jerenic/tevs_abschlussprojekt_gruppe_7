# TLS-Zertifikate (Loadbalancer)

Hier liegt das **selbstsignierte** Zertifikat, mit dem der NGINX-Loadbalancer
HTTPS bereitstellt (`server.crt` / `server.key`). Es ist ein reines
Dev-/Demo-Zertifikat fuer dieses Schulprojekt und bewusst mit eingecheckt,
damit `docker compose up --build` ohne weitere Schritte funktioniert.

Weil das Zertifikat selbstsigniert ist, zeigt der Browser eine
Sicherheitswarnung an. Diese ist erwartbar und kann fuer die Demo akzeptiert
werden (bei `curl` das Flag `-k` verwenden).

## Neu erzeugen

```bash
openssl req -x509 -nodes -newkey rsa:2048 \
  -keyout server.key \
  -out server.crt \
  -days 3650 \
  -subj "/C=AT/ST=Wien/L=Wien/O=TEVS-Gruppe7/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
```
