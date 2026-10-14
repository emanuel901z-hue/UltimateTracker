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
- Optional (Profil `findmy`): Google-Find-Hub-WebUI und Apple-Endpunkt
  (`macless-haystack`) sind **nur über Caddy** erreichbar
  (`https://findmy.localhost`, `https://apple.localhost`) und liegen damit
  hinter der Anmeldung der Eltern-UI – **keine zweite Anmeldung** ✓.
  Anisette läuft rein intern.
  Details: [`findmy.md`](findmy.md).
- Tracker-Endpunkte (mit `X-Auth-Token: <DEVICE_TOKEN>`):
  - `GET /api/v1/device/pending?device_id=<IMEI>`
  - `POST /api/v1/device/messages` (Multipart: `device_id`, `audio`)
  - `GET /api/v1/device/messages/{id}/audio`

## 5b. Eltern-UI: Benutzer & Anmeldung (mehrere Kinder, mehrere Eltern)

**Erststart ohne Terminal:** Existiert noch kein Konto, zeigt die UI beim ersten
Aufruf „**Konto anlegen**" (der erste Benutzer wird Administrator – wie bei
Traccar). Danach übernimmt der Setup-Assistent (Abschnitt 5c). Eine
`server/.env` ist dafür **nicht nötig**: `DEVICE_TOKEN`, `PARENT_TOKEN` und der
Traccar-Administrator entstehen automatisch; die Tokens liegen in der Datenbank
und überleben Neustarts. Der Assistent zeigt den Device-Token zum Kopieren an
(für die Firmware-Einrichtung).

Die Eltern-UI hat einen **richtigen Login** (Benutzerkonten mit PBKDF2-Hashes,
Sitzungstoken, 30 Tage gültig). Der erste Administrator entsteht beim Start aus
`server/.env`:

```env
PARENT_USER=admin
PARENT_PASSWORD=…        # mindestens 10 Zeichen, nicht in der Sperrliste
```

Weitere Zugänge (zweiter Elternteil, Großeltern) legt ein Administrator in der
UI/API an:
`POST /api/v1/auth/users {"username": "…", "password": "…", "role": "parent|admin"}`.

Der feste `PARENT_TOKEN` bleibt als **Rückfallweg** bestehen (Skripte,
Smoke-Test, Erstinstallation) und gilt als Administrator.

