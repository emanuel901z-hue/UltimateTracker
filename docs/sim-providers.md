# SIM-/SMS-Provider: anbieterneutrale Anbindung

Die Bridge spricht **nicht** direkt mit einem SIM-Anbieter, sondern über eine
Provider-Schicht (`server/audio-bridge/app/providers/`). Anbieterwechsel und
API-Versionssprünge sind damit Konfigurationsfragen – UI, Endpunkte und
Geräte-Registry bleiben unverändert.

## 1. Aufbau

```
app/providers/
├── base.py         SimProvider (Schnittstelle) + SimInfo/SmsMessage
├── nce.py          1NCE – REST, OAuth2 (Management API v2)
├── whereversim.py  wherever SIM – GraphQL/AppSync + WebSocket-Subscriptions
├── generic.py      konfigurationsgetriebener Provider (Template für alle anderen)
└── __init__.py     Registry: get_provider() liest SIM_PROVIDER
```

Schnittstelle (`base.SimProvider`):

| Methode | Zweck | Pflicht |
|---|---|---|
| `configured()` | sind die Zugangsdaten vorhanden? | ✅ |
| `list_sims()` | SIMs des Kontos (ICCID, MSISDN, Status, Kontingent, interne ID) | ✅ |
| `sms_quota(iccid)` | SMS-Kontingent einer SIM | ✅ (darf `None`) |
| `send_sms(iccid, text)` | MT-SMS senden | ✅ |
| `list_sms(iccid, limit)` | MT-/MO-Verlauf | ✅ |
| `network_location(iccid)` | netzbasierte Position | optional |
| `supports_watch()` / `watch_sms(iccid, callback)` | Echtzeit-SMS (Push) | optional |

API-Endpunkte der Bridge (unverändert, liefern `provider` mit):
`GET /api/v1/parent/sms/status`, `POST /api/v1/parent/sms`,
`GET /api/v1/parent/sms?iccid=…`, `GET /api/v1/parent/sim/messages`
(per Echtzeit empfangene SMS).

## 2. Anbieter wählen

```env
SIM_PROVIDER=nce          # 1NCE (Standard, nutzt 1NCE_API_CLIENTID/SECRET)
SIM_PROVIDER=whereversim  # wherever SIM (GraphQL, Token-Header)
SIM_PROVIDER=generic      # beliebiger Anbieter per JSON (siehe unten)
SIM_PROVIDER=none         # SMS-Funktionen aus
SMS_SUBSCRIBE=1           # Echtzeit-SMS abonnieren (falls der Anbieter das kann)
```

Ohne `SIM_PROVIDER` wird `nce` genommen, sobald 1NCE-Zugangsdaten gesetzt sind.

## 3. Neuen Anbieter per Konfiguration anbinden

1. `server/sim-providers/mein-anbieter.json` anlegen (Vorlagen liegen dort:
   `example-1nce-generic.json`, `example-whereversim-generic.json`,
   `example-emnify-generic.json`, `example-onomondo-generic.json`,
   `example-twilio-supersim-generic.json`).
2. Zugangsdaten als `${…}`-Platzhalter eintragen, Werte in `server/.env` setzen.
3. In `.env`: `SIM_PROVIDER=generic` und
   `SIM_PROVIDER_CONFIG=/etc/ut/providers/mein-anbieter.json`
   (`server/sim-providers/` ist in den Container gemountet).
4. `docker compose up -d --build audio-bridge`, dann
   `GET /api/v1/parent/sms/status` prüfen.

### Schema

```jsonc
{
  "name": "mein-anbieter",
  "base_url": "https://api.example.com/v3",
  "auth": {
    "type": "basic | bearer | header | oauth2 | none",
    "username": "…", "password": "…",                // basic
    "token": "…",                                     // bearer
    "header_name": "X-API-Key", "header_value": "…",  // header
    "token_url": "…", "client_id": "…", "client_secret": "…",
    "grant_type": "client_credentials", "basic_auth": true,
    "token_field": "access_token",
    "token_body": {"application_token": "${MEIN_TOKEN}"}   // eigener Body (z. B. EMnify)
  },
  "endpoints": {
    "list_sims": {"method": "GET",  "path": "/sims", "items": "$"},
    "send_sms":  {"method": "POST", "path": "/sims/{provider_id}/sms",
                  "encoding": "json | form",              // form z. B. für Twilio
                  "body": {"payload": "{text}", "source_address": "{source}"},
                  "expect": {"path": "data.sendSms", "equals": true}},
    "list_sms":  {"method": "GET",  "path": "/sims/{provider_id}/sms", "items": "data.items"},
    "sms_quota": {"method": "GET",  "path": "/sims/{iccid}/quota/sms"}
  },
  "fields": {
    "sim":  {"iccid": "iccid", "msisdn": "msisdn", "status": "status", "label": "label",
             "quota_sms": "current_quota_SMS", "provider_id": "id"},
    "sms":  {"id": "id", "text": "payload", "direction": "type", "state": "status",
             "source": "source_address", "submitted": "submit_date"},
    "quota": {"remaining": "volume", "total": "total_volume"}
  },
  "maps": {"direction": {"1": "MT", "2": "MO"}, "state": {"4": "DELIVERED", "5": "FAILED"}}
}
```

