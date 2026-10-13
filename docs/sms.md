# Identitäten & SMS-Pfad

Wie Tracker, SIM und Beacons eindeutig adressiert werden – und was SMS leisten
kann (und was nicht). **Stand 2026-10-12 korrigiert:** Die frühere Annahme
„Gerät ↔ Eltern direkt per SMS" ist mit 1NCE **nicht** möglich.

## 0. Wofür sind dann die 250 inklusiven SMS gut?

Die 250 SMS der 1NCE IoT Lifetime Flat sind **kein** Handy-Messaging, sondern
Kommunikation **zwischen dem Gerät und der 1NCE-Plattform**:

| Richtung | Was passiert | Nutzen für uns |
|---|---|---|
| **MO** (Gerät → Plattform) | Gerät sendet per `AT+CMGS`; die SMS landet im 1NCE-Konto (Portal/API) | Notfall-/Alarmmeldung („SOS", „Akku leer"), funktioniert auch **ohne Datensitzung** |
| **MT** (Plattform → Gerät) | Der Kunde sendet über die **1NCE-API** (`POST /v2/sims/{iccid}/sms`); Zustellung beim nächsten Attach | Weckruf („poll jetzt"), Suchmodus-Beschleunigung |

1NCE beschreibt den Zweck selbst als „fall-back or wake-up calls". Der Vorteil
gegenüber HTTP: Der Weg funktioniert, wenn die Datensitzung nicht steht, und er
weckt das Gerät **zwischen** seinen regulären Poll-Intervallen (Zustellung ist
allerdings bis zu 24 h gepuffert – also ein *queued* Weckruf, keine Sofortaktion).

**Nicht** möglich (1NCE-Regeln): Handy → Gerät (P2P-MT-SMS) und SMS über NB-IoT.

## 0b. Umsetzungsstand der 1NCE-API (2026-10-12)

| Baustein | Status |
|---|---|
| OAuth2-Token (`POST /oauth/token`, Basic-Auth mit Client-ID/Secret) | ✅ implementiert, **mit echtem Konto getestet** |
| `GET /api/v1/parent/sms/status` → SIMs + SMS-Kontingent | ✅ (Konto erreichbar; Zuordnung im 1NCE-Portal) |
| `POST /api/v1/parent/sms` → MT-SMS an eine SIM (`{iccid, text}`) | ✅ implementiert (noch kein Versand getestet – SIM fehlt) |
| `GET /api/v1/parent/sms?iccid=…` → MT-/MO-Verlauf | ✅ implementiert |
| UI-Karte „SMS (1NCE)" (Status + Senden) | ✅ |
| Zuordnung SIM ↔ Gerät (`iccid` in der Geräte-Registry) | ✅ Spalte + API |
| Zugangsdaten | `1NCE_API_CLIENTID`/`1NCE_API_CLIENTSECRET` in `server/.env` (nicht im Repo!) |

Quelle der API-Details: `docs/1NCE/authorization-v2.yaml` und
`docs/1NCE/sim-management-v2.json` (OpenAPI-Spezifikationen).

## 1. Wer ist wer: IMEI, MSISDN, Beacon-IDs

| Identität | Quelle | Verwendung |
|---|---|---|
| **IMEI** (SIM7080G) | Modem, per `AT+GSN` | **Primär-ID** des Trackers: Traccar-OsmAnd (`id=…`) und Bridge (`device_id`) |
| **MSISDN** (1NCE-Rufnummer) | SIM-Vertrag / 1NCE-Portal | SMS-Adresse (siehe Abschnitt 2 – nur gegen die 1NCE-Plattform) |
| **Beacon-ID** (Apple/Google) | Key-Generierung, `docs/findmy.md` | eigenes „Gerät" in Traccar/Bridge für Find-My-Positionen |
| Gerätename | Eltern-UI | Anzeige |

Die Bridge führt eine **Geräte-Registry** (`devices`-Tabelle):
`id` (= IMEI), `name`, `imei`, `msisdn`, `notes`.
Unbekannte Geräte werden beim ersten Kontakt automatisch angelegt (analog
Traccar `database.registerUnknown`) und können in der UI ergänzt werden.

API (Parent-Token): `GET /api/v1/parent/devices`,
`PUT /api/v1/parent/devices/{id}`, `DELETE /api/v1/parent/devices/{id}`.

## 2. SMS mit 1NCE – was das Netz erlaubt (und was nicht)

Quelle: 1NCE Developer Hub (SMS Services – Features & Limitations).

| Pfad | Möglich? | Anmerkung |
|---|---|---|
| Gerät → 1NCE-Plattform (MO-SMS) | ✅ | „Any device with a 1NCE SIM can send MO-SMS messages." Empfang über Portal/API. |
| Server → Gerät (MT-SMS, A2P) | ✅ | Nur über die **1NCE-API/Portal**, mit Auth-Token. Bis zu 24 h pending, wird beim nächsten Attach zugestellt. |
| **Handy → Gerät (P2P-MT-SMS)** | ❌ | „it is not possible to send a message to a device with a 1NCE SIM using a mobile phone" |
| Gerät → Handy | ❌ | 1NCE liefert MO-SMS nur an die Plattform; Weiterleitung per „SMS forwarding" an einen eigenen Server. |
| SMS über **NB-IoT** | ❌ | „SMS is not possible with NB-IoT" → **LTE-M (Cat-M1) erzwingen** (`AT+CNMP=38`, `AT+CMNB=1`). |
| Kontingent | 250 SMS | In der 1NCE IoT Lifetime Flat enthalten. |

**Fazit für die Architektur:** Es gibt **keinen direkten Gerät-↔-Eltern-SMS-Weg**.
SMS ist nur *serververmittelt* nutzbar (1NCE-API in der Bridge) – und selbst dann
nur als **queued Weckruf** (Zustellung beim nächsten Netz-Attach), nicht als
sofortige Aktion. Der Primärpfad bleibt deshalb **HTTP-Polling** (D-003).

## 3. Ist das ein Hardware-Problem des SIM7080G?

**Nein.** Das Modul unterstützt SMS:

- Der SIMCom-AT-Befehlssatz der SIM7070/7080/7090-Serie enthält das komplette
  3GPP-TS-27.005-SMS-Kapitel (`AT+CMGF`, `AT+CMGS`, `AT+CMGL`, `AT+CNMI`, `AT+CPMS`, `AT+CSMS`, …).
- TinyGSM implementiert eine SMS-Klasse für den SIM7080.
- Community-Berichte (M5Stack U137, gleicher Modemtyp): Senden **und** Empfangen funktioniert.

LilyGOs pauschales `#error "This modem not sms function"` in ihren Beispielen ist
eine **Absicherung ihrer Beispiel-Sketches** (die für die A76xx/SIM7670-Familie
geschrieben sind; dort gilt teils „kein SMS/Voice"), **keine Hardware-Aussage**.
Wahrscheinlichster Grund für die Pauschale: nie mit einem SMS-fähigen Netz getestet.

**Verifikation läuft über M4:** Die Bring-up-Firmware prüft jetzt die
SMS-Fähigkeit (`c`) und kann eine Test-SMS senden (`x`) – siehe `docs/bring-up.md`.

**Stand 2026-10-12 (ohne SIM):** Alle SMS-AT-Befehle liefern auf diesem Board
**ERROR** (`+CMGF`, `+CSCS`, `+CPMS?`, `+CSMS?`, `+CMGS=?`, `+CSCA?`, `+CNMI`, `+CMGL`) –
ohne SIM erwartbar (der SMS-Dienst braucht die SIM-Speicher), also **kein Beweis**
für oder gegen SMS. Modul-Firmware hier: `ATI → R1951.07`,
`AT+CGMR → Revision:1951B17SIM7080`. Endgültige Klärung mit SIM per `c`/`x`.

## 4. SMS-Kommandos – Neubewertung

Die frühere Spezifikation (`UT <PIN> FIND/LOC/…` per SMS von den Eltern) ist mit
1NCE **nicht umsetzbar** (kein P2P-MT-SMS). Falls SMS doch genutzt werden soll,
dann serververmittelt:

| Richtung | Weg | Nutzen |
|---|---|---|
| Server → Gerät | 1NCE-API (`POST` MT-SMS), Gerät liest per `AT+CMGL` beim Attach | Weckruf/Suchmodus, wenn Polling zu langsam wäre |
| Gerät → Server | `AT+CMGS` an die 1NCE-Plattform, Server holt per API ab | Notfall-Alarm (z. B. „Akku leer", „SOS") |

Sicherheit: Der Server-Token der 1NCE-API gehört in `server/.env` (nie ins Repo);
Kommandos vom Gerät werden über die Absendernummer/das Gerätekonto zugeordnet.

## 5. Offene Punkte

1. **M4 (Bring-up `c`/`x`):** SMS-Fähigkeit mit der echten 1NCE-SIM testen –
   `AT+CMGF`, `AT+CMGS=?`, `AT+CPMS?`, Senden an eine Nummer, Empfang per `AT+CMGL`.
2. `AT+CPSMS?`/`AT+CEDRXS?` lieferten ohne SIM **ERROR** (siehe `docs/bring-up.md`) –
   mit SIM erneut prüfen; relevant für die B1-Entscheidung.
3. Entscheidung: Wollen wir die **1NCE-API** überhaupt integrieren (SMS-Weckruf),
   oder bleibt es beim reinen HTTP-Polling? (Kosten: API-Client in der Bridge,
   Token-Verwaltung.)