**Passwörter:** Jeder Zugang kann sein eigenes Passwort in der UI ändern
(„Passwort ändern" oben; dabei werden **alle anderen Sitzungen beendet**).
Administratoren können in der Karte „Benutzer" ein Passwort **zurücksetzen**,
ohne das alte zu kennen (z. B. wenn ein Elternteil es vergessen hat) – auch
dabei enden die Sitzungen des betroffenen Kontos. Passwortregeln: mindestens
10 Zeichen, keine Standardsperrwörter (`app/auth.py`).

**Mehrere Kinder:** Die Karte „Kinder" zeigt alle Tracker mit Akkustand, letzter
Position und Suchmodus; „auswählen" schaltet Status, Nachrichten und Aufnahme auf
das jeweilige Kind um. Der **Suchmodus ist pro Kind** (`device_id`) – bei fünf
Kindern piept also nur das gesuchte. Nachrichten und Positionen werden je Gerät
geführt; Traccar zeigt ohnehin alle Geräte auf der Karte.

## 6a. Ein Login für alle Dienste (Single Sign-on)

Die Eltern-UI ist die **Anmeldung**: Caddy prüft bei Traccar, Google- und
Apple-Oberfläche das Sitzungs-Cookie der Bridge (`forward_auth` auf
`/api/v1/auth/verify`). Wer dort angemeldet ist, kommt ohne zweite Anmeldung
durch.

| Dienst | Zugangsschutz | Eigene Anmeldung zusätzlich |
|---|---|---|
| Eltern-UI/API | Benutzerkonto (PBKDF2 + Sitzungstoken) | – |
| Karte in der UI | läuft über die Bridge (`/api/v1/parent/map`) | **keine** ✓ |
| Traccar (Verlauf, Geofences, Berichte) | **Traccars eigenes Konto** – der bequeme Weg ist „öffnen" (Einmal-Ticket, automatische Anmeldung) | automatisch per Ticket ✓ |
| Google-Find-Hub-WebUI | über die Bridge-Session (Caddy `forward_auth`); „öffnen" löst ein Einmal-Ticket ein | **keine** ✓ |
| Apple (macless-haystack) | über die Bridge-Session (Caddy `forward_auth`); „öffnen" löst ein Einmal-Ticket ein | **keine** ✓ |

**Warum Traccar kein `forward_auth` mehr hat:** Browser verwerfen Cookies mit
`Domain=localhost` (RFC 6265 verlangt einen Punkt in der Domain). Ein Gate auf
`traccar.localhost` könnte also nie erfüllt werden – jede direkte Traccar-URL
endete in „HTTP ERROR 401". Deshalb schützt Traccar sich mit **seinem eigenen
Konto**; die Eltern kommen über den „öffnen"-Link im Dienste-Bereich ohne
zweite Eingabe hinein (Einmal-Ticket, 120 s gültig).

**Geräte-Zuordnung:** Traccar legt Geräte bei unbekannten Uploads automatisch an
(`database.registerUnknown`), ordnet sie aber **keinem Benutzer** zu – die
Oberfläche zeigt dann „Registriere dein erstes Gerät", obwohl die Geräte
existieren. Die Bridge ordnet deshalb nach jedem Weiterleiten alle bekannten
Geräte dem Konto zu (über `?all=true`, höchstens alle 10 Minuten, idempotent).

**Gate-Dienste (Google/Apple):** Sie haben kein eigenes Konto und bleiben hinter
dem `forward_auth`-Gate. Das Sitzungscookie der Eltern-UI erreicht sie aber
nicht (`Domain=localhost`, siehe oben) – ein direkter Aufruf endete deshalb in
„HTTP ERROR 401". Deshalb löst „öffnen" auch hier ein **Einmal-Ticket** ein:
Caddy leitet `/_sso/*` **vor** dem Gate an die Bridge, die auf dem Ziel-Host ein
**host-only** Sitzungscookie setzt und auf die Wurzel weiterleitet
(`docs/decisions.md` D-018). Danach lässt `forward_auth` durch.

Antwortet ein Dienst nicht (z. B. weil er noch startet), liefert Caddy auf den
Dienst-Hosts eine **eigene, verständliche Fehlerseite** (502/503/504, Snippet
`ut_unavailable_page`) mit Verweis auf die Eltern-UI – statt der nackten
Browser-Meldung „Diese Seite funktioniert nicht". In der Dienste-Liste bietet
die UI „öffnen" außerdem **nur bei erreichbaren Diensten** an.

**Automatische Traccar-Anmeldung (Cookie):** Die Eltern-UI verlinkt Traccar auf
`https://<SITE_TRACCAR>/_sso/traccar`. Caddy leitet diesen Pfad an die Bridge –
**auf demselben Hostnamen**, deshalb darf die Bridge das Traccar-Sitzungscookie
setzen. Sie meldet sich serverseitig mit `TRACCAR_SSO_EMAIL`/`TRACCAR_SSO_PASSWORD`
aus `server/.env` an (Werte stehen in `ADMIN-ZUGANG.txt`) und gibt das
`JSESSIONID`-Cookie an den Browser weiter. Ergebnis: **kein zweites Login** ✓
(im Browser verifiziert).

**Keine zweite Anmeldung bei Google/Apple:** Die Find-My-Oberflächen
veröffentlichen keine Ports mehr und laufen ohne eigene Basic-Auth – sie
sind ausschließlich über Caddy und damit hinter dem SSO der Eltern-UI
erreichbar (beim „öffnen"-Klick wird ein Einmal-Ticket eingelöst). Es gibt
also nichts zu konfigurieren: **ein Login, alle Dienste** ✓. (Nur wer die
Dienste bewusst direkt veröffentlicht, setzt in `server/.env` wieder
`WEBUI_USER`/`WEBUI_PASSWORD`.)

**Warum die Karte nicht mehr eingebettet wird:** Traccar verlangt sein eigenes
Konto, und in einem iframe hält diese Sitzung wegen der Third-Party-Cookie-
Blockade der Browser oft nicht – man meldet sich also immer wieder an. Deshalb
zeichnet die Eltern-UI die Karte **selbst** (Leaflet, selbst gehostet in
`static/vendor/leaflet/`) aus `/api/v1/parent/map`: letzte Position je Kind
(Marker) und je Find-My-Beacon (Kreis). Traccar bleibt für Verlauf, Geofences
und Berichte verlinkt.

**Kacheln:** Standard sind OpenStreetMap-Kacheln (`MAP_TILES` in `server/.env`)
– dabei sieht der Kachelserver, welche Ausschnitte abgerufen werden. Für „keine
externen Aufrufe" einen eigenen Kachelserver eintragen; die Karte funktioniert
auch ohne Kacheln (Marker + Umriss bleiben sichtbar).

**Cookies:** Beim Zugriff über `*.localhost` setzt die Bridge `Domain=localhost`
– damit gilt die Anmeldung für `audio.`, `traccar.`, `findmy.` und
`apple.localhost`. Für eigene Domains mit Subdomains in `server/.env`
`SESSION_COOKIE_DOMAIN=.example.org` setzen. Beim Betrieb über **einen** Namen
mit verschiedenen Ports (DynDNS, Abschnitt 9.2) greift das Cookie automatisch –
Ports sind für Cookies irrelevant.

**Was nicht geht:** die Anmeldung *innerhalb* von Traccar ersetzen (Traccar kennt
kein Header-Login; dafür bräuchte es OpenID Connect). Die Caddy-Prüfung
verhindert aber, dass überhaupt jemand ohne Eltern-Login hinkommt – und der
Browser merkt sich die App-Anmeldungen danach.

## 5c. Setup-Assistent (Einführung für Eltern)

Beim ersten Login springt die UI automatisch in den Tab **„Einrichtung"**,
solange noch kein Tracker Daten geliefert hat. Der Assistent führt in sieben
Schritten durch die Einführung – und **prüft jeden Schritt serverseitig**
(`GET /api/v1/parent/setup`), damit „Weiter" erst freigegeben wird, wenn der
Schritt wirklich erledigt ist:

| Schritt | Prüfung | überspringbar |
|---|---|---|
| Willkommen | – | – |
| Tracker anlegen (IMEI + Name) | Gerät in der Registry | – |
| SIM eintragen (ICCID/MSISDN) | ICCID gesetzt | ✓ |
| Karte prüfen (Traccar) | Traccar erreichbar | ✓ |
| Benachrichtigungen | Web-Push abonniert | ✓ |
| Zertifikat einrichten | CA-Datei vorhanden (Caddy läuft) | ✓ |
| **Apple Find My** | Apple-ID in `macless-data/config.ini` hinterlegt (Formular: Tab „Geräte" → „Apple Find My einrichten", auch über den Assistenten erreichbar) | ✓ |
| Funktionstest (PTT drücken) | Position/Nachricht/Beacon angekommen | ✓ |
| Fertig | Zusammenfassung + nächste Schritte | – |

Nach der Einrichtung bleibt der Tab erhalten (zum Nachschlagen), die
Übersichtsseite zeigt einen Hinweis, solange etwas offen ist. Fehleingaben
werden feldbezogen und in Klartext gemeldet (z. B. „Die IMEI besteht aus genau
15 Ziffern, ohne Leerzeichen."), und der Speichern-Knopf blockiert bis dahin.

## 6. TLS (Profil `tls`, vor dem Produktiveinsatz!)

```bash
cd ~/UltimateTracker/server
# Hostnamen in .env setzen (SITE_AUDIO/SITE_TRACCAR/SITE_FINDMY/SITE_APPLE, TLS_ARG)
docker compose --profile tls up -d caddy
```

Damit sind alle Oberflächen unter **einem** TLS-Frontdoor erreichbar:

| Hostname (Default) | Dienst |
|---|---|
| `audio.localhost` | Eltern-UI/API (enthält die Dienste-Übersicht, s. u.) |
| `traccar.localhost` | Traccar (Karte) |
| `findmy.localhost` | Google-Find-Hub-WebUI |
| `apple.localhost` | Apple-Oberfläche (macless-haystack, Profil `findmy`) |

**LAN-Betrieb (Default, `TLS_ARG=internal`):** Caddy erzeugt eine eigene CA.
Das Root-Zertifikat gibt es **in der UI** zum Herunterladen – Tab „Betrieb" →
Karte „Zertifikat" oder im Setup-Assistenten (Schritt „Zertifikat einrichten"),
mit Anleitung für Windows/Android/iOS. Der Download läuft bewusst über HTTP und
ohne Anmeldung (`GET /ca.crt`), weil er ja gerade dann nötig ist, wenn HTTPS
noch eine Warnung zeigt.

Für Skripte/Server ohne Browser geht es weiterhin klassisch:

```bash
docker compose --profile tls exec caddy cat /data/caddy/pki/authorities/local/root.crt > caddy-root.crt
```

Die Hostnamen müssen auf den Server zeigen (Router-DNS oder hosts-Datei).
Die Find-My-Dienste veröffentlichen gar keine Ports mehr – Zugriff nur über
Caddy (SSO). Für die Hauptdienste gilt: 8082/8085 nicht nach außen öffnen.

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

**Der Datenbestand liegt in PostgreSQL** (Positionen, Fahrten, Geofences) – nicht
in `traccar-data` (dort stehen nur Medien). Deshalb sichert
`scripts/backup-volumes.sh` **beides**: einen konsistenten `pg_dump` **und** die
Volumes (Audio-Nachrichten, Geräte-Registry, Find-My, Zertifikate).

```bash
bash scripts/backup-volumes.sh [Zielverzeichnis]   # Standard: ~/UltimateTracker/backups
```

Cron (täglich 03:00) – Beispiel steht im Kopf des Skripts:

```cron
0 3 * * * bash "$HOME/UltimateTracker/scripts/backup-volumes.sh" >> "$HOME/UltimateTracker/backups/backup.log" 2>&1
```

Einzelne Volumes von Hand:

```bash
docker run --rm -v ultimatetracker_audio-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/audio-data.tgz -C /data .
```

Wiederherstellen (Beispiele):

```bash
gunzip -c traccar-db-<STAMP>.sql.gz | docker exec -i <postgres-container> psql -U traccar traccar
docker run --rm -v ultimatetracker_audio-data:/data -v "$PWD":/backup alpine \
  sh -c "rm -rf /data/* && tar xzf /backup/audio-data-<STAMP>.tgz -C /data"
```

Umzug: auf dem Thin Client Docker installieren, Repo klonen/kopieren, `server/.env`
übernehmen, Datenbank-Dump einspielen, Volumes zurückspielen, `docker compose up -d`.

## 8. Blick vom Windows-Host & parallele Test-Instanz

### 8.1 Die WSL-Instanz vom Windows-Browser aus ansehen

WSL2 leitet `localhost` automatisch weiter – es ist **kein** zweiter Stack nötig:

| Dienst | URL im Windows-Browser |
|---|---|
| Eltern-UI/API (**Einstiegspunkt für alles**) | <http://localhost:8085> |
| Traccar | <http://localhost:8082> |
| Google-Find-My-WebUI | <https://findmy.localhost> (über den SSO-Login) |

**„Eine App"-Übersicht:** Die Eltern-UI zeigt oben eine **Dienste-Karte** mit
Live-Status aller Dienste (Karte, Find My Google/Apple, Anisette, Apple-Bridge)
und Links dorthin. Die Traccar-Karte lässt sich zusätzlich **direkt einbetten**
(Traccar liefert kein `X-Frame-Options`, das ist geprüft). Der Status wird
serverseitig im Docker-Netz ermittelt (`GET /api/v1/parent/services`, 10 s gecacht).

Im HTTPS-Betrieb werden die Links automatisch auf die `SITE_*`-Hostnamen
umgestellt (z. B. `https://traccar.localhost`), sonst auf
`http://<aktueller Host>:<Port>` – funktioniert also auch vom Handy im LAN.

Für **HTTPS** (Profil `tls`): `.localhost`-Namen lösen im Browser auf 127.0.0.1
auf, also <https://audio.localhost> / <https://traccar.localhost>. Damit die
Warnung verschwindet, einmalig die Caddy-CA in den Windows-Zertifikatsspeicher
importieren (Datei vorher per `caddy-root.crt`-Export holen, siehe Abschnitt 6):

```powershell
certutil -addstore -user Root caddy-root.crt
```

**Docker Desktop** (falls du es installierst): in den Einstellungen unter
*Resources → WSL Integration* die Distribution **UltimateTracker deaktivieren** –
sonst mischen sich zwei Docker-Engines in derselben Distro.

### 8.2 Zweite Instanz zum Ausprobieren (ohne die laufende anzufassen)

```bash
# in der WSL, aus dem Repo-Verzeichnis
bash scripts/start-test-instance.sh                  # Kern-Stack (Postgres, Traccar, Bridge)
bash scripts/start-test-instance.sh --profile tls    # zusätzlich Caddy

# Stoppen (entfernt auch die Test-Volumes):
docker compose -p uttest down -v
```

| | Hauptinstanz | Test-Instanz |
|---|---|---|
| Compose-Projekt | `ultimatetracker` | `uttest` |
| Traccar | 8082 / 5055 | **9082 / 9055** |
| Audio-Bridge | 8085 | **9085** |
| Caddy (Profil `tls`) | 80 / 443 | **8080 / 8443** |
| Find-My-Dienste | nur über Caddy (keine Ports) | **5321 / 7176 / 6500** (nur Test-Instanz) |
| Volumes | `ultimatetracker_*` | `uttest_*` (getrennt) |
| Datenbank | bestehende Daten | **leer** – Traccar legt einen neuen Admin an (erster registrierter Benutzer wird Administrator) |

Beide Instanzen nutzen dieselbe `server/.env` (gleiche Tokens) und dieselben
Config-Bind-Mounts (nur lesend). Die Container-Namen sind **nicht** mehr fest
verdrahtet (`ut-*`), sondern vom Compose-Projekt abgeleitet – Skripte wie der
Smoke-Test finden den Bridge-Container dynamisch.

### 8.3 Zugriff vom Handy im LAN (WSL2 nutzt NAT!)

WSL2 nutzt **NAT**: Die veröffentlichten Ports sind **nur auf `localhost`** sichtbar.
Vom Handy ist `http://<host-ip>:8085` deshalb nicht erreichbar – das ist kein
Konfigurationsfehler im Stack. Drei Wege:

| Weg | Aufwand | Bemerkung |
|---|---|---|
| **Port-Weiterleitung auf dem Host** | `powershell -ExecutionPolicy Bypass -File scripts\windows-lan-forward.ps1` (als **Administrator**) | leitet 8085/8082/80/443 per `netsh portproxy` auf die WSL-IP und öffnet die Firewall-Regeln. Nach jedem Distro-Neustart erneut ausführen (WSL-IP ändert sich) |
| **Mirrored Networking** | `C:\Users\<du>\.wslconfig`: `[wsl2]` + `networkingMode=mirrored`, danach `wsl --shutdown` | WSL teilt sich die Host-IP → LAN-Zugriff ohne Weiterleitung (Windows 11 22H2+). Gilt für **alle** Distros |
| **Tailscale** (empfohlen für „von außen") | in der WSL: `curl -fsSL https://tailscale.com/install.sh \| sh` + `sudo tailscale up` | eigenes Tailnet-Gerät, **kein** offener Port, Zugriff vom Handy überall – ohne DynDNS. Ideal, weil auf dem Windows-Host ohnehin Tailscale läuft |

**HTTPS über die nackte IP:** In `server/.env` `SITE_LAN=192.168.1.50` setzen – Caddy
stellt dafür ein Zertifikat aus. Wichtig: Browser senden bei **IP-Adressen kein
SNI**; deshalb steht im Caddyfile zusätzlich `default_sni {$SITE_LAN:localhost}`.
Ohne das schlägt der TLS-Handshake fehl („internal error", HTTP 000).
Das Zertifikat stammt aus der internen Caddy-CA → auf dem Handy einmalig
`caddy-root.crt` importieren (Abschnitt 6). Für den Schnelltest genügt
`http://<host-ip>:8085` (über die Port-Weiterleitung oben).

## 9. Operationszentrale & Internet-Betrieb

### 10.1 Was gehört wohin (und warum nicht alles in Traccar)

| Aufgabe | Wo | Warum dort |
|---|---|---|
| Karte, Verlauf, Geofences, Berichte, Fahrtenbuch | **Traccar** (8082) | ausgereifte Tracking-App |
| Sprachnachrichten, Geräte-Registry, Benutzer, Suchmodus, OTA, SIM/SMS, Monitoring, Einstellungen, Backup | **Audio-Bridge** (8085) – die Operationszentrale | hier steckt unsere gesamte Geräte-/Familienlogik |
| Karte zusätzlich **eingebettet** | in der Bridge-UI | ein Einstiegspunkt, kein Wechsel |
| Apple/Google Find My | optional (Profil `findmy`) | experimentell, eigenständige Werkzeuge |

**Traccar als Basis wäre ein Fork:** Traccar ist eine Java-Anwendung mit
kompilierter Vue-Oberfläche; eigene Seiten/Logik darin zu integrieren heißt, die
Web-App zu ersetzen – und damit bei **jedem** Update zu brechen. Der tragfähige
Weg ist umgekehrt: **eine Oberfläche (Bridge) mit einem Login**, die Traccar
einbettet und verlinkt. Deshalb sind Karte, Dienste-Status, Kinder-Übersicht,
Benutzer, Einstellungen, Betriebswerte und Backup in der Bridge-UI gebündelt.

### 10.2 Ein Einstiegspunkt von außen (DynDNS + ein Name)

Ziel: vom Handy nur `https://<dein-dyndns-name>` aufrufen → Login → alles da.

1. **Router**: nur **80** und **443** auf den Host weiterleiten (Let's Encrypt
   braucht 80 für die Prüfung). Optional zusätzlich **8443** für die vollständige
   Traccar-Oberfläche. Alle anderen Ports (8082, 8085 …) **nicht** öffnen –
   die Find-My-Dienste sind ohnehin nur intern erreichbar.
2. **`server/.env`** anpassen:
   ```env
   SITE_AUDIO=meinname.dyndns.org
   SITE_TRACCAR=meinname.dyndns.org:8443
   SITE_FINDMY=meinname.dyndns.org:8444
   SITE_APPLE=meinname.dyndns.org:8445
   TLS_ARG=du@example.org        # Let's Encrypt; Caddy holt die Zertifikate selbst
   ```
3. `docker compose --profile tls up -d caddy`
4. Handy: `https://meinname.dyndns.org` → Login → **„Zum Home-Bildschirm"**
   (PWA) → danach wie eine App, mit Push-Benachrichtigungen.

Die eingebettete Karte funktioniert auch hier, weil die UI die Links automatisch
auf die `SITE_*`-Hostnamen umstellt (HTTPS-Modus).

### 10.3 Sicherheits-Checkliste für den Internet-Betrieb

| Punkt | Status/Umsetzung |
|---|---|
| TLS überall | Caddy-Profil `tls`, Let's Encrypt (`TLS_ARG=<E-Mail>`) |
| Anmeldung | Bridge: Benutzerkonten (PBKDF2, Sitzungstoken); Traccar: eigenes Konto (Auto-Login per Einmal-Ticket); Find-My-WebUIs: hinter dem SSO, ohne eigene Anmeldung |
| Passwörter | mindestens 10 Zeichen erzwungen; Admin-Reset dokumentiert (Abschnitt 10) |
| Nur nötige Ports | 80/443 (+ ggf. 8443/8444/8445) – Datenbank, Postgres, Anisette bleiben intern |
| Updates | Images sind gepinnt (Abschnitt 2/5) – bewusst aktualisieren, nicht automatisch |
| Backups | UI-Knopf (Abschnitt 10.4) + `scripts/backup-volumes.sh` (pg_dump **und** Volumes, Abschnitt 7) |
| Angriffsfläche | Find-My-Dienste nur bei Bedarf starten (`--profile findmy`) |
| Rate-Limits | Caddy-Plugin (`caddy-ratelimit`) oder fail2ban auf 401er – optional |
| Alternative ohne Exposition | **Tailscale/WireGuard**: Geräte im privaten Netz, kein offener Port |

### 10.4 Betrieb in der UI

| Karte | Inhalt |
|---|---|
| **Dienste** | Live-Status aller Dienste + Links (Karte einbettbar) |
| **Kinder** | pro Tracker: Akku, letzte Position, offene Nachrichten, Suchmodus |
| **Betrieb** | Laufzeit, Last, Speicher, Plattenplatz, Datenbestand, letztes Aufräumen/Backup + Knöpfe „Aufräumen jetzt" und „Backup herunterladen" |
| **Einstellungen** | Poll-Intervalle, Suchmodusdauer, Aufbewahrung, Akkuschwelle, Benachrichtigungen – **wirken sofort** (überschreiben die `.env`-Startwerte) |
| **Benutzer** | Konten anlegen/löschen, Passwort zurücksetzen (nur Admin) |

Damit ist die Bridge die Operationszentrale: ein Login, Monitoring,
Konfiguration, Administration und Wartung an einer Stelle – Traccar liefert die
Karte, die eingebettet daneben liegt.

## 10. Repo veröffentlichen (Remote & Zugangsdaten)

Das Projekt bleibt lokal, bis du es bewusst veröffentlichst. Wenn es soweit ist:

```bash
cd /d/Projekte/UltimateTracker
git remote add origin https://github.com/<user>/UltimateTracker.git
git push -u origin main          # veröffentlicht den Branch
```

**Zugangsdaten gehören nicht in `server/.env`**, sondern in die Projekt-Git-Settings
– dort sind sie nie versioniert (`.git/` wird nie committet):

```bash
git config --local credential.helper "store --file=$PWD/.git/credentials"
printf 'https://<user>:<PAT>@github.com\n' > .git/credentials
icacls ".git\\credentials" /inheritance:r /grant:r "$USERNAME:F"   # Windows
```

Prüfen ohne zu veröffentlichen:

```bash
GIT_TERMINAL_PROMPT=0 git ls-remote --heads origin   # Exit 0 = Zugang ok
```

**Zwei Netze vor versehentlichen Secrets:**

1. `.gitignore` hält `.env`, `ADMIN-ZUGANG.txt`, `*.bin`, Laufzeitdaten draußen.
2. `scripts/git-hooks/pre-commit` blockt `.env`-Dateien und Secret-Muster
   (Installation: `cp scripts/git-hooks/pre-commit .git/hooks/pre-commit`).

**Vor dem ersten Push einmal prüfen:**

```bash
# Muster wie im Hook (scripts/git-hooks/pre-commit) – hier bewusst umschrieben,
# damit dieser Text selbst keinen Secret-Scanner triggert:
git grep -nE 'github[_-]pat|AKIA[0-9A-Z]{16}|API_CLIENTSECRET=' -- . || echo "sauber"
git log --all -S'github_pat' --oneline | wc -l    # 0 = nie in der Historie
```

## 11. Troubleshooting

| Symptom | Ursache/Abhilfe |
|---|---|
| `ADMIN-ZUGANG.txt` verschwindet nach `sync-to-wsl.sh` | Die Datei gibt es **nur in der WSL** (Secrets). Der Sync muss sie ausnehmen – siehe Ausschlussliste im Skript (`server/ADMIN-ZUGANG.txt`, `server/.env`, `server/caddy-root.crt`). Fehlt der Eintrag, löscht `rsync --delete` die Datei. |
| Traccar-Admin-Passwort unbekannt (z. B. weil die Zugangsdatei weg ist) | Nicht-destruktive Wiederherstellung: (1) Registrierung kurz aktivieren: `UPDATE tc_servers SET registration = true;`, (2) temporären Benutzer per API registrieren (`POST /api/users` mit Name/E-Mail/Passwort), (3) dessen Hash auf den Admin kopieren: `UPDATE tc_users AS admin SET hashedpassword = tmp.hashedpassword, salt = tmp.salt FROM tc_users AS tmp WHERE admin.email = '<admin-mail>' AND tmp.email = '<temp-mail>';`, (4) temporären Benutzer löschen, (5) `UPDATE tc_servers SET registration = false;`, (6) Login per `POST /api/session` prüfen (Formulardaten, nicht JSON!). |
| `POST /api/session` liefert HTTP 415 | Traccar erwartet **Formulardaten** (`--data-urlencode email=… password=…`), kein JSON. |

| Symptom | Ursache/Abhilfe |
|---|---|
| `permission denied` bei `docker` | Gruppe `docker` greift erst in neuer Session: `wsl --terminate UltimateTracker` |
| Port belegt | `ss -tlnp` in der Distro; Ports in `docker-compose.yml` anpassen |
| Traccar leer | OsmAnd-GET prüfen (Parameter `id`, `lat`, `lon`); Logs: `docker compose logs traccar` |
| Bridge konvertiert nicht | `docker compose exec audio-bridge ffmpeg -version` |
| Windows erreicht Ports nicht | WSL-Neustart: `wsl --shutdown` (beendet alle Distros!) |
