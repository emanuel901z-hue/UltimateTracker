#!/usr/bin/env bash
# Smoke-Test für den Server-Stack (Traccar + Audio-Bridge).
# Aufruf innerhalb der Distro (Stack muss laufen):
#   bash scripts/smoke-test.sh
#
# Voraussetzungen: curl, python3; server/.env mit gesetzten Tokens.

set -euo pipefail

SERVER_DIR="${SERVER_DIR:-$HOME/UltimateTracker/server}"
BASE="${BASE:-http://localhost:8085}"
TRACCAR="${TRACCAR:-http://localhost:5055}"
WEB="${WEB:-http://localhost:8082}"

cd "$SERVER_DIR"
DTOK=$(grep '^DEVICE_TOKEN=' .env | cut -d= -f2)
PTOK=$(grep '^PARENT_TOKEN=' .env | cut -d= -f2)
PARENT_USER=$(grep '^PARENT_USER=' .env | cut -d= -f2- || true)
PARENT_PASSWORD=$(grep '^PARENT_PASSWORD=' .env | cut -d= -f2- || true)

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

python3 - "$TMP/test.wav" <<'PY'
import math, struct, sys, wave
w = wave.open(sys.argv[1], "wb")
w.setnchannels(1)
w.setsampwidth(2)
w.setframerate(8000)
w.writeframes(b"".join(struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * i / 8000))) for i in range(8000)))
w.close()
PY

pass() { echo "  OK   - $1"; }
fail() { echo "  FAIL - $1"; exit 1; }
info() { echo "  INFO - $1"; }

echo "1) Health"
curl -sf "$BASE/healthz" | grep -q '"status":"ok"' && pass "Bridge erreichbar" || fail "Bridge nicht erreichbar"

echo "2) Uplink (Tracker -> Bridge)"
UP=$(curl -sf -X POST -H "X-Auth-Token: $DTOK" -F device_id=TEST123 -F audio=@"$TMP/test.wav" "$BASE/api/v1/device/messages")
echo "$UP" | grep -q '"converted":true' && pass "Upload + Konvertierung nach MP3" || fail "Upload fehlgeschlagen: $UP"

echo "3) Eltern-Liste"
curl -sf -H "X-Auth-Token: $PTOK" "$BASE/api/v1/parent/messages?limit=3" | grep -q '"direction":"in"' && pass "Nachricht sichtbar" || fail "Liste leer"

echo "4) Downlink (Eltern -> Bridge)"
curl -sf -X POST -H "X-Auth-Token: $PTOK" -F device_id=TEST123 -F audio=@"$TMP/test.wav" "$BASE/api/v1/parent/messages" | grep -q '"converted":true' && pass "Konvertierung nach IMA-ADPCM" || fail "Downlink-Konvertierung fehlgeschlagen"

echo "5) Tracker-Poll + Download"
PEND=$(curl -sf -H "X-Auth-Token: $DTOK" "$BASE/api/v1/device/pending?device_id=TEST123")
MID=$(printf '%s' "$PEND" | python3 -c 'import json,sys; print(json.load(sys.stdin)["message_id"] or "")')
[ -n "$MID" ] && pass "Nachricht angekündigt ($MID)" || fail "Keine Nachricht im Poll"
curl -sf -H "X-Auth-Token: $DTOK" -o "$TMP/down.wav" "$BASE/api/v1/device/messages/$MID/audio"
head -c 12 "$TMP/down.wav" | grep -q "RIFF" && pass "WAV-Datei geladen ($(stat -c%s "$TMP/down.wav") Bytes)" || fail "Download ist keine WAV-Datei"

echo "6) Suchmodus"
curl -sf -X POST -H "X-Auth-Token: $PTOK" -F active=true "$BASE/api/v1/parent/search-mode" | grep -q '"search_mode":true' && pass "Suchmodus setzbar" || fail "Suchmodus fehlgeschlagen"

