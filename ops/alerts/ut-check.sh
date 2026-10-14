#!/usr/bin/env bash
# Täglicher Betriebscheck der Server-Maschine → Alarm über ut-alert.sh.
#
# Aufruf (Cron, täglich 07:00):  ut-check.sh
#
# Prüft:
#   * Plattenplatz auf / (Warnung ab 85 %)
#   * SMART-Gesundheit der Systemplatte (falls smartctl vorhanden)
#   * Alter der letzten Sicherung (Warnung ab 2 Tagen)
#   * Zustand der Tracker-Container (nicht "running")

set -u

ALERT="${UT_ALERT:-$HOME/UltimateTracker/ops/alerts/ut-alert.sh}"
BACKUP_DIR="${UT_BACKUP_DIR:-$HOME/UltimateTracker/backups}"
WARN_PERCENT="${UT_DISK_WARN_PERCENT:-85}"
BACKUP_MAX_AGE_DAYS="${UT_BACKUP_MAX_AGE_DAYS:-2}"

problems=()

# --- Plattenplatz ---
used=$(df --output=pcent / | tail -1 | tr -dc '0-9')
if [ -n "$used" ] && [ "$used" -ge "$WARN_PERCENT" ]; then
	problems+=("Plattenplatz auf / bei ${used}% (Grenze ${WARN_PERCENT}%)")
fi

# --- SMART ---
if command -v smartctl >/dev/null 2>&1; then
	for disk in /dev/sd? /dev/nvme?n1; do
		[ -b "$disk" ] || continue
		health=$(smartctl -H "$disk" 2>/dev/null | grep -iE "SMART overall-health|SMART Health Status" | head -1)
		case "$health" in
		*PASSED*|*OK*) ;;
		"") ;;
		*) problems+=("SMART $disk: ${health#*: }") ;;
		esac
	done
fi

# --- letzte Sicherung ---
newest=$(find "$BACKUP_DIR" -name '*.sql.gz' -o -name '*.tgz' 2>/dev/null | head -1)
if [ -z "$newest" ]; then
	problems+=("Keine Sicherung in $BACKUP_DIR gefunden")
else
	age_days=$((($(date +%s) - $(stat -c %Y "$(find "$BACKUP_DIR" -name '*.sql.gz' -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)" 2>/dev/null || echo 0)) / 86400))
	if [ "$age_days" -ge "$BACKUP_MAX_AGE_DAYS" ]; then
		problems+=("Letzte Sicherung ist $age_days Tage alt (Grenze ${BACKUP_MAX_AGE_DAYS})")
	fi
fi

# --- Container des Tracker-Stacks ---
if command -v docker >/dev/null 2>&1; then
	while read -r name state; do
		[ -n "$name" ] || continue
		[ "$state" = "running" ] || problems+=("Container $name ist nicht running ($state)")
	done < <(docker ps -a --filter 'name=ultimatetracker_' --format '{{.Names}} {{.State}}')
fi

if [ "${#problems[@]}" -eq 0 ]; then
	exit 0
fi

body=$(printf ' • %s\n' "${problems[@]}")
"$ALERT" "manucloud: Betriebscheck" "$body" 4
echo "[check] ${#problems[@]} Problem(e) gemeldet"
