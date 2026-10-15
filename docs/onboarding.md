# Onboarding: vom Auspacken bis „Kind ist auf der Karte"

Maßstab ist ein **DAU**: jemand ohne Terminal, ohne `.env`, ohne Wissen über
Traccar, Caddy oder SIM-Anbieter. Der Setup-Assistent deckt heute nur die
**Server-Seite** ab; die **Geräte-Seite** (Firmware, Provisioning, SIM) ist noch
reine Handarbeit. Dieses Dokument hält den vollständigen Weg, die Stolpersteine
und den Umsetzungsvorschlag fest.

> **Stand:** Bestandsaufnahme 2026-10-14. Ergänzt `docs/parent-usability.md`
> (das nur die Server-/UI-Schicht betrachtet).

## 1. Zugangsmodell: zwei getrennte Wege

| Wer | Weg | Warum |
|---|---|---|
| **Eltern** | Tailscale (privat) bzw. LAN | kein offener Port, keine DynDNS-Pflege |
| **Tracker** | LTE → **öffentlich** | ein ESP32-S3 kann kein Tailscale; er braucht eine erreichbare URL (`server_url`, `config_store.h`) |

Wichtig: Tailscale löst **nur** die Eltern-Seite. Der Tracker hängt im
Mobilfunknetz und braucht einen öffentlichen Ingress – heute DynDNS + Ports
(`docs/deployment.md` §10.2), später Let's Encrypt.

Entschieden (2026-10-14): Eltern-Zugang **Option B** (Tailscale-Name + interne
CA), Option A (echtes Zertifikat) später; Tracker-Ingress bleibt bei
DynDNS + Ports, weil noch lokal entwickelt wird.

## 2. Die zwei Stolpersteine (und ihr Stand)

### 2a. Die Tailscale-URL war funktionslos