echo "7) Auth-Schutz"
CODE=$(curl -s -o /dev/null -w '%{http_code}' -H "X-Auth-Token: falsch" "$BASE/api/v1/parent/messages")
[ "$CODE" = "401" ] && pass "Falsches Token -> 401" || fail "Auth greift nicht (HTTP $CODE)"

echo "8) Traccar Web"
CODE=$(curl -s -o /dev/null -w '%{http_code}' "$WEB")
[ "$CODE" = "200" ] && pass "Web-UI erreichbar" || fail "Web-UI HTTP $CODE"

echo "9) Traccar OsmAnd-Position"
curl -sf "$TRACCAR/?id=TEST123&lat=48.1372&lon=11.5756&batt=87&timestamp=$(date +%s)" >/dev/null && pass "Position akzeptiert" || fail "Position abgelehnt"

echo "10) Geräte-Registry (IMEI/MSISDN)"
curl -sf -X PUT -H "X-Auth-Token: $PTOK" -H 'Content-Type: application/json' \
  -d '{"name":"Testtracker","imei":"TEST123","msisdn":"+491700000000","notes":"Smoke-Test"}' \
  "$BASE/api/v1/parent/devices/TEST123" | grep -q '"id":"TEST123"' && pass "Gerät gespeichert" || fail "Geräte-Upsert fehlgeschlagen"
curl -sf -H "X-Auth-Token: $PTOK" "$BASE/api/v1/parent/devices" | grep -q '"TEST123"' && pass "Gerät in Liste" || fail "Gerät fehlt in Liste"

echo "11) Find-My-Ingest (Apple/Google-Gegenstück)"
FM=$(curl -sf -X POST -H 'Content-Type: application/json' \
  -d '{"provider":"apple","beacon_id":"BEACON-TEST","lat":48.1372,"lon":11.5756,"timestamp":1770000000}' \
  "$BASE/api/v1/findmy/locations")
echo "$FM" | grep -q '"stored":1' && pass "Position gespeichert" || fail "Ingest fehlgeschlagen: $FM"
curl -sf -H "X-Auth-Token: $PTOK" "$BASE/api/v1/parent/findmy/locations?limit=5" | grep -q 'BEACON-TEST' && pass "Position in Liste" || fail "Position fehlt in Liste"
if echo "$FM" | grep -q '"forwarded":1'; then
  pass "Position an Traccar weitergeleitet"
else
  info "Traccar-Forwarding aus oder nicht erreichbar (TRACCAR_FORWARD_URL prüfen)"
fi

echo "12) Find-My-Toleranz (unbekanntes Format)"
curl -sf -X POST -H 'Content-Type: application/json' \
  -d '{"source":"google","id":"BEACON-G2","latitude":48.15,"longitude":11.6,"time":"2026-10-11T12:00:00Z"}' \
  "$BASE/api/v1/findmy/locations" | grep -q '"stored":1' && pass "Alternatives Schema akzeptiert" || fail "Toleranter Ingest fehlgeschlagen"

echo "13) Firmware/OTA (B7)"
head -c 1024 /dev/zero > "$TMP/fw.bin"
curl -sf -X POST -H "X-Auth-Token: $PTOK" -F version=9.9.9 -F notes=Smoke-Test \
  -F firmware=@"$TMP/fw.bin" "$BASE/api/v1/parent/firmware" | grep -q '"version":"9.9.9"' \
  && pass "Firmware hochgeladen" || fail "Firmware-Upload fehlgeschlagen"
curl -sf -H "X-Auth-Token: $DTOK" "$BASE/api/v1/device/firmware/latest?fw=0.1.0" | grep -q '"update":true' \
  && pass "Update-Angebot für alte Version" || fail "Kein Update-Angebot"
curl -sf -X POST -H "X-Auth-Token: $DTOK" -H 'Content-Type: application/json' \
  -d '{"device_id":"TEST123","fw":"0.1.0"}' "$BASE/api/v1/device/sync" | grep -q '"ota":{' \
  && pass "OTA-Angebot im Sync enthalten" || fail "OTA fehlt im Sync"
