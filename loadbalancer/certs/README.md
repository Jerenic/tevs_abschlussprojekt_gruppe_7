# TLS-Zertifikate (Loadbalancer und Statusnodes)

Hier liegt das **selbstsignierte** Zertifikat, mit dem der NGINX-Loadbalancer
und die internen Statusnode-APIs HTTPS bereitstellen (`server.crt` /
`server.key`). Es ist ein reines Dev-/Demo-Zertifikat für dieses Schulprojekt
und bewusst mit eingecheckt, damit `docker compose up --build` ohne weitere
Schritte funktioniert.

Weil das Zertifikat selbstsigniert ist, zeigt der Browser eine
Sicherheitswarnung an. Diese ist erwartbar und kann für die Demo akzeptiert
werden (bei `curl` das Flag `-k` verwenden). Für die internen
Self-Signed-Verbindungen ist die Zertifikatsprüfung in Docker Compose
deaktiviert (`PEER_TLS_VERIFY=false`, `proxy_ssl_verify off`); die Verbindung
ist trotzdem TLS-verschlüsselt.

## Neu erzeugen

```bash
openssl req -x509 -nodes -newkey rsa:2048 \
  -keyout server.key \
  -out server.crt \
  -days 3650 \
  -subj "/C=AT/ST=Wien/L=Wien/O=TEVS-Gruppe7/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,DNS:node-a,DNS:node-b,DNS:node-c,IP:127.0.0.1"
```
