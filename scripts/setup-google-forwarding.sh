#!/usr/bin/env bash
# Richtet in der Google-Find-Hub-WebUI für alle Geräte einen Weiterleitungs-
# Endpunkt auf die Audio-Bridge ein (POST /api/v1/findmy/locations).
#
# Damit landen die Google-Find-Hub-Positionen in der Bridge – und von dort über
# die Sensor-Fusion in Karte/Traccar (docs/fusion.md, docs/findmy.md).
#
# Idempotent: vorhandene Endpunkte und andere Einstellungen bleiben erhalten.
# Nach dem Google-Login einmal ausführen; für später neu hinzugefügte Geräte
# einfach erneut.
#
# Aufruf in der WSL-Distro (Stack läuft, Profil `findmy`):
#   bash scripts/setup-google-forwarding.sh
#
# Danach in der Eltern-UI: Tab „Geräte" → „Find-My-Beacons zuordnen" – die
# Beacons erscheinen dort als „google / <Gerätename>".
set -euo pipefail

SERVER_DIR="${SERVER_DIR:-$HOME/UltimateTracker/server}"
BASE="${BASE:-http://localhost:8085}"
TARGET_URL="${GOOGLE_FORWARD_URL:-http://audio-bridge:8085/api/v1/findmy/locations}"
CRON="${GOOGLE_FORWARD_CRON:-*/15 * * * *}"
HOSTNAME_="${SITE_FINDMY:-findmy.localhost}"

cd "$SERVER_DIR"

CONTAINER=$(docker ps --filter 'name=google-findmy-webui' --format '{{.Names}}' | head -1)
if [ -z "$CONTAINER" ]; then
	echo "Kein WebUI-Container gefunden – läuft das Compose-Profil 'findmy'?" >&2
	exit 1
fi

PT=$(docker compose exec -T audio-bridge python -c "import app.main as m; print(m.parent_token())" | tr -d "\r")
TICKET=$(curl -s -X POST -H "X-Auth-Token: $PT" "$BASE/api/v1/parent/sso/ticket" \
	| python3 -c "import json,sys; print(json.load(sys.stdin)['ticket'])")
RESP=$(curl -sk -i --resolve "$HOSTNAME_:443:127.0.0.1" \
	"https://$HOSTNAME_/_sso/session?ticket=$TICKET&next=/")
COOKIE=$(printf '%s' "$RESP" | grep -i '^set-cookie:' | sed -E 's/.*ut_session=([^;]+).*/\1/' | tr -d '\r')
if [ -z "$COOKIE" ]; then
	echo "SSO-Anmeldung an der WebUI fehlgeschlagen (läuft Caddy?)." >&2
	exit 1
fi

fetch() { curl -sk --resolve "$HOSTNAME_:443:127.0.0.1" -H "Cookie: ut_session=$COOKIE" "$@"; }

DEVS=$(fetch "https://$HOSTNAME_/settings" | grep -oE "/settings/devices/[0-9a-fA-F-]{8,}" | sed 's#.*/##' | sort -u)
if [ -z "$DEVS" ]; then
	echo "Keine Geräte gefunden. Zuerst in der UI bei Google anmelden:" >&2
	echo '  https://<host> -> Tab Config -> "Sign in with Google"' >&2
	exit 1
fi

echo "Weiterleitungsziel: $TARGET_URL (cron: $CRON)"
for dev in $DEVS; do
	CURRENT=$(fetch "https://$HOSTNAME_/settings/devices/$dev/yaml" | python3 -c '
import html, re, sys
m = re.search(r"<textarea[^>]*>(.*?)</textarea>", sys.stdin.read(), re.S)
print(html.unescape(m.group(1)) if m else "")
')
	MERGED=$(docker exec -e UT_YAML="$CURRENT" -e UT_TARGET="$TARGET_URL" -e UT_CRON="$CRON" \
		"$CONTAINER" python3 -c '
import os, yaml
cfg = yaml.safe_load(os.environ["UT_YAML"]) or {}
target = os.environ["UT_TARGET"]
cfg.setdefault("display_name", "")
endpoints = cfg.setdefault("endpoints", [])
if any((e or {}).get("url") == target for e in endpoints):
    print("SKIP")
else:
    endpoints.append({
        "alias": "UltimateTracker-Bridge",
        "method": "POST",
        "url": target,
        "headers": {},
        "body_type": "json",
        "body": ("{\"provider\": \"google\", \"beacon_id\": \"{{device_name}}\", "
                 "\"lat\": {{latitude}}, \"lon\": {{longitude}}, "
                 "\"accuracy\": {{accuracy_m}}, \"timestamp\": {{google_timestamp}}}"),
        "cron": os.environ["UT_CRON"],
    })
    print(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), end="")
')
	if [ "$MERGED" = "SKIP" ]; then
		echo "  $dev: Endpunkt ist schon vorhanden – übersprungen"
		continue
	fi
	CODE=$(curl -sk -o /dev/null -w '%{http_code}' -X POST \
		--resolve "$HOSTNAME_:443:127.0.0.1" -H "Cookie: ut_session=$COOKIE" \
		--data-urlencode "yaml_text=$MERGED" \
		"https://$HOSTNAME_/settings/devices/$dev/yaml")
	echo "  $dev: Endpunkt gesetzt (HTTP $CODE)"
done

echo
echo "Fertig. In der Eltern-UI jetzt die Beacons zuordnen:"
echo '  Geraete -> "Find-My-Beacons zuordnen" (Eintraege "google / <Geraetename>").'
