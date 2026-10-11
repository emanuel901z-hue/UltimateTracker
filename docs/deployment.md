# Deployment (WSL jetzt, Thin Client später)

Der Server-Stack läuft als Docker Compose auf Linux (x86_64). Aktuell: dedizierte
WSL-Distro auf dem Entwicklungsrechner. Ziel: Thin Client im Heimnetz.

## 1. Dedizierte WSL-Distro (bereits eingerichtet)

```powershell
# Auf D: installieren (C: ist fast voll), ohne Store-Interaktion
wsl --install Ubuntu-24.04 --name UltimateTracker --location D:\WSL\UltimateTracker --no-launch
```

Erstkonfiguration (als root, ohne interaktive Abfragen):

```bash
wsl -d UltimateTracker -u root -- bash -lc '
  useradd -m -s /bin/bash manu
  usermod -aG sudo manu
  echo "manu ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/90-manu
  chmod 440 /etc/sudoers.d/90-manu
  printf "[user]\ndefault=manu\n\n[boot]\nsystemd=true\n" > /etc/wsl.conf'
wsl --terminate UltimateTracker   # systemd + Default-User aktivieren
```

Docker (offizielles Repository, inkl. Compose-Plugin):

```bash
wsl -d UltimateTracker -- bash -lc '
  sudo apt-get update -qq
  sudo apt-get install -y -qq ca-certificates curl rsync
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker manu
  sudo systemctl enable --now docker'
```

## 2. Repo in die Distro spiegeln

Aus WSL heraus:

```bash
bash /mnt/d/Projekte/UltimateTracker/scripts/sync-to-wsl.sh
```

Das Skript rsynct nach `~/UltimateTracker` und überschreibt `server/.env` **nicht**.
Workflow: Dateien werden unter Windows bearbeitet, dann gespiegelt.

## 3. Server starten

```bash
cd ~/UltimateTracker/server
cp .env.example .env
openssl rand -hex 24   # zweimal ausführen -> DEVICE_TOKEN und PARENT_TOKEN eintragen
nano .env
docker compose up -d
docker compose ps
docker compose logs -f audio-bridge
```

Prüfen:

```bash
curl -s http://localhost:8085/healthz
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8082
```

Von Windows aus sind die Ports per WSL2-Forwarding erreichbar:
<http://localhost:8085> (Eltern-UI), <http://localhost:8082> (Traccar).

## 4. Erstkonfiguration Traccar

1. <http://localhost:8082> öffnen. **Traccar legt keinen Standard-Admin mehr an:**
   den ersten Benutzer registrieren – er wird automatisch Administrator.
   (Passwort sicher wählen; nicht `admin/admin` verwenden.)
2. Gerät anlegen (oder automatisch registrieren lassen, `database.registerUnknown=true`):
   Bezeichnung z. B. „Tracker“, Identifier = **IMEI des SIM7080G**.
3. Optional: Geofence (z. B. Spielplatz) in der UI anlegen und dem Gerät zuordnen;
   Ereignisse werden per `event.forward` zusätzlich an die Bridge geschickt
   (nachprüfbar in `/data/events.jsonl`).

Test-Upload einer Position (vom Host aus, solange der Tracker noch fehlt):

```bash
curl -s "http://localhost:5055/?id=TEST123&lat=48.1372&lon=11.5756&batt=87&timestamp=$(date +%s)"
```

## 5. Eltern-UI & API

- Eltern-UI: <http://localhost:8085> → Geräte-ID (IMEI) und Parent-Token eintragen,
  Nachricht aufnehmen und senden; Suchmodus-Schalter.
- Optional (Profil `findmy`): Google-Find-Hub-WebUI auf <http://localhost:4321>
  (Zugangsdaten `WEBUI_USER`/`WEBUI_PASSWORD` aus `server/.env`),
  Apple-Endpunkt `macless-haystack` auf Port 6176, Anisette auf 6969.
  Details: [`findmy.md`](findmy.md).
- Tracker-Endpunkte (mit `X-Auth-Token: <DEVICE_TOKEN>`):
  - `GET /api/v1/device/pending?device_id=<IMEI>`
  - `POST /api/v1/device/messages` (Multipart: `device_id`, `audio`)
  - `GET /api/v1/device/messages/{id}/audio`

## 6. TLS (Profil `tls`, vor dem Produktiveinsatz!)

```bash
cd ~/UltimateTracker/server
# Hostnamen in .env setzen (SITE_AUDIO/SITE_TRACCAR/SITE_FINDMY, TLS_ARG)
docker compose --profile tls up -d caddy
```

**LAN-Betrieb (Default, `TLS_ARG=internal`):** Caddy erzeugt eine eigene CA.
Einmalig das Root-Zertifikat exportieren und auf den Geräten (Handys der Eltern!)
installieren und als vertrauenswürdig markieren:

```bash
docker compose --profile tls exec caddy cat /data/caddy/pki/authorities/local/root.crt > caddy-root.crt
```

Die Hostnamen müssen auf den Server zeigen (Router-DNS oder hosts-Datei).
Danach die Ports 8082/8085/4321 nicht mehr nach außen veröffentlichen.

**Internet-Betrieb:** echte Domains in `SITE_*` eintragen, `TLS_ARG=du@example.org`
setzen, Ports 80/443 freigeben – Caddy holt die Zertifikate automatisch.

## 6b. Datenbank (PostgreSQL, Standard)

Seit A10 läuft Traccar auf **PostgreSQL** (`postgres:16-alpine`), konfiguriert über
Umgebungsvariablen (`CONFIG_USE_ENVIRONMENT_VARIABLES=true`, `DATABASE_*` in `.env`).
Traccar legt Schema und Admin beim ersten Start selbst an – **der erste registrierte
Benutzer wird Administrator** (siehe Abschnitt 4).

H2-Fallback (nur wenn gewünscht): `DATABASE_DRIVER=org.h2.Driver`,
`DATABASE_URL=jdbc:h2:./data/database`, `DATABASE_USER=sa`, `DATABASE_PASSWORD=` in
`.env` setzen und den `postgres`-Dienst stoppen.

## 7. Backup & Umzug auf den Thin Client

```bash
# Volumes sichern
docker run --rm -v ultimatetracker_audio-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/audio-data.tgz -C /data .
docker run --rm -v ultimatetracker_traccar-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/traccar-data.tgz -C /data .
```

Umzug: auf dem Thin Client Docker installieren, Repo klonen/kopieren, `server/.env`
übernehmen, Volumes zurückspielen, `docker compose up -d`.

## 8. Troubleshooting

| Symptom | Ursache/Abhilfe |
|---|---|
| `permission denied` bei `docker` | Gruppe `docker` greift erst in neuer Session: `wsl --terminate UltimateTracker` |
| Port belegt | `ss -tlnp` in der Distro; Ports in `docker-compose.yml` anpassen |
| Traccar leer | OsmAnd-GET prüfen (Parameter `id`, `lat`, `lon`); Logs: `docker compose logs traccar` |
| Bridge konvertiert nicht | `docker compose exec audio-bridge ffmpeg -version` |
| Windows erreicht Ports nicht | WSL-Neustart: `wsl --shutdown` (beendet alle Distros!) |
