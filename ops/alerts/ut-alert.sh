#!/usr/bin/env bash
# Sendet eine Meldung an den lokalen ntfy-Dienst (Alarmkanal der Maschine).
#
# Aufruf:  ut-alert.sh "Titel" "Text" [Priorität]
#
# Das Thema steht in ~/UltimateTracker/ops/.env (NTFY_TOPIC). Damit melden sich
# SMART-Warnungen, Plattenplatz, Backup-Fehler und (über Apprise) auch die
# Tracker-Ereignisse – ein Kanal für alles.

set -u

ENV_FILE="${UT_OPS_ENV:-$HOME/UltimateTracker/ops/.env}"
NTFY_URL="${UT_NTFY_URL:-http://localhost:8086}"

TOPIC=$(grep -m1 '^NTFY_TOPIC=' "$ENV_FILE" 2>/dev/null | cut -d= -f2-)
TOPIC="${TOPIC:-ut-alerts}"

TITLE="${1:-manucloud}"
BODY="${2:-}"
PRIORITY="${3:-3}"

curl -s -o /dev/null -m 10 \
	-H "Title: $TITLE" \
	-H "Priority: $PRIORITY" \
	-H "Tags: warning" \
	--data-binary "$BODY" \
	"$NTFY_URL/$TOPIC"
