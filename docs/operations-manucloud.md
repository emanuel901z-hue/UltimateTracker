# Betrieb: manucloud (10.1.9.53) – die Server-Maschine

Diese Datei beschreibt **die Maschine**, auf der der Tracker-Stack produktiv
läuft (im Unterschied zu `docs/deployment.md`, das den Aufbau beschreibt).

## 1. Maschine

| Punkt | Wert |
|---|---|
| Host | `manucloud` (SSH-Alias, `~/.ssh/config`) |
| Adresse | `10.1.9.53` (und `10.1.9.208`), LAN `10.1.9.0/24`, Gateway `10.1.9.3` |
| OS | Ubuntu 24.04 LTS, Kernel 6.8, x86_64 |
| Hardware | 4 vCPU, 30 GiB RAM, 8 GiB Swap, **Intenso SSD 477 GB** (LVM, 466 GB nutzbar) |
| Docker | 29.9.0 + Compose v5.6.0, Loglimits + `live-restore` in `/etc/docker/daemon.json` |
| Zeit | Europe/Berlin, NTP synchron |
| Updates | `unattended-upgrades` aktiv |

## 2. Was läuft wo

| Bereich | Dienst | Port(s) | Anmerkung |
|---|---|---|---|
| **Tracker-Stack** (`~/UltimateTracker/server`) | `caddy` | 80, 443 | TLS-Frontdoor, interne CA |
| | `audio-bridge` | 8085 | Eltern-UI/API + Tracker-Uplink |
| | `traccar` | 8082, 5055 | Karte; 5055 = OsmAnd-Ingest |
| | `postgres` | – | **hier liegen die Positionen** |
| Betriebswerkzeuge (`~/ops`) | `ntfy` | 8086 | Push-Kanal für Alarme |
| | `dozzle` | 8088 | Container-Logs |
| | `beszel` | 8090 | Verlaufs-Metriken |
| | `diun` | – | Image-Update-Meldungen |
| Fremd | `HomeAssistant` | 8123, 18555, 40000 | läuft weiter (host-Netz) |
| | `portainer` | 9443 | Container-Verwaltung |

Profil `findmy` (Apple/Google) ist hier **nicht** gestartet.

## 3. Firewall (UFW)

Default: eingehend **abweisen**, ausgehend erlauben.

| Port | Von | Zweck |
|---|---|---|
| 22/tcp | LAN | SSH |
| 80, 443/tcp | überall | Caddy (später Let's Encrypt) |
| 8085, 8082, 5055/tcp | LAN | Tracker/UI, Traccar |
| 8086, 8088, 8090/tcp | LAN | ntfy, Dozzle, Beszel |
| 9443/tcp | LAN | Portainer |
| 8123, 18555, 40000/tcp, 5353/udp | LAN | HomeAssistant |

```bash
sudo ufw status verbose
```

**Sicherheitsnetz beim Ändern** (verhindert Aussperren):

```bash
sudo systemd-run --on-active=5min --unit=ufw-safety /usr/sbin/ufw disable
# ... Regeln ändern, neue SSH-Verbindung testen ...
sudo systemctl stop ufw-safety.timer
```

## 4. Zugänge

Geheimnisse stehen **nicht** in diesem Dokument:

| Zugang | Wo |
|---|---|
| Eltern-UI | `~/UltimateTracker/server/.env` → `PARENT_USER` / `PARENT_PASSWORD` |
| Traccar | `TRACCAR_SSO_EMAIL` / `TRACCAR_SSO_PASSWORD` (Auto-Login per Ticket) |
| Tracker-Token | `DEVICE_TOKEN` (im Setup-Assistenten sichtbar) |
| Portainer | eigenes Konto (beim Einrichten gesetzt) |
| Dozzle | `~/ops/dozzle-users.yml` |
| ntfy-Thema | `~/ops/.env` → `NTFY_TOPIC` |

Zertifikat fürs Handy: `http://10.1.9.53:8085/ca.crt` importieren → danach ist
`https://10.1.9.53/` ohne Warnung.

## 5. Backups

```bash
cd ~/UltimateTracker && bash scripts/backup-volumes.sh    # pg_dump + Volumes
```

- Ziel: `~/UltimateTracker/backups` (Aufbewahrung 30 Tage)
- **Cron:** täglich 03:30 (`crontab -l`)
- **Off-Site:** `scripts/pull-manucloud-backups.ps1` holt die Dateien auf den
  Windows-Host (Task Scheduler, täglich 04:30). Eine Sicherung auf derselben
  Platte schützt **nicht** gegen Plattenausfall.

Wiederherstellen: `docs/deployment.md` §7.

## 6. Alarme (Apprise → ntfy)

`~/UltimateTracker/server/.env`:

```env
APPRISE_URLS=ntfy://ntfy:80/<NTFY_TOPIC>
```

Damit melden sich Akku-warnungen, Suchmodus, neue Nachrichten **und** die
Betriebsmeldungen. Test:

```bash
docker compose exec audio-bridge python -c "import app.main as m; m.notify('Test','ok')"
```

## 7. Updates (bewusst, nicht automatisch)

```bash
cd ~/UltimateTracker && git pull
cd server && docker compose --profile tls pull && docker compose --profile tls up -d
cd ~/ops && docker compose pull && docker compose up -d
```

Image-Versionen sind gepinnt; **Diun** meldet per ntfy, wenn es Neues gibt.
Systempakete macht `unattended-upgrades` (Sicherheitsupdates) selbst.

## 8. Diagnose

| Frage | Befehl |
|---|---|
| Läuft alles? | `docker ps --format '{{.Names}}\t{{.Status}}'` |
| Bridge gesund? | `curl -s localhost:8085/healthz` |
| Dienste-Status | Eltern-UI → Übersicht → „Dienste" |
| Welche Quelle liefert? | Eltern-UI → Geräte → „Quellen (letzte Position)" |
| Container-Logs | `docker compose logs -f audio-bridge` oder Dozzle (8088) |
| Plattenplatz | `df -h /` · SMART: `sudo smartctl -H /dev/sda` |
| Firewall | `sudo ufw status verbose` |
| Fehlgeschlagene Logins | `sudo fail2ban-client status sshd` |

## 9. Was NICHT auf dieser Maschine liegt

- `xrdp` ist **deaktiviert** (Fernzugriff nur per SSH).
- TeamViewer ist installiert, aber inaktiv (kein Dienst) – kann entfernt werden.
- Teddycloud wurde entfernt (Volumes + Image).
