#!/usr/bin/env bash
# Sichert den Datenbestand des Stacks in ein Zielverzeichnis:
#   * PostgreSQL-Dump (Traccar: Positionen, Fahrten, Geofences …)
#   * Docker-Volumes (Audio-Nachrichten, Geräte-Registry, Find-My, Zertifikate)
# Aufruf (in der WSL/manucloud):  bash scripts/backup-volumes.sh [Zielverzeichnis]
#
# Cron-Beispiel (täglich 03:00):
#   0 3 * * * bash "$HOME/UltimateTracker/scripts/backup-volumes.sh" >> "$HOME/UltimateTracker/backups/backup.log" 2>&1
#
# Restore (Beispiele):
#   # Datenbank
#   gunzip -c traccar-db-<STAMP>.sql.gz | docker exec -i <postgres-container> psql -U traccar traccar
#   # Volume (z. B. audio-data)
#   docker run --rm -v ultimatetracker_audio-data:/data -v "$PWD":/backup alpine \
#     sh -c "rm -rf /data/* && tar xzf /backup/audio-data-<STAMP>.tgz -C /data"
#
# Hinweis: Die **Positionen liegen in PostgreSQL**, nicht in `traccar-data`
# (dort stehen nur Medien/Anhänge). Deshalb der Dump – ein rohes Kopieren des
# Datenverzeichnisses wäre zudem inkonsistent.

set -euo pipefail

TARGET="${1:-$HOME/UltimateTracker/backups}"
PROJECT="${PROJECT:-ultimatetracker}"
STAMP="$(date +%Y%m%d-%H%M%S)"
VOLUMES=(audio-data traccar-data google-findmy-data findmy-bridge-data macless-data anisette-data)

mkdir -p "$TARGET"
echo "[backup] Ziel: $TARGET"

# --- PostgreSQL (der eigentliche Datenbestand) ---
PG=$(docker ps --filter "name=${PROJECT}_postgres" --format '{{.Names}}' | head -1 || true)
if [ -z "$PG" ]; then
	PG=$(docker ps --filter 'name=postgres' --format '{{.Names}}' | head -1 || true)
fi
if [ -n "$PG" ]; then
	# Im Container verbindet sich pg_dump über den lokalen Socket (trust) –
	# kein Passwort nötig.
	if docker exec "$PG" pg_dump -U "${POSTGRES_USER:-traccar}" traccar \
		| gzip > "$TARGET/traccar-db-${STAMP}.sql.gz"; then
		echo "[backup] gesichert: traccar-db-${STAMP}.sql.gz"
	else
		echo "[backup] WARNUNG: Datenbank-Dump fehlgeschlagen ($PG)" >&2
		rm -f "$TARGET/traccar-db-${STAMP}.sql.gz"
	fi
else
	echo "[backup] übersprungen (kein PostgreSQL-Container): Datenbank"
fi

# --- Volumes ---
for volume in "${VOLUMES[@]}"; do
	name="${PROJECT}_${volume}"
	if ! docker volume inspect "$name" >/dev/null 2>&1; then
		echo "[backup] übersprungen (Volume fehlt): $name"
		continue
	fi
	docker run --rm -v "$name":/data:ro -v "$TARGET":/backup alpine \
		tar czf "/backup/${volume}-${STAMP}.tgz" -C /data . >/dev/null
	echo "[backup] gesichert: ${volume}-${STAMP}.tgz"
done

# Alte Backups aufräumen (Standard: älter als 30 Tage)
find "$TARGET" \( -name '*.tgz' -o -name '*.sql.gz' \) -mtime +30 -print -delete 2>/dev/null || true

echo "[backup] Fertig."