SIZE=$(curl -sf -H "X-Auth-Token: $DTOK" "$BASE/api/v1/device/firmware/9.9.9/download" | wc -c)
[ "$SIZE" = "1024" ] && pass "Download liefert 1024 Bytes" || fail "Download-Größe: $SIZE"
curl -sf -H "X-Auth-Token: $DTOK" "$BASE/api/v1/device/firmware/latest?fw=9.9.9" | grep -q '"update":false' \
  && pass "Aktuelle Version bekommt kein Angebot" || fail "Angebot trotz aktueller Version"
curl -sf -X DELETE -H "X-Auth-Token: $PTOK" "$BASE/api/v1/parent/firmware/9.9.9" | grep -q '"deleted":"9.9.9"' \
  && pass "Test-Firmware wieder entfernt" || fail "Aufräumen fehlgeschlagen"

echo "14) Push (PWA/Web-Push)"
# Container-ID dynamisch bestimmen (funktioniert auch für parallele Instanzen)
BRIDGE_CID=$(docker ps --filter "name=audio-bridge" --format '{{.ID}}' | head -1)
KEYS=$(docker exec -i "$BRIDGE_CID" python - <<'PY'
import base64, os
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
key = ec.generate_private_key(ec.SECP256R1())
raw = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
print(base64.urlsafe_b64encode(raw).rstrip(b"=").decode())
print(base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode())
PY
)
P256=$(printf '%s' "$KEYS" | sed -n 1p)
AUTH=$(printf '%s' "$KEYS" | sed -n 2p)
curl -sf -H "X-Auth-Token: $PTOK" "$BASE/api/v1/parent/push/key" | grep -q '"key"' \
  && pass "VAPID-Schlüssel verfügbar" || fail "Kein VAPID-Schlüssel"
curl -sf -X POST -H "X-Auth-Token: $PTOK" -H 'Content-Type: application/json' \
  -d "{\"endpoint\":\"https://example.invalid/push/smoke\",\"keys\":{\"p256dh\":\"$P256\",\"auth\":\"$AUTH\"}}" \
  "$BASE/api/v1/parent/push/subscribe" | grep -q '"subscribed":true' \
  && pass "Abo gespeichert (gültiges Schlüsselmaterial)" || fail "Abo fehlgeschlagen"
curl -sf -X POST -H "X-Auth-Token: $PTOK" "$BASE/api/v1/parent/push/test" | grep -q '"total":1' \
  && pass "Versand durchlaufen (Ziel absichtlich unerreichbar)" || fail "Versand fehlgeschlagen"
curl -sf -X DELETE -H "X-Auth-Token: $PTOK" -H 'Content-Type: application/json' \
  -d '{"endpoint":"https://example.invalid/push/smoke"}' "$BASE/api/v1/parent/push/subscribe" | grep -q '"subscriptions":0' \
  && pass "Abo wieder entfernt" || fail "Abo nicht entfernt"

echo "15) 1NCE-SMS-API"
SMS_STATUS=$(curl -s -H "X-Auth-Token: $PTOK" "$BASE/api/v1/parent/sms/status")
echo "$SMS_STATUS" | grep -q '"configured"' \
  && pass "Status-Endpunkt antwortet" || fail "Status-Endpunkt fehlerhaft"
if echo "$SMS_STATUS" | grep -q '"configured":true'; then
  pass "1NCE-Zugangsdaten aktiv (SIMs: $(echo "$SMS_STATUS" | grep -o '"count":[0-9]*' | cut -d: -f2))"
else
  echo "  SKIP - 1NCE nicht konfiguriert (1NCE_API_CLIENTID/SECRET in .env)"
fi
CODE=$(curl -s -o /dev/null -w "%{http_code}" -H "X-Auth-Token: $PTOK" \
  "$BASE/api/v1/parent/sms?iccid=0000000000000000000")
# 502 = Anbieter antwortet mit Fehler (Zugangsdaten gesetzt)
# 503 = kein SIM-Provider konfiguriert (z. B. in der CI ohne 1NCE-Zugangsdaten)
if [ "$CODE" = "502" ] || [ "$CODE" = "503" ]; then
  pass "Ungültige ICCID sauber beantwortet (HTTP $CODE)"
