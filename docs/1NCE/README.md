# 1NCE-API-Spezifikationen (Referenz)

Diese Dateien sind die **öffentlichen OpenAPI-Spezifikationen** der 1NCE-APIs,
hier als Referenz für die Integration in `server/audio-bridge/app/main.py`
(Abschnitt „1NCE-API-Client", Endpunkte `/api/v1/parent/sms*`).

| Datei | Inhalt | Bezug im Code |
|---|---|---|
| `authorization-v2.yaml` | `POST /oauth/token` (OAuth2 `client_credentials`, Basic-Auth mit Client-ID/Secret) | `nce_token()` |
| `sim-management-v2.json` | SIM Management v2: `GET /v2/sims`, `GET/POST /v2/sims/{iccid}/sms`, `GET /v2/sims/{iccid}/quota/sms` u. a. | `sms_status()`, `sms_send()`, `sms_list()` |

Quelle: 1NCE Developer Hub / API-Portal (öffentliche Dokumentation).
Bei einer Veröffentlichung des Repos prüfen, ob die Specs mit eingecheckt
bleiben dürfen oder nur verlinkt werden sollen (siehe `TODO.md`, Abschnitt F).

**Fachliche Kernpunkte** (siehe `docs/sms.md`):

- SMS nur **Device ↔ 1NCE-Plattform** (A2P), **kein** P2P-Handy-↔-Gerät.
- **SMS nur im LTE-M-Modus** (über NB-IoT nicht möglich).
- MT-SMS wird bis zu 24 h gepuffert und beim nächsten Attach zugestellt.
- Kontingent: 250 SMS in der 1NCE IoT Lifetime Flat; Kontostand über
  `GET /v2/sims/{iccid}/quota/sms` abfragbar.
