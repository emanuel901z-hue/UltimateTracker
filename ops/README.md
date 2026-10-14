# ops – Betriebswerkzeuge der Server-Maschine

Bewusst **getrennt** vom Tracker-Stack (`server/`): eigenes Compose-Projekt
`utops`, eigene Volumes, unabhängige Updates. Alles hier ist **optional** – der
Tracker läuft ohne diese Dienste.

| Dienst | Zweck | Port (nur LAN) | Anmeldung |
|---|---|---|---|
| `ntfy` | selbst gehosteter Push-Dienst – Ziel für Apprise-Alarme, **kein Dritter** | 8086 | unratbares Thema |
| `dozzle` | Container-Logs live und durchsuchbar im Browser (Ergänzung zu Portainer) | 8088 | `dozzle-users.yml` |
| `diun` | meldet neue Image-Versionen an ntfy – **kein Auto-Update** (unsere Images sind bewusst gepinnt) | – | – |
| `beszel` | Verlaufs-Metriken (CPU/RAM/Disk/Container) + Alarme | 8090 | im Hub anlegen |

## Einrichten

```bash
cd ~/ops
cp .env.example .env
openssl rand -hex 8        # -> NTFY_TOPIC eintragen (unratbar!)

# Zugang für Dozzle erzeugen (Passwort ersetzen):
docker run --rm amir20/dozzle:v11.1.3 generate admin \
  --password 'DEIN-PASSWORT' --email admin@ultimatetracker.local > dozzle-users.yml

docker compose up -d
docker compose ps
```

## Alarme in der Bridge auf ntfy zeigen lassen

In `server/.env`:

```env
APPRISE_URLS=ntfy://ntfy:80/<NTFY_TOPIC>
```

Dann die Bridge neu erlösen (`docker compose --profile tls up -d audio-bridge`).
Test – muss `ok` melden:

```bash
cd ~/UltimateTracker/server
docker compose exec audio-bridge python -c "import app.main as m; m.notify('Test','Hallo vom Tracker')"
```

**Am Handy:** ntfy-App installieren, Server `http://10.1.9.53:8086` hinzufügen,
Thema abonnieren. Alternativ in `APPRISE_URLS` ein anderes Ziel eintragen
(kommasepariert), z. B. `tgram://<bot-token>/<chat-id>` oder
`mailto://user:pass@gmail.com` – Apprise unterstützt über 100 Dienste.

## Beszel-Agent (Verlaufs-Metriken)

Der Hub läuft mit `docker compose up -d beszel`. Für die Systemwerte braucht er
einen Agenten, dessen Zugangsdaten der Hub erzeugt:

1. <http://10.1.9.53:8090> öffnen, Admin-Konto anlegen.
2. „Add system" → Name `manucloud`, Host `beszel-agent`, Port `45876`.
3. Die angezeigten Werte `KEY` und `TOKEN` in `docker-compose.yml` beim Dienst
   `beszel-agent` eintragen (Abschnitt ist dort vorbereitet) und
   `docker compose up -d beszel-agent` starten.

## Hinweise

- `dozzle-users.yml` und `.env` sind **gitignoriert** (enthalten Geheimnisse).
- Alle Ports sind per UFW auf das LAN beschränkt – siehe
  [`docs/operations-manucloud.md`](../docs/operations-manucloud.md).
- `ntfy` hat keine eigene Anmeldung: Schutz ist das unratbare Thema **und** die
  LAN-Beschränkung. Für Internet-Betrieb zuerst `NTFY_AUTH_*` einrichten.
