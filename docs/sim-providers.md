# SIM-/SMS-Provider: anbieterneutrale Anbindung

Die Bridge spricht **nicht** direkt mit 1NCE, sondern über eine Provider-Schicht
(`server/audio-bridge/app/providers/`). Damit ist der Wechsel des Anbieters
(einschließlich einer neuen API-Version) eine Konfigurationsfrage – und der
Rest des Systems (UI, Endpunkte, Geräte-Registry) bleibt unverändert.

## 1. Aufbau

```
app/providers/
├── base.py      SimProvider (Schnittstelle) + SimInfo/SmsMessage
├── nce.py       1NCE Management API v2 (OAuth2, SIM-/SMS-Endpunkte)
├── generic.py   konfigurationsgetriebener Provider (Template für alle anderen)
└── __init__.py  Registry: get_provider() liest SIM_PROVIDER
```

Schnittstelle (`base.SimProvider`):

| Methode | Zweck |
|---|---|
| `configured()` | sind die Zugangsdaten vorhanden? |
| `list_sims()` | SIMs des Kontos (ICCID, MSISDN, Status, Kontingent) |
| `sms_quota(iccid)` | SMS-Kontingent einer SIM |
| `send_sms(iccid, text)` | MT-SMS senden |
| `list_sms(iccid, limit)` | MT-/MO-Verlauf |

API-Endpunkte der Bridge bleiben gleich:
`GET /api/v1/parent/sms/status`, `POST /api/v1/parent/sms`,
`GET /api/v1/parent/sms?iccid=…` – sie liefern zusätzlich `provider` mit.

## 2. Anbieter wählen

```env
SIM_PROVIDER=nce        # 1NCE (Standard, nutzt 1NCE_API_CLIENTID/SECRET)
SIM_PROVIDER=generic    # eigener Anbieter per JSON
SIM_PROVIDER=none       # SMS-Funktionen aus
```

Ohne `SIM_PROVIDER` wird `nce` genommen, sobald 1NCE-Zugangsdaten gesetzt sind.

## 3. Neuen Anbieter anbinden (ohne Codeänderung)

1. `server/sim-providers/mein-anbieter.json` anlegen – Vorlage:
   `server/sim-providers/example-1nce-generic.json` (beschreibt die 1NCE-API
   komplett über das Template und dient gleichzeitig als Test).
2. Zugangsdaten als `${…}`-Platzhalter eintragen, die Werte in `server/.env`
   setzen (Secrets bleiben aus der JSON-Datei heraus).
3. In `.env`: `SIM_PROVIDER=generic` und
   `SIM_PROVIDER_CONFIG=/etc/ut/providers/mein-anbieter.json`
   (`server/sim-providers/` ist in den Container gemountet).
4. `docker compose up -d --build audio-bridge` und
   `GET /api/v1/parent/sms/status` prüfen.

### Schema der JSON-Konfiguration

```jsonc
{
  "name": "mein-anbieter",
  "base_url": "https://api.example.com/v3",
  "auth": {
    "type": "basic | bearer | header | oauth2 | none",
    "username": "…", "password": "…",              // basic
    "token": "…",                                   // bearer
    "header_name": "X-API-Key", "header_value": "…",// header
    "token_url": "…", "client_id": "…", "client_secret": "…",
    "grant_type": "client_credentials", "basic_auth": true, "token_field": "access_token"
  },
  "endpoints": {
    "list_sims": {"method": "GET",  "path": "/sims", "items": "$"},
    "send_sms":  {"method": "POST", "path": "/sims/{iccid}/sms",
                  "body": {"payload": "{text}", "source_address": "{source}"}},
    "list_sms":  {"method": "GET",  "path": "/sims/{iccid}/sms", "items": "data.items"},
    "sms_quota": {"method": "GET",  "path": "/sims/{iccid}/quota/sms"}
  },
  "fields": {                       // Feldnamen des Anbieters → unsere Namen
    "sim":  {"iccid": "id.iccid", "msisdn": "id.msisdn", "quota_sms": "quota.sms"},
    "sms":  {"id": "message_id", "text": "body", "direction": "type", "state": "status"},
    "quota": {"remaining": "left", "total": "all"}
  },
  "maps": {                         // Zahlen/Codes → lesbare Werte
    "direction": {"1": "MT", "2": "MO"},
    "state": {"4": "DELIVERED", "5": "FAILED"}
  }
}
```

- **`items`**: Pfad zur Liste in der Antwort (`$` = Wurzel, `data.items` = verschachtelt).
- **`fields`**: Pfade ins Objekt (`a.b.c`); fehlt ein Feld, bleibt der Wert leer.
- **`expect`** (optional, nur `send_sms`): Erfolgsprüfung im Antwort-Body für
  APIs, die keinen Fehlerstatus, sondern einen Wert liefern
  (`{"path": "data.sendSms", "equals": true}`).