`https://100.124.33.92/` lieferte **HTTP 200 mit leerem Body**. Grund: Caddy
wählt die Site über den **Host-Header**; die Tailscale-Adresse stand in keiner
Site (Kontrolltest: beliebiger Fremd-Host → ebenfalls „200 + leer"). Zusätzlich
senden Browser bei **IP-Adressen kein SNI**, deshalb greift `default_sni` – das
Zertifikat muss die IP also mit abdecken.

→ **behoben:** `SITE_AUDIO` ist der MagicDNS-Name (der Einstieg), die
Tailscale-IP steht in `SITE_LAN_ALIASES` (siehe `docs/operations-manucloud.md`
§4b). Empfohlen ist der **Name** – nur er liefert ein passendes Zertifikat.

### 2b. `*.localhost` gibt es nur auf dem Server

Die „ein Login für alle Dienste"-Mechanik hing an den Hostnamen
`audio.`/`traccar.`/`findmy.`/`apple.localhost`. Auf dem Handy oder über
Tailscale lösen die **nicht** auf – die Dienste-Links waren dort tot.

→ **behoben über Muster (b):** Alle Dienste laufen unter **einem** Namen auf
eigenen Ports (Ein-Host-Muster, `docs/deployment.md` §10.2): Einstieg auf 443,
Traccar auf **8443**, Google auf **8444**, Apple auf **8445**. Das Sitzungscookie
ist host-only und gilt über Ports hinweg – das SSO funktioniert also weiter.

- **(a) echte Domains/Subdomains** bleibt die Option für später (Internet-Betrieb
  mit Let's Encrypt) – dann bekommt jeder Dienst wieder einen eigenen Namen.
- **Hinweis:** Die Ports sind über Docker veröffentlicht und gehen an UFW vorbei
  (`docs/operations-manucloud.md` §4b). Wer sie begrenzen will, braucht
  `ufw-docker`.

### 2c. Zertifikat war nur nach dem Login erreichbar

Der CA-Download hing im Tab „Betrieb" bzw. im Assistenten – **beide erst nach
dem Login** (Henne-Ei). Außerdem leitete `http://<host>/ca.crt` auf HTTPS um,
also genau in die Warnung.

→ **behoben:** Ein Block „Zertifikat einrichten" steht direkt auf der
**Anmeldeseite**, und Caddy liefert `/ca.crt` auf **Port 80** ohne
HTTPS-Umleitung aus (`http://<host>/ca.crt`) – inklusive Kurzanleitung für
Android/iPhone/Windows.

## 3. Der Soll-Weg (drei Phasen)

**Phase 0 – Maschine (Betreiber, einmalig):** Docker, `server/.env`,
`--profile tls`, Firewall, Backups – steht in `docs/operations-manucloud.md`.

**Phase 1 – Eltern (einmalig):** Zugang herstellen (Tailscale-App, Gerät ins
Tailnet, `caddy-root.crt` importieren), UI öffnen, Konto anlegen/anmelden.

**Phase 2 – Server-Seite pro Tracker:** Setup-Assistent (Tracker anlegen, SIM,
Karte, Benachrichtigungen, Zertifikat, Funktionstest).

**Phase 3 – Gerät pro Tracker** (die fehlende Hälfte): Firmware flashen, SIM
einlegen, **provisionieren** (Token + Server-URL + IMEI), Funktionstest.

## 4. Was der Assistent heute prüft – und was fehlt

| Schritt | geprüft | Lücke |
|---|---|---|
| Willkommen | – | – |
| Tracker anlegen | Gerät in Registry | IMEI abtippen (A7) – schon gemeldete Tracker lassen sich inzwischen **übernehmen** (§5) |
| SIM | ICCID gesetzt | 1NCE-Aktivierung ist **extern** (Portal) |
| Karte prüfen | Traccar erreichbar | – |
| Benachrichtigungen | Web-Push abonniert | braucht HTTPS/PWA, kein Fallback (F1) |
| Zertifikat | CA-Datei vorhanden | Import pro Gerät ist Handarbeit |
| Apple Find My | Apple-ID hinterlegt | 2FA per SMS, experimentell |
| Funktionstest | Position/Nachricht/Beacon | setzt ein **fertiges Gerät** voraus |
| Fertig | – | – |

**Die Geräte-Seite ist gar nicht geführt:** Flashen (PlatformIO + USB),
Provisioning (`{"cmd":"provision",…}` per USB-Serial), SIM-Einlage. Genau das
muss ein Elternteil beim zweiten Tracker erneut machen – „Anlegen ist nur die
halbe Miete".

## 5. „Tracker in Betrieb nehmen" – Stand & Plan

**Umgesetzt (2026-10-14):**
- **Nummern & Texte im Assistenten:** Schritt-Nummern folgen jetzt der
  Ablaufreihenfolge (1–7, vorher sprangen sie 4 → 6 → 7 → 5); der
  Willkommen-Schritt nennt den Flashen-/Provisioning-Schritt ehrlich.
- **SIM-Schritt** verlinkt das Anbieter-Portal (1NCE) und benennt die
  Aktivierung als Pflicht.
- **„Bereits gemeldet – hier übernehmen"** (Befund A7): Hat sich ein Tracker schon
  gemeldet, bietet der Tracker-Schritt ihn als Auswahl an – die IMEI muss **nicht
  abgetippt** werden, nur noch ein Name vergeben.
- **Provisioning-Zeile in der UI:** Der Tracker-Schritt baut live die fertige
  JSON-Zeile `{"cmd":"provision","device_id":…,"server":…,"token":…}` zum
  Kopieren in den Serial-Monitor – mit editierbarem Server-Feld. Die vorgeschlagene
  Adresse kommt aus `TRACKER_SERVER_URL` (neu in `server/.env`), sonst aus
  `SITE_AUDIO`/`SITE_LAN`; sie muss **aus dem Mobilfunknetz** erreichbar sein.

**Offen – die Geräte-Seite (Firmware):** Flashen (PlatformIO + USB) und
Provisioning (`{"cmd":"provision",…}`) sind heute Handarbeit. **Der Knackpunkt
ist ein Compile-Flag:** Provisioning läuft nur mit `UT_DEBUG_SERIAL`; der
Release-Build hat bewusst **kein** USB-CDC (`ARDUINO_USB_CDC_ON_BOOT=1` → Board
startet am Akku nicht). Optionen für einen geführten Weg:

| # | Weg | Aufwand / Haken |
|---|---|---|
| 1 | **WebSerial im Browser** (Desktop-Chrome/Edge): die UI schreibt die JSON-Zeile direkt aufs Gerät | kein Terminal/Toolchain; braucht USB-CDC ⇒ nur mit Dev-/Provisioning-Build. Ablauf: Provisioning-Build → im Browser provisionieren → Release flashen (NVS bleibt) |
| 2 | **Provisioning-Fenster im Release-Build** | am elegantesten, aber `ARDUINO_USB_CDC_ON_BOOT` ist ein Compile-Flag → eigenes Env oder Trick nötig (Akku-Start!) |
| 3 | **WLAN-Provisioning (SoftAP)**: Board spannt ohne Config ein Netz auf, die UI zeigt einen QR-Code | kein Kabel, kein Desktop – dafür mehr Firmware-Arbeit |
| 4 | **Vorprovisioniert ausliefern** (URL+Token ab Werk), Elternteil benennt nur noch | passt zum Prototyp; die „Übernehmen"-Abkürzung oben deckt das schon ab |

**Empfehlung:** Für den Prototyp reicht heute „Dev-Build → provisionieren →
Release-Build"; die **Provisioning-Zeile zeigt die UI jetzt fertig zum Kopieren**
(Server-Feld editierbar, `TRACKER_SERVER_URL` in `server/.env`). Für den echten
DAU (Elternteil, kein Desktop) später Weg 3.

Weitere offene Punkte:
- **Benachrichtigungen** ohne HTTPS/localhost haben keinen Fallback (F1).
- **Zertifikat-Import** pro Gerät bleibt Handarbeit (entfällt mit Let's Encrypt).
- **Diagnose in Klartext:** „Warum meldet mein Tracker nicht?" als Ampel – die
  Gesundheitsanzeige je Kind gibt es schon (D1/D2).

## 6. Offene Entscheidungen

- **Mehr-Dienst-Zugang:** Muster **(b)** ist umgesetzt (Ports 8443–8445);
  Wechsel auf **(a)** echte Domains/Subdomains steht für den Internet-Betrieb an.
- **Tailscale-Name final:** `manucloud.tail0c6f95.ts.net` oder stabiler Alias?
- **Ingress für den Tracker final:** DynDNS heute; Funnel/Cloudflare später?

## 7. Ports & Härtung – Strategie (festgehalten 2026-10-14)

**Problem:** Docker veröffentlicht Ports **an UFW vorbei** (`DOCKER-USER` leer,
kein `ufw-docker`) – die UFW-Regeln „von LAN" greifen für Container-Ports nicht.
Docker schreibt seine DNAT-Regeln in die eigene Kette und läuft vor UFWs Filter.

**Entscheidung: zweistufig, `ufw-docker` erst zum Produktivgang.**

**Stufe 1 – jetzt (Entwicklung):** Nichts umbauen. Der Host hängt hinter NAT; das
reale Risiko ist klein. Die einzige Maßnahme, die zählt: am Router **wirklich nur
80/443** weiterleiten (kein 8085/8082/8086/9443/8443…). Dann ist „Docker geht an
UFW vorbei" praktisch folgenlos.

**Stufe 2 – vor Produktion: „nur Caddy exponiert".**
- Caddy veröffentlicht 80/443 (mit echten Domains später nur noch 443); alles
  andere – Bridge 8085, Traccar 8082/5055, Portainer, Dozzle, Beszel, ntfy –
  wird **nicht** veröffentlicht bzw. auf `127.0.0.1` gebunden.
- Der **Tracker-Upload** läuft über einen Caddy-Hostnamen (z. B.
  `ingest.<domain>` → `traccar:5055`) statt über einen offenen Port.
- **Admin-Werkzeuge** von unterwegs über **Tailscale**; dafür `ufw-docker` mit
  Freigabe für `100.64.0.0/10` (und LAN) einführen.

**Bewusst nicht jetzt:** `ufw-docker` kostet während der Entwicklung nur Pflege
(Freigaben mitpflegen). Auch das Binden an die Tailscale-IP ist fragil – startet
Docker vor `tailscale0`, schlägt das Binden fehl.

**Warum der spätere URL-/IP-Wechsel harmlos ist:** `SITE_*` liegen in
`server/.env` (Konfiguration, kein Code); mit echten Domains entfällt der
CA-Import und die Ports 8443–8445 fallen wieder weg. Daten (Postgres, Volumes)
bleiben unberührt. Einmal neu nötig sind nur PWA-Installationen, Web-Push-Abos
und Sitzungen (Origin-gebunden). **Einziger „eingebrannter" Wert ist
`server_url` im Tracker-NVS** – da die Firmware erst zum Betrieb geflasht wird,
wird dort gleich die endgültige Adresse provisioniert.
