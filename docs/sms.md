# Identitäten & SMS-Pfad

Wie Tracker, SIM und Beacons eindeutig adressiert werden – und was SMS leisten
kann (und was nicht).

## 1. Wer ist wer: IMEI, MSISDN, Beacon-IDs

| Identität | Quelle | Verwendung |
|---|---|---|
| **IMEI** (SIM7080G) | Modem, per `AT+GSN` | **Primär-ID** des Trackers: Traccar-OsmAnd (`id=…`) und Bridge (`device_id`) |
| **MSISDN** (1NCE-Rufnummer) | SIM-Vertrag / 1NCE-Portal | SMS-Adresse (Gerät ↔ Eltern; später ggf. Server → Gerät) |
| **Beacon-ID** (Apple/Google) | Key-Generierung, `docs/findmy.md` | eigenes „Gerät“ in Traccar/Bridge für Find-My-Positionen |
| Gerätename | Eltern-UI | Anzeige |

Die Bridge führt eine **Geräte-Registry** (`devices`-Tabelle):
`id` (= IMEI), `name`, `imei`, `msisdn`, `notes`.
Unbekannte Geräte werden beim ersten Kontakt automatisch angelegt (analog
Traccar `database.registerUnknown`) und können in der UI ergänzt werden.

API (Parent-Token): `GET /api/v1/parent/devices`,
`PUT /api/v1/parent/devices/{id}`, `DELETE /api/v1/parent/devices/{id}`.

## 2. SMS-Pfade – Bestandsaufnahme

| Pfad | Weg | Status |
|---|---|---|
| Gerät → Eltern | Tracker sendet SMS direkt an die Elternnummer (Modem) | **optional**, erst nach M4 (SMS-Support am SIM7080G unbestätigt) |
| Eltern → Gerät | SMS an die MSISDN; Gerät liest sie beim nächsten Wake | **optional**, Latenz Minuten–Stunden (PSM!) |
| Server → Gerät | Server braucht SMS-Gateway (Provider-API oder lokales GSM-/LTE-Modem) | **nicht implementiert**, nicht nötig solange Polling funktioniert |
| Gerät → Server | SMS an Empfangsnummer + Gateway, das in die Bridge einspeist | **nicht implementiert** |

**Fazit:** Alle Funktionen laufen heute über **HTTP-Polling** (Datenpfad,
Entscheidung D-003). SMS ist ein Zusatzpfad für Notfall/Komfort und hängt an
Messung **M4**. Wenn SMS genutzt wird, dann am einfachsten **Gerät ↔ Eltern
direkt** (ohne Serverbeteiligung).

## 3. SMS-Kommandos (Spezifikation für den Fall der Aktivierung)

Format: `UT <PIN> <Befehl> [Argument]`, Beispiel: `UT 4711 FIND`.
Nur Nummern aus einer Whitelist (in der Firmware hinterlegt) werden akzeptiert;
Antworten gehen an die Absendernummer.

| Befehl | Wirkung | Antwort |
|---|---|---|
| `FIND` | Suchalarm (Piezo-Intervallton) für N Minuten | `OK FIND <min>` |
| `STOP` | Suchalarm beenden | `OK STOP` |
| `LOC` | einmalige Positionsmeldung per SMS | `LOC <lat>,<lon>,<hdop>,<batt>` |
| `BATT` | Akkustand | `BATT <prozent>` |
| `INFO` | Status (Netz, letzter Fix, Firmware) | `INFO …` |

Sicherheit & Kosten: PIN verpflichtend; unbekannte Nummern ignorieren und loggen;
Rate-Limit (z. B. max. 10 SMS/Stunde) gegen Missbrauch und Kosten.

## 4. Offene Punkte

1. **M4**: SMS senden/empfangen am SIM7080G prüfen (`docs/measurement-plan.md`).
2. RI-Wake (GPIO 3) testen: weckt eine eingehende SMS den ESP32? Nur mit
   registriertem Modem (nicht im PSM) – kostet Ruhestrom.
3. Falls Server-seitige SMS gewünscht: Gateway wählen (lokales LTE-Modem am
   Server oder Provider-API) und in der Bridge als Adapter ergänzen
   (`SMS_PROVIDER`-Konfiguration).