else
  fail "Unerwarteter Status bei ungültiger ICCID: $CODE"
fi

echo "16) Dienste-Übersicht (eine Oberfläche für alles)"
SERVICES=$(curl -s -H "X-Auth-Token: $PTOK" "$BASE/api/v1/parent/services")
echo "$SERVICES" | grep -q '"services"' && pass "Übersicht abrufbar" || fail "Übersicht fehlerhaft"
CHECK=$(printf '%s' "$SERVICES" | python3 -c "
import json, sys
data = json.load(sys.stdin)
by_key = {service['key']: service for service in data['services']}
problems = []
if by_key.get('traccar', {}).get('status') != 'up':
    problems.append('Traccar nicht als erreichbar gemeldet')
if by_key.get('findmy-bridge', {}).get('status') != 'n/a':
    problems.append('findmy-bridge falsch bewertet')
if 'apple-findmy' not in by_key:
    problems.append('Apple-Eintrag fehlt')
if 'sso' not in data:
    problems.append('SSO-Status fehlt')
print('; '.join(problems))
")
[ -z "$CHECK" ] && pass "Dienste vollständig (Traccar erreichbar, SSO-Status, Apple dabei)" \
  || fail "Übersicht: $CHECK"

echo "17) Anmeldung & Mehrkind-Übersicht"
LOGIN_FAIL=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"definitiv-falsch-1234"}' "$BASE/api/v1/auth/login")
[ "$LOGIN_FAIL" = "401" ] && pass "Falsches Passwort abgelehnt (HTTP 401)" || fail "Login-Schutz: $LOGIN_FAIL"
NOAUTH=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/v1/parent/overview")
[ "$NOAUTH" = "401" ] && pass "Ohne Anmeldung kein Zugriff (HTTP 401)" || fail "Zugriffsschutz: $NOAUTH"
curl -s -H "X-Auth-Token: $PTOK" "$BASE/api/v1/auth/me" | grep -q '"kind":"token"' \
  && pass "API-Token funktioniert weiterhin" || fail "API-Token abgelehnt"
curl -s -H "X-Auth-Token: $PTOK" "$BASE/api/v1/parent/overview" | grep -q '"children"' \
  && pass "Kinder-Übersicht abrufbar" || fail "Kinder-Übersicht fehlgeschlagen"
if [ -n "${PARENT_PASSWORD:-}" ]; then
  SESSION=$(curl -s -X POST -H 'Content-Type: application/json' \
    -d "{\"username\":\"${PARENT_USER:-admin}\",\"password\":\"${PARENT_PASSWORD}\"}" \
    "$BASE/api/v1/auth/login" | python3 -c "import json,sys; print(json.load(sys.stdin).get('token',''))" 2>/dev/null)
  [ -n "$SESSION" ] && pass "Anmeldung mit Benutzer/Passwort erfolgreich" || fail "Anmeldung fehlgeschlagen"
  curl -s -H "X-Auth-Token: $SESSION" "$BASE/api/v1/parent/overview" | grep -q '"children"' \
    && pass "Sitzungstoken funktioniert für die API" || fail "Sitzungstoken abgelehnt"
else
  echo "  SKIP - PARENT_PASSWORD nicht gesetzt (Login-Test übersprungen)"
fi

echo "18) Passwort ändern / zurücksetzen (temporärer Benutzer)"
TMPUSER="smoke-$$"
TMPPW1="Smoke-Passwort-1"
TMPPW2="Smoke-Passwort-2"
curl -s -X POST -H "X-Auth-Token: $PTOK" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$TMPUSER\",\"password\":\"$TMPPW1\",\"role\":\"parent\"}" \
  "$BASE/api/v1/auth/users" | grep -q "\"created\":\"$TMPUSER\"" \
  && pass "Temporärer Benutzer angelegt" || fail "Benutzer anlegen fehlgeschlagen"

