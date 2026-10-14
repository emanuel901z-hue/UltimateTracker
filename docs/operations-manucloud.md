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
| Updates | `unattended-upgrades` aktiv; journald auf 500 MB begrenzt |

## 2. Was läuft wo

| Bereich | Dienst | Port(s) | Anmerkung |
|---|---|---|---|
| **Tracker-Stack** (`~/UltimateTracker/server`) | `caddy` | 80, 443 | TLS-Frontdoor, interne CA |
| | `audio-bridge` | 8085 | Eltern-UI/API + Tracker-Uplink |
| | `traccar` | 8082, 5055 | Karte; 5055 = OsmAnd-Ingest |
| | `postgres` | – | **hier liegen die Positionen** |
| Betriebswerkzeuge (`~/ops`, Projekt `utops`) | `ntfy` | 8086 | Push-Kanal für Alarme (selbst gehostet) |
| | `dozzle` | 8088 | Container-Logs (Anmeldung aus `dozzle-users.yml`) |
| | `beszel` | 8090 | Verlaufs-Metriken (Agent optional) |
| | `diun` | – | meldet neue Image-Versionen an ntfy |
| System | `cockpit` | 9090 | OS-Verwaltung im Browser (systemd, LVM, Journal, Terminal) |
| | `portainer` | 9443 | Container-Verwaltung |
| | `fail2ban`, `smartd` | – | Login-Schutz, Plattenüberwachung |
| Fremd | `HomeAssistant` | 8123, 18555, 40000 | läuft weiter (host-Netz) |

Profil `findmy` (Apple/Google) ist hier **nicht** gestartet.

## 3. Firewall (UFW)

Default: eingehend **abweisen**, ausgehend erlauben.

| Port | Von | Zweck |
|---|---|---|
| 22/tcp | LAN | SSH |
| 80, 443/tcp | überall | Caddy (später Let's Encrypt) |
| 8085, 8082, 5055/tcp | LAN | Tracker/UI, Traccar |
| 8086, 8088, 8090, 9090/tcp | LAN | ntfy, Dozzle, Beszel, Cockpit |
| 9443/tcp | LAN | Portainer |
| 8123, 18555, 40000/tcp, 5353/udp | LAN | HomeAssistant |
| `tailscale0` | – | Tailscale (nach `tailscale up`) |

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
| Dozzle | `~/ops/dozzle-users.yml` (neu erzeugen: siehe `ops/README.md`) |
| ntfy-Thema | `~/ops/.env` → `NTFY_TOPIC` (auch die App am Handy braucht es) |
| Cockpit | Systemkonto (`administrator`) |

Zertifikat fürs Handy: `http://10.1.9.53:8085/ca.crt` importieren → danach ist
`https://10.1.9.53/` ohne Warnung.

## 5. Backups

```bash
cd ~/UltimateTracker && bash scripts/backup-volumes.sh    # pg_dump + Volumes
```

- Ziel: `~/UltimateTracker/backups` (Aufbewahrung 30 Tage)
- **Cron:** täglich **03:30**; schlägt der Lauf fehl, kommt sofort ein Alarm
- **Off-Site:** geplante Aufgabe **„UltimateTracker Backup-Abholung"** auf dem
  Windows-Host holt die Dateien täglich **04:30** nach `D:\Backups\manucloud`
  (`scripts/pull-manucloud-backups.ps1`, angelegt mit
  `scripts/register-backup-task.ps1`). Eine Sicherung auf derselben Platte
  schützt **nicht** gegen Plattenausfall.

Wiederherstellen: `docs/deployment.md` §7.

## 6. Alarme (ein Kanal für alles)

`~/UltimateTracker/server/.env`:

```env
APPRISE_URLS=ntfy://ntfy:80/<NTFY_TOPIC>
```

Damit melden sich Akku-Warnungen, Suchmodus und neue Nachrichten **und** die
Betriebsmeldungen der Maschine. Test:

```bash
docker compose exec audio-bridge python -c "import app.main as m; m.notify('Test','ok')"
```

**Betriebsmeldungen** (`ops/alerts/`, installiert nach `/usr/local/bin`):

| Skript | Wann | Meldet |
|---|---|---|
| `ut-check.sh` | Cron täglich **07:00** | Plattenplatz ≥ 85 %, SMART-Problem, Sicherung ≥ 2 Tage alt, Container nicht `running` |
| `ut-smart-alert.sh` | `smartd` (`-M exec`) | Plattenproblem sofort |
| `ut-alert.sh` | von beiden genutzt | sendet Titel/Text an ntfy |
| Backup-Cron | bei Fehlschlag | „Backup fehlgeschlagen" |

Am Handy: ntfy-App → Server `http://10.1.9.53:8086` → Thema abonnieren.

## 7. Updates (bewusst, nicht automatisch)

```bash
cd ~/UltimateTracker && git pull
cd server && docker compose --profile tls pull && docker compose --profile tls up -d
cd ~/ops && docker compose pull && docker compose up -d
```

Image-Versionen sind gepinnt; **Diun** meldet per ntfy, wenn es Neues gibt
(täglich 06:00). Systempakete macht `unattended-upgrades` selbst.

## 8. Diagnose

| Frage | Befehl |
|---|---|
| Läuft alles? | `docker ps --format '{{.Names}}\t{{.Status}}'` |
| Bridge gesund? | `curl -s localhost:8085/healthz` |
| Dienste-Status | Eltern-UI → Übersicht → „Dienste" |
| Welche Quelle liefert? | Eltern-UI → Geräte → „Quellen (letzte Position)" |
| Container-Logs | Dozzle (8088) oder `docker compose logs -f audio-bridge` |
| Verlauf CPU/RAM/Disk | Beszel (8090) |
| OS-Ebene (Dienste, LVM, Journal) | Cockpit (9090) |
| Plattenplatz / SMART | `df -h /` · `sudo smartctl -H /dev/sda` |
| Firewall | `sudo ufw status verbose` |
| Fehlgeschlagene Logins | `sudo fail2ban-client status sshd` |
| Betriebscheck sofort | `/usr/local/bin/ut-check.sh` |

## 9. Fernzugriff

- **SSH** (Schlüssel) – der normale Weg.
- **Tailscale** ist installiert (`tailscale` 1.104). Aktivieren:
  `sudo tailscale up` → Link im Browser bestätigen. Danach ist die Maschine ohne
  offene Ports von außen erreichbar; UFW erlaubt das Interface `tailscale0`.
- `xrdp` ist **deaktiviert**, TeamViewer inaktiv (Paket liegt noch).

## 10. Was NICHT auf dieser Maschine liegt

- Teddycloud wurde entfernt (Volumes + Image).
- Das Compose-Profil `findmy` (Apple/Google) ist hier nicht gestartet.
