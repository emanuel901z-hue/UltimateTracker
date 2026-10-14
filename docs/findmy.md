# Find My (Apple & Google) – optionale Ortung über Fremdnetze

Ziel: Ein BLE-Beacon (Tracker-Mod, zusätzlicher ESP32 oder separater Chip) wird
von fremden Smartphones empfangen; die Standorte kommen über Apples bzw. Googles
Netz zurück. Dieses Dokument beschreibt die **Gegenstücke im Docker-Stack**, die
Initialisierung (Keys/Geräteregistrierung) und die Auswertung – plus die Grenzen.

> **Status: EXPERIMENTELL.** Beide Wege nutzen reverse-engineerte Protokolle ohne
> offizielle Unterstützung. Apple filtert seit 2025 geklonte AirTag-Advertisements
> (OpenHaystack-Issue #273); der Google-Weg ist eine Community-Reimplementierung.
> Beides kann jederzeit brechen.

## 1. Voraussetzungen & Grenzen

| Punkt | Apple (Find My) | Google (Find Hub) |
|---|---|---|
| Offiziell für DIY? | nein (OpenHaystack) | nein (Community-Tools) |
| Konto nötig | Apple-ID mit 2FA (**nur SMS-2FA**) | Google-Konto + Chrome (Desktop) |
| Docker-Gegenstück | `findmy-bridge` (automatisch) + `anisette` + `macless-haystack` (Keys/UI) | `google-findmy-webui` (empfohlen) bzw. `google-findmy` (minimal) |
| Erst-Setup | **Eltern-UI** (Apple-ID + Passwort, dann SMS-Code im Tab „Geräte"; Helfer `apple-login`) | interaktiv (Chrome-Login in der WebUI) |
| Zuverlässigkeit | wackelig (Apple-Filter) | experimentell |
| Abdeckung | sehr hoch (iPhone-Dichte) | hoch (Android-Dichte) |

**Strombedarf:** Ein Beacon muss dauerhaft senden. Der ESP32-S3 kann im Deep Sleep
**nicht** advertisen → entweder Wake-Zyklen (1–3 mA Durchschnitt) oder ein
separater Always-on-Chip (z. B. ST17H66, µA-Bereich). Siehe `docs/decisions.md` D-009.

## 2. Apple: automatische Bridge (empfohlen) + Key-Tooling

Drei Bausteine arbeiten zusammen:

| Baustein | Aufgabe |
|---|---|
| `anisette` | Apple-Authentifizierung (Anisette-Daten), wird von der Bridge genutzt. Bei uns **`dadoum/anisette-v3-server`** (aktuell v2.2.2, Debian 13); der Client fragt die v1-kompatible Wurzel ab, das *Provision* ist v3 (`X-Apple-I-MD-RINFO`). Wechselbar über `ANISETTE_URL` in `server/.env` – nur auf **v3**-Server, ältere v1-Server können Apple-Sperren provozieren. |
| **`findmy-bridge`** (findmy.py) | **Automatisch**: holt die Standorte der DIY-/OpenHaystack-Beacons und pusht sie **in unsere Bridge** (`APPLE_BRIDGE_TARGET`, OsmAnd-Protokoll) – von dort in die Sensor-Fusion und (optional) nach Traccar |
| `macless-haystack` | Key-Generierung (`generate_keys.py`) und optional Web-UI für manuelle Sicht |

### 2a. Bridge starten und initialisieren

```bash
cd server
docker compose --profile findmy up -d anisette findmy-bridge
# Einmalig interaktiv (Apple-ID + SMS-2FA); bis dahin bleibt die Bridge idle:
docker compose --profile findmy exec findmy-bridge .venv/bin/findmy-traccar-bridge-init
```

Konfiguration über `server/.env`: `APPLE_BEACON_KEYS` (Private Keys der Beacons,
kommasepariert) und `APPLE_POLL_INTERVAL` (Default 3600 s).

**Ziel der Bridge:** Standardmäßig unser **OsmAnd-kompatibler Ingest**
(`APPLE_BRIDGE_TARGET=http://audio-bridge:8085/api/v1/findmy/osmand`). Damit
landen Apple-Positionen in der Sensor-Fusion, und Traccar bekommt **eine**
Position je Kind (statt eines Fremdgeräts). Nur zum Zurückschalten auf das alte
Verhalten zeigt die Variable wieder direkt auf Traccar (`http://traccar:5055`).
**Ban-Risiko:** Apple mag häufige Abfragen nicht – 1 Abfrage/30 min gilt als
„relativ sicher“, das Default (1/h) ist bewusst konservativ. Ein Zweit-Account
ist empfehlenswert.

### 2b. Keys erzeugen und Beacons flashen

1. `generate_keys.py` aus den macless-haystack-Releases laden.
2. Keypair erzeugen → liefert `*_devices.json` (Frontend) und die
   Base64-Keys: **Advertising-Key** in die Beacon-Firmware, **Private Key** in
   `APPLE_BEACON_KEYS`.
3. ESP32-Firmware (macless-haystack/OpenHaystack) mit dem Advertising-Key flashen –
   oder ST17H66-Clones als separaten Always-on-Beacon nutzen.

### 2c. macless-haystack-Web-UI (optional, manuelle Sicht)

**Über die Eltern-UI (empfohlen, ohne Terminal):** Tab **Geräte → „Apple Find My
einrichten"** → Apple-ID und Passwort eintragen → speichern. (Dieselbe Maske gibt
es im Setup-Assistenten, Schritt „Apple Find My" – der Schritt verweist auf das
Formular im Tab „Geräte", damit es auch später für weitere Kinder erreichbar
bleibt.) Die Bridge
schreibt damit `data/config.ini` im Volume `macless-data` (die interaktive
Abfrage des Images entfällt) und der Dienst startet automatisch neu
(`restart: on-failure`).

Enthält das Passwort ein `%`, wird es in der Datei als `%%` **maskiert**: der
Dienst liest die Datei mit `configparser`-Interpolation und bräche sonst mit
„'%' must be followed by '%' or '('" ab. Ob der Dienst schon läuft, zeigen die
Statuszeile in **Geräte → „Apple Find My einrichten"** (aktualisiert sich
automatisch, dazu „Status jetzt prüfen") und der Punkt in der Dienste-Liste.

> **Erste Anmeldung (2FA) direkt in der UI.** Das Image fragt den SMS-Code über
> `input()` ab – headless unmöglich. Dafür läuft im Profil `findmy` der kleine
> Helfer **`apple-login`** (`server/apple-login/watch.py`): Er führt die Anmeldung
> auf Anforderung aus und reicht den Code nach, den die Eltern-UI entgegennimmt.
> Gesteuert wird ausschließlich über Dateien im Volume `macless-data` – die Bridge
> braucht **keinen** Docker-Zugriff.
>
> Ablauf in **Geräte → „Apple Find My einrichten" → Apple-Anmeldung (2FA):**
> Apple-ID/Passwort speichern → „Anmeldung starten" → Code aus der SMS eintragen →
> „Code senden". Danach liegt `auth.json` im Volume und der Dienst startet von
> selbst. Das **Protokoll** in der UI zeigt, woran es ggf. hängt.
>
> Ohne Helfer (z. B. Profil nicht gestartet) geht es klassisch:
> `docker compose --profile findmy run --rm macless-haystack` (Apple-ID, Passwort,
> SMS-Code) – oder eine fertige `auth.json` übernehmen. Blockt Apple mit
> **HTTP 503** (`gsa.apple.com`) bzw. `ec -80045` („This action cannot be
> completed at this time"), ist das eine Einschränkung des **Apple-Kontos** (siehe
> Liste unten) – kein Fehler in der Einrichtung. Konto prüfen/bestätigen (und ggf.
> Zahlungs-/Kontodaten ergänzen, Stichwort „account score"):
> <https://account.apple.com> – die frühere Adresse `appleid.apple.com` leitet
> dorthin um (Apple ID heißt seit iOS 18 „Apple Account"; `appleid.apple.com`
> bleibt nur die OIDC-Domain).
> Der Endpunkt startet deshalb **nicht** in einer
> Neustart-Schleife, sondern wartet ohne Apple-Zugriffe auf `auth.json`
> (`server/apple-login/endpoint-start.sh`) – so kann sich die Sperre wieder lösen.
> (Der Anisette-Dienst liefert gültige Daten; eine nachgestellte GSA-Anfrage
> antwortet mit HTTP 200 und obigem `ec`.)

```bash
# Alternativ klassisch auf der Kommandozeile:
docker compose --profile findmy up -d macless-haystack
docker compose stop macless-haystack
docker compose run --rm macless-haystack    # Apple-ID, Passwort, SMS-2FA
docker compose up -d macless-haystack
```

Auswertung: Web-Frontend <https://dchristl.github.io/macless-haystack/>
(Endpunkt `http://<host>:6176`, `*_devices.json` importieren). Vor dem Exponieren
per `config.ini` (`endpoint_user`/`endpoint_pass`) absichern.

**Wenn Apple die Anmeldung ablehnt** (`ec -80045` / „This action cannot be
completed at this time", teils HTTP 503): Das ist laut
[FAQ des Projekts](https://github.com/dchristl/macless-haystack/blob/main/FAQ.md)
eine Einschränkung des **Apple-Kontos** („account score") – nicht der Einrichtung.
Ein Browser-Login auf `account.apple.com` kann trotzdem klappen. Typische Ursachen
und Abhilfen, in dieser Reihenfolge:

1. **Geräteliste aufräumen:** Jeder Anmeldeversuch legt im Konto ein neues Gerät
   an (`MacBookPro13,2`). Zu viele davon blockieren den Login →
   <https://account.apple.com> → Geräte entfernen, dann erneut versuchen.
2. **Einmal an einem echten Apple-Gerät anmelden** (iPhone/iPad/Mac) – danach gilt
   das Konto als „vertrauenswürdiger" (mehrfach bestätigter Fix in den Issues).
3. **Kontodaten vervollständigen** (Zahlungsmethode/Adresse) – hebt den „score".
4. **Anderes Apple-Konto probieren:** „manche Konten funktionieren, andere nicht,
   warum weiß nur Apple".
5. Alternativ eine passende `auth.json` von einem anderen Rechner/Tool übernehmen –
   liegt sie im Volume, überspringt der Endpunkt die Registrierung.
6. **Anisette-Server prüfen** (nur falls ein fremder Dienst eingetragen ist): Es
   muss ein **v3**-Server sein – ältere v1-Server können Apple-Sperren
   provozieren. Bei uns läuft bereits `dadoum/anisette-v3-server`; ein Wechsel
   ändert am `ec -80045` nichts (siehe Diagnose unten).

**Diagnose bei uns (2026-10-13)** – schließt Konto und Anisette als Ursache aus:

- Browser-Login auf `account.apple.com` **klappt** (mit 2FA); Zahlungsmethode und
  Lieferadresse sind hinterlegt, im Konto steht **ein** Gerät.
- Frisch provisionierte Anisette (eigene Machine-ID) → **derselbe** Fehler.
- HTTP/1.1 und HTTP/2 → **derselbe** Fehler.
- **Erfundenes** Konto mit **gültigem SRP-Wert** → **derselbe** `ec -80045`.

Apple lehnt also den **SRP-Init-Flow selbst** ab (community-weit berichtet als
„any account, any IP, fake credentials too"), bevor das Konto überhaupt bewertet
wird. Von unserer Seite ist nichts einzustellen – es bleibt **warten** oder eine
fertige `auth.json` übernehmen.

### 2d. Verworfene Alternativen (geprüft)

| Projekt | Warum nicht |
|---|---|
| `traccar/apple-find-my-sync` | **Nativer macOS-Service** (Swift) – für Linux/Docker unbrauchbar |
| `nikita-skakun/apple-find-my-sync` | Headless-Linux-Service, aber **AirTag-first** (DIY/OpenHaystack „planned“) + macOS-Bootstrap |
| `hass-FindMy` | Home-Assistant-Integration – wir nutzen Traccar, nicht HA |
| Node.js-Bibliotheken (`findmy.js`) | Kein Traccar-Bezug; Bridge deckt den Fall ab |

## 3. Google: WebUI (empfohlen) oder Minimal-Microservice

Hintergrund: Das Google-Gegenstück basiert auf `GoogleFindMyTools` und existiert in
zwei Ausprägungen – **traccar/google-find-hub-sync** (Traccar-Organisation; Basis
der Minimal-Variante) und die **GoogleFindMyToolsWebUi** (P6g9YHK6), die den offenen
Fix für den Key-Rotations-Bug (leonboe1/GoogleFindMyTools#114) bereits enthält und
zusätzlich Web-UI, Scheduling und Firmware-Build mitbringt.

### 3a. WebUI – empfohlen (Profil `findmy`, nur über Caddy)

> Zugriff über **<https://findmy.localhost>** (hinter dem Login der
> Eltern-UI). Ein direkter Port ist bewusst nicht veröffentlicht.

```bash
cd server
docker compose --profile findmy up -d google-findmy-webui
```

Dann <https://findmy.localhost> → Menüpunkt **„Config"** (diese Seite ist
`/auth`) → Abschnitt **„Google account"** → Knopf **„Sign in with Google"**.
**Es gibt kein Formular zum Eintippen:** Der Knopf startet im Container ein
temporäres Chrome + virtuellen Bildschirm (Xvfb/noVNC, wird beim ersten Mal
nachinstalliert), in dem du dich bei Google anmeldest; direkt danach folgt eine
**zweite** Google-Bestätigung (für die E2EE-Standortberichte). Der erste Start
dauert ~30–90 s, jeder Schritt hat 5 Minuten Zeit – bei Timeout einfach erneut
klicken. Der Status steht als Diagnose auf derselben Seite (`username`,
`aas_token`, `fcm_credentials`, `shared_key`, `owner_key`). Kernfunktionen:

- Geräteliste mit „Locate“/„Play sound“, **Poll-Schedule pro Gerät**
- Ziele mit Presets: **Traccar (OsmAnd)**, Nextcloud PhoneTrack, GpsLogger,
  OwnTracks, uLogger, Locus Map … plus generische HTTP-Ziele mit
  `{{latitude}}`-Platzhaltern → auch unser Bridge-Ingest ist als Ziel nutzbar
  (`POST http://audio-bridge:8085/api/v1/findmy/locations`)
- **ESP32-Tracker aus der UI registrieren** und Firmware im Browser bauen/flashen
  (Web Serial) – passt direkt zu den geplanten Beacon-„Mods“
- Logs + Apprise-Benachrichtigungen (ntfy, Telegram, E-Mail …), Rate-Limiting,
  `/metrics` (Prometheus)

**Weiterleitung an unsere Bridge (der eigentliche Anschluss).** In
**„Forwarding Settings"** bekommt **jedes Gerät** einen Endpunkt auf unseren
Ingest. Am einfachsten:

```bash
bash scripts/setup-google-forwarding.sh   # idempotent, alle Geräte
```

Das Skript setzt pro Gerät einen POST auf
`http://audio-bridge:8085/api/v1/findmy/locations` (Cron `*/15 * * * *`) und
lässt vorhandene Endpunkte unangetastet. Manuell geht es genauso – Gerät →
„+ Add endpoint" → Preset **Custom**:

| Feld | Wert |
|---|---|
| Method | `POST` |
| URL | `http://audio-bridge:8085/api/v1/findmy/locations` |
| Body type | `json` |
| Body | `{"provider": "google", "beacon_id": "{{device_name}}", "lat": {{latitude}}, "lon": {{longitude}}, "accuracy": {{accuracy_m}}, "timestamp": {{google_timestamp}}}` |
| Cron | `*/15 * * * *` |

Danach in der **Eltern-UI: Geräte → „Find-My-Beacons zuordnen"** die Beacons den
Kindern zuordnen – die Einträge heißen `google / <Gerätename>`. **Nur zugeordnete**
Beacons fließen in die fusionierte Position (und damit nach Traccar); nicht
zugeordnete bleiben in der Bridge-Liste, erzeugen aber kein Fremdgerät in Traccar
(`docs/fusion.md`).

Verifiziert (2026-10-13): WebUI → Bridge-Ingest → Fusion → Karte; nach dem
Zuordnen war die Google-Position die Position des Kindes
(`GET /api/v1/parent/fused?device_id=…` → `source: google`).

**Wenn das eingebettete noVNC-Fenster „keine Verbindung" meldet** – zwei Ursachen
sind bekannt und behoben bzw. umschiffbar:

1. **Caddy/`forward_auth` schickt den WebSocket-Upgrade an die Prüf-URL.** Die
   Bridge kennt dort keinen WebSocket und antwortet 403, Caddy gibt das weiter
   (Log: `"WebSocket /api/v1/auth/verify" 403`, caddy#5430). Gelöst über
   `header_up -Connection` in den `forward_auth`-Blöcken (Caddyfile) – das
   betrifft nur die Kopie für die Prüfung.
2. **Chrome bricht mit „Permission denied" ab** (`chrome_crashpad_handler` ohne
   Ausführungsrecht; das Image entpackt „Chrome for Testing" ohne +x). Im Log:
   `FATAL: posix_spawn .../chrome_crashpad_handler: Permission denied (13)` →
   „Browser provisioning failed". Workaround:
   `bash scripts/fix-findmy-browser.sh`, danach erneut „Sign in with Google"
   klicken. (Nach einem Container-Neustart ggf. erneut nötig; Upstream-Fehler.)

Sicherheit: In unserem Stack ist die WebUI **nicht** direkt veröffentlicht
(kein Port) und läuft hinter dem SSO der Eltern-UI – `WEBUI_USER`/`WEBUI_PASSWORD`
bleiben leer. `SECRETS_ENCRYPTION_KEY` verschlüsselt die Google-Tokens at rest.
Nur wer die WebUI bewusst direkt exponiert, setzt dort wieder Zugangsdaten
(optional `HTTPS_ENABLED=1`).
Alle Daten liegen im Volume `google-findmy-data`.

### 3b. Minimal-Microservice (Profil `google-minimal`, Port 5500)

```bash
cd server
docker compose --profile google-minimal up -d google-findmy
```

Erst-Setup (Desktop mit Chrome, einmalig): `git clone
https://github.com/traccar/google-find-hub-sync`, `pip install -r requirements.txt`,
`python main.py` (Login + optional ESP32-Registrierung mit `r`), dann
`docker cp Auth/secrets.json ut-google-findmy:/app/Auth/secrets.json`.
Der Service pusht anschließend per `PUSH_URL` an die Bridge.

**Bekannter Bug:** Rotiert Google die E2EE-Owner-Keys des Kontos, schlägt die
Entschlüsselung fehl (Code fragt immer `owner_key_version=-1` an). Fix ist als
offener PR leonboe1/GoogleFindMyTools#114 vorhanden, aber nicht gemerged →
in diesem Fall auf 3a (WebUI) wechseln.

### 3c. Weitere Anbindungen (nicht in unserem Stack verbaut)

| Option | Ansatz | Wann sinnvoll |
|---|---|---|
| Traccar Relay (Android-App) | Offizielle App verbindet Find Hub mit Traccar | Wenn ein Handy dauerhaft online ist; braucht **Preview-Traccar** + `notificator.traccar.key` |
| Home-Assistant-Integration (BSkando/GoogleFindMy-HA) | Geräte/Standorte als HA-Entitäten | Wenn Home Assistant die Zentrale ist |
| MQTT-Fork (DominicWindisch) | Standorte → MQTT (Home-Assistant-Discovery) | Wenn MQTT im Haushalt läuft |
| go-findmy (dylanmazurek) | Go-Binary, FCM-Echtzeit, MQTT-Publisher | Schlanker eigener Service, Go-Stack |

*Hinweis:* Ein ioBroker-Adapter für Google Find Hub war nicht verifizierbar
(ioBroker-Adapter existieren für Apple-Geräte, z. B. `ioBroker.apple-find-me`).

**Google-Konto-Voraussetzung (alle Wege):** Auf einem Android-Gerät „Find My
Device“ mit „Mit Netzwerk in allen Bereichen“ aktivieren, sonst fehlen die
E2EE-Daten.

## 4. Ingest & Auswertung in der Bridge

**Ein Anlaufpunkt für alle Wege** (`docs/decisions.md` D-019): jedes
Find-My-Gegenstück postet nur noch an die Bridge – die entscheidet, was passiert
(Fusion → optional Traccar). Zwei Protokolle stehen bereit:

- `POST /api/v1/findmy/locations` – **toleranter** JSON-Ingest (Einzelobjekt oder
  Liste). Erkannt werden u. a. `lat/latitude`, `lon/lng/longitude`, `accuracy/acc`,
  `timestamp/time/reported_at`, `id/beacon_id/device_id`, `provider/source`.
  Unbekannte Formate werden inkl. Roh-JSON gespeichert (nichts geht verloren).
- `GET /api/v1/findmy/osmand?id=&lat=&lon=&timestamp=&hdop=&provider=` –
  **OsmAnd-Protokoll** (das sprechen `findmy-bridge` und die Traccar-Presets der
  WebUI). `provider` ist optional, Standard `apple`. Antwort: `{"stored":1,"forwarded":0|1}`.

- Optional Token: `FINDMY_TOKEN` als Header `X-Auth-Token` (leer = offen; dann
  den Port nicht nach außen exponieren).
- **Beacon-Schlüssel:** `(provider, beacon_id)`. Gleichnamige Beacons zweier Netze
  bleiben damit getrennt; Zuordnungen aus früheren Versionen werden migriert.
- Mit gesetztem `TRACCAR_FORWARD_URL` geht die **fusionierte** Position jedes
  Kindes als OsmAnd-Position an Traccar → **ein Gerät je Kind** (nicht je Beacon).
  **ID-Bereinigung:** Traccar akzeptiert in Geräte-IDs keine Bindestriche (HTTP 400);
  beim Forwarding wird die ID deshalb auf `A–Z a–z 0–9 . _` reduziert
  (`BEACON-TEST-1` → `BEACONTEST1`). Die Original-ID bleibt in der Bridge erhalten.
- Eltern-UI zeigt die letzten Positionen; API: `GET /api/v1/parent/findmy/locations`.
- **Quellen-Status:** `GET /api/v1/parent/sources` liefert je Quelle die jüngste
  Position, ihr Alter, Vertrauensstufe und Gültigkeitsfenster – damit ist
  sichtbar, ob ein (experimenteller) Weg überhaupt Daten liefert. In der UI:
  Tab „Geräte" → Karte „Quellen (letzte Position)".
- **Alles auf einmal einrichten:** `bash scripts/setup-findmy.sh` (Google-Weiterleitung
  setzen + Apple-Zustand melden), danach die Beacons in der UI zuordnen.

Test:

```bash
curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"provider":"apple","beacon_id":"BEACON-1","lat":48.1372,"lon":11.5756,"timestamp":1770000000}' \
  http://localhost:8085/api/v1/findmy/locations
```

## 4b. Testen ohne echtes Konto (Account-„Dummies")

**Kurz: es gibt keine.** Für beide Wege existiert **kein Sandbox-/Testkonto** ✗:

| Frage | Antwort |
|---|---|
| Apple-Testkonto? | **Nein.** Der Weg authentifiziert gegen `gsa.apple.com` – dieselbe Schnittstelle wie echte Geräte. Apples „Sandbox-Apple-IDs" gelten nur für In-App-Käufe, nicht für Find My. |
| Google-Testkonto? | **Nein.** Die E2EE-Schlüssel kommen aus dem echten Konto; die Community-Reimplementierung hat keinen Testmodus. |
| Was geht stattdessen? | **Zweitkonten** – genau dafür gedacht: frisches Apple-Konto (SMS-2FA) bzw. zweites Google-Konto. |

**Praktische Erfahrungen aus der Community** (macless-haystack FAQ/Issues):

- Ein **frisches, „leeres" Apple-Konto** genügt in vielen Fällen ✓ – es muss
  nicht das Hauptkonto sein ✓ (empfohlen wird ausdrücklich ein Zweitkonto ✓).
- Stolperstein: **„account score is not high enough"** ✗ – ganz neue Konten
  brauchen manchmal eine Zahlungsmethode (es wird nichts abgebucht) oder ein
  echtes Apple-Gerät ✓.
- Bei **zu vielen Geräten** im Konto schlägt der Login fehl ✗ – alte
  Login-Geräte im Apple-Konto entfernen ✓.
- **Abkürzung:** Wer bereits ein `auth.json` hat (z. B. aus FindMy.py oder
  Biemster), kann es **direkt ins Volume legen** ✓
  (`macless-data:/app/endpoint/data/auth.json`) – dann entfällt die Anmeldung
  komplett ✓ (das Image überspringt die Registrierung ✓).

**Ohne jedes Konto testbar** (nutzen wir in der CI ✓): der Ingest-Pfad
(`POST /api/v1/findmy/locations` mit synthetischen Beacons ✓), die komplette
Sensor-Fusion (Unit-Tests ✓), die Beacon-Zuordnung und die Karte ✓ sowie der
Tracker-Simulator (`scripts/simulate-tracker.py` ✓) für den Gerätepfad ✓.

## 5. Noch nicht implementiert

- Automatischer Abruf der Apple-Berichte aus macless-haystack (API nicht
  dokumentiert) – derzeit manuell/per Skript einspeisen.
- Beacon-Verwaltung in der UI (Keys, Provider-Zuordnung) – aktuell über die
  jeweiligen Fremd-Tools.

## 6. Rechtliches

Beacons in Fremdnetzen sind für Dritte als „unbekannter Tracker“ sichtbar
(Anti-Stalking-Warnungen). Für das eigene Kind vertretbar, aber bewusst
entscheiden. Keine offiziellen APIs → Nutzung auf eigenes Risiko.

## 7. Quellen

- macless-haystack (Keys + UI) – <https://github.com/dchristl/macless-haystack>
- OpenHaystack – <https://github.com/seemoo-lab/openhaystack>
- Apple-Filterproblem – <https://github.com/seemoo-lab/openhaystack/issues/273>
- Apple→Traccar-Bridge (empfohlen) – <https://github.com/jannisko/findmy-traccar-bridge>
- findmy.py (Bibliothek) – <https://github.com/malmeloo/FindMy.py>
- traccar/apple-find-my-sync (macOS-only) – <https://github.com/traccar/apple-find-my-sync>
- nikita-skakun/apple-find-my-sync (AirTag-first) – <https://github.com/nikita-skakun/apple-find-my-sync>
- Traccar-Fork (Google, Minimal-Variante) – <https://github.com/traccar/google-find-hub-sync>
- GoogleFindMyToolsWebUi (empfohlen) – <https://github.com/P6g9YHK6/GoogleFindMyToolsWebUi>
- GoogleFindMyTools (Original) – <https://github.com/leonboe1/GoogleFindMyTools>
- Key-Rotations-Fix (offener PR) – <https://github.com/leonboe1/GoogleFindMyTools/pull/114>
- Traccar Relay (Android) – <https://www.traccar.org/relay/>
- MQTT-Fork – <https://github.com/DominicWindisch/googlefindmytools-homeassistant>
- go-findmy – <https://github.com/dylanmazurek/go-findmy>