TMP_SESSION=$(curl -s -X POST -H 'Content-Type: application/json' \
  -d "{\"username\":\"$TMPUSER\",\"password\":\"$TMPPW1\"}" "$BASE/api/v1/auth/login" \
  | python3 -c "import json,sys; print(json.load(sys.stdin).get('token',''))" 2>/dev/null)
[ -n "$TMP_SESSION" ] && pass "Anmeldung als temporärer Benutzer" || fail "Anmeldung fehlgeschlagen"

CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "X-Auth-Token: $TMP_SESSION" \
  -H 'Content-Type: application/json' -d "{\"current\":\"falsch-falsch\",\"new\":\"$TMPPW2\"}" \
  "$BASE/api/v1/auth/password")
[ "$CODE" = "401" ] && pass "Falsches aktuelles Passwort abgelehnt" || fail "Passwortwechsel-Schutz: $CODE"

curl -s -X POST -H "X-Auth-Token: $TMP_SESSION" -H 'Content-Type: application/json' \
  -d "{\"current\":\"$TMPPW1\",\"new\":\"$TMPPW2\"}" "$BASE/api/v1/auth/password" \
  | grep -q '"changed":true' && pass "Eigenes Passwort geändert" || fail "Passwortwechsel fehlgeschlagen"

curl -s -X POST -H 'Content-Type: application/json' -d "{\"username\":\"$TMPUSER\",\"password\":\"$TMPPW2\"}" \
  "$BASE/api/v1/auth/login" | grep -q '"token"' \
  && pass "Anmeldung mit neuem Passwort möglich" || fail "Neues Passwort funktioniert nicht"
curl -s -o /dev/null -w "%{http_code}" -X POST -H 'Content-Type: application/json' \
  -d "{\"username\":\"$TMPUSER\",\"password\":\"$TMPPW1\"}" "$BASE/api/v1/auth/login" | grep -q "401" \
  && pass "Altes Passwort abgelehnt" || fail "Altes Passwort funktioniert noch"

TMPID=$(curl -s -H "X-Auth-Token: $PTOK" "$BASE/api/v1/auth/users" \
  | python3 -c "import json,sys; print(next(u['id'] for u in json.load(sys.stdin)['users'] if u['username']=='$TMPUSER'))" 2>/dev/null)
curl -s -X POST -H "X-Auth-Token: $PTOK" -H 'Content-Type: application/json' \
  -d '{"new":"Admin-Reset-Passwort-9"}' "$BASE/api/v1/auth/users/$TMPID/password" \
  | grep -q '"reset"' && pass "Admin-Reset (ohne altes Passwort)" || fail "Admin-Reset fehlgeschlagen"
curl -s -o /dev/null -w "%{http_code}" -H "X-Auth-Token: $TMP_SESSION" "$BASE/api/v1/auth/me" | grep -q "401" \
  && pass "Sitzungen nach Reset ungültig" || fail "Alte Sitzung noch gültig"

curl -s -X DELETE -H "X-Auth-Token: $PTOK" "$BASE/api/v1/auth/users/$TMPID" | grep -q '"deleted"' \
  && pass "Temporärer Benutzer entfernt" || fail "Aufräumen fehlgeschlagen"

echo "19) Betrieb: Monitoring, Einstellungen, Backup"
SYS=$(curl -s -H "X-Auth-Token: $PTOK" "$BASE/api/v1/parent/system")
echo "$SYS" | grep -q '"uptime_s"' && pass "Systemwerte abrufbar" || fail "Systemwerte fehlgeschlagen"
echo "$SYS" | grep -q '"messages"' && pass "Datenbestand enthalten" || fail "Datenbestand fehlt"
SETTINGS=$(curl -s -H "X-Auth-Token: $PTOK" "$BASE/api/v1/parent/settings")
echo "$SETTINGS" | grep -q '"poll_interval_s"' && pass "Einstellungen abrufbar" || fail "Einstellungen fehlgeschlagen"
OLD=$(printf '%s' "$SETTINGS" | python3 -c "import json,sys; print(json.load(sys.stdin)['values']['search_mode_minutes'])")
NEW=$((OLD + 1))
APPLIED=$(curl -s -X PUT -H "X-Auth-Token: $PTOK" -H 'Content-Type: application/json' \
  -d "{\"search_mode_minutes\": $NEW}" "$BASE/api/v1/parent/settings" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['values']['search_mode_minutes'])" 2>/dev/null)