- **`items`**: Pfad zur Liste (`$` = Wurzel, `data.listSims.items` = verschachtelt).
- **`fields`**: Pfade ins Objekt (`a.b.c`); fehlende Felder bleiben leer.
- **`provider_id`**: viele APIs adressieren SIMs **nicht** über die ICCID
  (Twilio SID, Onomondo sim_id, EMnify endpoint_id). Ist das Feld gesetzt, löst
  die Bridge die ICCID automatisch in die interne ID auf – nutzbar als
  `{provider_id}` in Pfad/Body.
- **`expect`**: Erfolgsprüfung im Body für APIs, die keinen Fehlerstatus, sondern
  einen Wert liefern (GraphQL-Boolean).
- **Platzhalter**: `{iccid}`, `{provider_id}`, `{text}`, `{source}`;
  `${VAR}` / `${VAR:-default}` aus der Umgebung (Secrets bleiben in der `.env`).
- **Version**: steckt die Version im Pfad, gehört sie in `base_url`/`path`.
  Beim 1NCE-Provider zusätzlich über `NCE_API_VERSION` umstellbar (Default `v2`).

## 4. Anbieter-Landschaft (Stand 2026-10)

| Anbieter | Stil | Auth | Abdeckung |
|---|---|---|---|
| **1NCE** | REST v2 | OAuth2 `client_credentials` | ✅ eigene Klasse, **live getestet** |
| **wherever SIM** (Link+) | **GraphQL/AppSync** | Token-Header | ✅ eigene Klasse (GraphQL + **WebSocket-Subscriptions** + netzbasierte Position) |
| **EMnify** | REST v1 | Token per eigenem Body (`application_token`) | 🟡 Template (`example-emnify-generic.json`) – Feldnamen prüfen |
| **Onomondo** | REST | `Authorization: Bearer <Key>` | 🟡 Template – SIMs per interner `sim_id`; SMS-Inhalte primär per Webhook |
| **Twilio Super SIM** | REST | Basic (SID/Token) | 🟡 Template – SIMs per `sid`, SMS als **Formulardaten** |
| **Soracom** | REST | **zwei** Header (`X-Soracom-API-Key` + `X-Soracom-Token`) aus `/v1/auth` | ⛔ braucht eine eigene Klasse (Zwei-Schritt-Auth, zwei Header) |
| **Hologram / Telnyx / BICS / floLIVE / 1oT** | REST | je Anbieter | ⛔/🟡 nicht geprüft – Muster: REST + Token-Header/API-Key, per Template versuchen |

🟡 = Vorlage liegt bei, **vor dem Einsatz gegen die Anbieter-Doku prüfen** (kein
Konto zum Testen vorhanden). ⛔ = Sonderlogik nötig, eigene Klasse nach dem
Muster `nce.py` / `whereversim.py`.

**WhereverSIM-Besonderheiten** (Doku: `https://docs.whereversim.com/`):
eine POST-URL, Abfragen im Body, Fehler kommen als `{"errors": […]}` mit HTTP 200,
Paginierung über `nextToken`, und Echtzeit nur per **WebSocket** – deshalb die
eigene Klasse. `sendSms` liefert nur ein Boolean (wird geprüft).

## 5. Echtzeit-SMS (`SMS_SUBSCRIBE=1`)

Unterstützt der Provider `watch_sms()` (aktuell wherever SIM), abonniert die
Bridge beim Start die SMS aller ICCIDs, die in der **Geräte-Registry** stehen
(Feld `iccid`). Eingehende Nachrichten:

- landen in der Tabelle `sim_sms` → abrufbar über
  `GET /api/v1/parent/sim/messages`
- lösen bei Richtung **MO** (Gerät → Server, z. B. „SOS") zusätzlich eine
  **Eltern-Benachrichtigung** aus (Web-Push + Apprise)

Das ist der einzige Pfad, der ohne Polling auskommt: Der Tracker kann sich per
SMS melden, und die Eltern erfahren es in Sekunden. Verbindungsabbrüche fängt
der Provider mit Wiederverbindung und Backoff ab (kein Reconnect-Hammering).

## 6. Tests

```bash
# Unit-Tests der Provider-Schicht (ohne Netzwerk, 31 Tests)
cd server/audio-bridge && python -m unittest discover -s tests -v

# Im Container (dort sind requests + websockets vorhanden → auch der WS-Test)
docker run --rm -v "$PWD/..:/src:ro" -w /src/audio-bridge ultimatetracker-audio-bridge \
  python -m unittest discover -s tests

# End-to-End (echter Anbieter, read-only)
bash scripts/smoke-test.sh      # Gruppe 15 prüft /sms/status
```

Abgedeckt sind u. a.: GraphQL-Antwortmapping, `nextToken`-Paginierung,
Boolean-Erfolgsprüfung, ICCID→Provider-ID-Auflösung, eigener Token-Body,
Formulardaten, Env-Platzhalter – und die **WebSocket-Subscription gegen einen
lokalen Fake-AppSync-Server**.
