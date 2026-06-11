# TLS-Zertifikat (Loadbalancer)

Hier liegt das **selbstsignierte** Zertifikat für den NGINX-Loadbalancer
(`server.crt` / `server.key`). Der Browser spricht nur den Loadbalancer über
HTTPS an; TLS wird dort terminiert. Die internen Verbindungen (Loadbalancer →
Node, Node → Node) laufen im isolierten Docker-Netz per HTTP.

Das Zertifikat ist ein Dev-/Demo-Zertifikat und bewusst eingecheckt, damit
`docker compose up --build` ohne weitere Schritte funktioniert.

Weil das Zertifikat selbstsigniert ist, zeigt der Browser eine
Sicherheitswarnung an. Diese ist erwartbar und kann für die Demo akzeptiert
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