[ "$APPLIED" = "$NEW" ] && pass "Einstellung geändert (wirkt sofort)" || fail "Einstellung nicht übernommen ($APPLIED)"
curl -s -X PUT -H "X-Auth-Token: $PTOK" -H 'Content-Type: application/json' \
  -d "{\"search_mode_minutes\": $OLD}" "$BASE/api/v1/parent/settings" >/dev/null
SIZE=$(curl -s -H "X-Auth-Token: $PTOK" "$BASE/api/v1/parent/maintenance/backup" | wc -c)
[ "$SIZE" -gt 1000 ] && pass "Backup herunterladbar ($SIZE Bytes)" || fail "Backup zu klein: $SIZE"

echo "20) Karte (Kartendaten direkt aus der Bridge)"
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/v1/parent/map")
[ "$CODE" = "401" ] && pass "Karte ohne Anmeldung gesperrt (HTTP 401)" || fail "Karten-Schutz: $CODE"
MAP=$(curl -s -H "X-Auth-Token: $PTOK" "$BASE/api/v1/parent/map")
echo "$MAP" | grep -q '"tiles"' && pass "Kartendaten abrufbar" || fail "Kartendaten fehlgeschlagen"
CHECK=$(printf '%s' "$MAP" | python3 -c "
import json, sys
data = json.load(sys.stdin)
problems = []
if not str(data.get('tiles', '')).startswith('http'):
    problems.append('keine Kachel-URL')
for key in ('trackers', 'beacons'):
    if key not in data:
        problems.append(key + ' fehlt')
for tracker in data.get('trackers', []):
    if not (-90 <= tracker['latitude'] <= 90 and -180 <= tracker['longitude'] <= 180):
        problems.append('unplausible Koordinaten')
print('; '.join(problems))
")
[ -z "$CHECK" ] && pass "Kacheln + Marker plausibel" || fail "Karte: $CHECK"
curl -s -o /dev/null -w "" -H "X-Auth-Token: $PTOK" "$BASE/static/vendor/leaflet/leaflet.js"
LEAFLET=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/static/vendor/leaflet/leaflet.js")
[ "$LEAFLET" = "200" ] && pass "Leaflet wird ausgeliefert (selbst gehostet)" || fail "Leaflet: HTTP $LEAFLET"

echo "21) Setup-Assistent (Status der Einrichtung)"
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/v1/parent/setup")
[ "$CODE" = "401" ] && pass "Setup-Status ohne Anmeldung gesperrt (HTTP 401)" || fail "Setup-Schutz: $CODE"
SETUP=$(curl -s -H "X-Auth-Token: $PTOK" "$BASE/api/v1/parent/setup")
echo "$SETUP" | grep -q '"steps"' && pass "Einrichtungsschritte abrufbar" || fail "Setup-Status fehlgeschlagen"
CHECK=$(printf '%s' "$SETUP" | python3 -c "
import json, sys
data = json.load(sys.stdin)
problems = []
steps = data.get('steps', {})
for key in ('willkommen', 'geraet', 'sim', 'traccar', 'benachrichtigungen', 'funktionstest'):
    if key not in steps:
        problems.append('Schritt ' + key + ' fehlt')
if not isinstance(data.get('done'), bool):
    problems.append('done fehlt')
if data.get('sso', {}).get('available') is None:
    problems.append('SSO-Status fehlt')
print('; '.join(problems))
")
[ -z "$CHECK" ] && pass "Alle Assistenten-Schritte vorhanden" || fail "Setup: $CHECK"

echo
echo "Alle Smoke-Tests bestanden."