- **Platzhalter**: `{iccid}`, `{text}`, `{source}` in Pfad/Body; `${VAR}` bzw.
  `${VAR:-default}` in der Konfiguration (aus der Umgebung).
- **Versionen**: Steckt die Version im Pfad (wie bei 1NCE `/v2/…`), einfach in
  `base_url`/`path` eintragen. Beim 1NCE-Provider ist sie zusätzlich über
  `NCE_API_VERSION` umstellbar (Default `v2`) – ein Wechsel auf `v3` wäre damit
  eine Umgebungsvariable, kein Codeumbau.

## 4. Beispiel: wherever SIM (GraphQL statt REST)

`https://docs.whereversim.com/` ist die aktuelle Referenz der **wherever SIM
Link+ GraphQL-API** (AWS AppSync) – das erklärt das „wilde" Aussehen: **eine**
POST-URL (`https://graphql.api.whereversim.com/graphql`), die Abfragen stecken
im Body; dazu WebSocket-Subscriptions unter `/graphql/realtime`.

| Eigenschaft | whereversim | 1NCE (zum Vergleich) |
|---|---|---|
| Stil | GraphQL (Queries/Mutations) | REST |
| Auth | statischer Header `Authorization: <Token>` | OAuth2 `client_credentials` |
| SIM-Liste | `query { listSims(limit:) { items { … } } }` | `GET /v2/sims` |
| SMS senden | `mutation { sendSms(iccid:, text:) }` → **Boolean** | `POST /v2/sims/{iccid}/sms` |
| SMS-Verlauf | `query { listSms(iccid:, limit:) { items { … } } }` | `GET /v2/sims/{iccid}/sms` |
| Paginierung | `nextToken` | keine (Liste komplett) |
| Push | WebSocket-Subscriptions (`onSms`, `updatedSim`) | – |

**Das Template deckt das ab** – mitgeliefert als
`server/sim-providers/example-whereversim-generic.json`:

- Auth: `{"type": "header", "header_name": "Authorization", "header_value": "${WHEREVERSIM_API_TOKEN}"}`
- Endpunkte: `path: ""` (also genau die `base_url`), `items: "data.listSims.items"` bzw.
  `"data.listSms.items"` (GraphQL verschachtelt unter `data`), Query + `variables` im `body`.
- `sendSms` liefert **nur ein Boolean** → dafür gibt es die optionale Erfolgsprüfung:
  ```json
  "expect": {"path": "data.sendSms", "equals": true}
  ```
  Ist der Wert `false`, meldet die Bridge einen Fehler statt „gesendet".

**Nicht** über das Template abgedeckt (bräuchte eine eigene Provider-Klasse wie
`nce.py`): die **WebSocket-Subscriptions** (Echtzeit-Push bei SMS/SIM-Änderung)
und Mehrseiten-Abfragen über `nextToken` (aktuell wird eine Seite mit
`limit: 100` geholt).

> Nebenbei: whereversim hat **zwei** API-Welten. Die oben beschriebene GraphQL-API
> gehört zu **Link+**. Für das **tech+**-Portal gibt es zusätzlich eine klassische
> REST-/SOAP-/Push-API (Doku im eingeloggten Portal bzw.
> `help.whereversim.de`) – auch die ließe sich über das Template anbinden.

## 5. Beispiele für andere Anbieter (Muster, nicht getestet)

| Anbieter | Auth | SIM-Liste | SMS senden |
|---|---|---|---|
| **EMnify** | OAuth2 `client_credentials` (`/api/v1/authenticate`) | `/api/v1/sims` | `/api/v1/sim/{id}/sms` |
| **Twilio Super SIM** | Basic (Account SID/Token) | `/v1/Sims` | `/v1/SmsCommands` (`Sim=…`, `Payload=…`) |
| **Soracom** | Header (`X-Soracom-API-Key`/`-Token`) | `/v1/sims` | `/v1/subscribers/{imsi}/send_sms` |
| **Hologram** | Header (`X-Hologram-API-Key`) | `/api/1/devices` | `/api/1/devices/{id}/sms` |

Diese Zeilen sind **Recherche-Muster** – Feldnamen und Pfade vor dem Einsatz
gegen die jeweilige Doku prüfen und in der JSON-Konfiguration hinterlegen.
Ein Provider, der Sonderlogik braucht (Signierung, Multipart, Paginierung),
bekommt wie 1NCE eine eigene Klasse in `app/providers/`.

## 6. Tests

```bash
# Unit-Tests der Provider-Schicht (ohne Netzwerk)
cd server/audio-bridge && python -m unittest discover -s tests -v

# End-to-End (echter Anbieter, read-only)
bash scripts/smoke-test.sh      # Gruppe 15 prüft /sms/status
```
