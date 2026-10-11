#!/usr/bin/env bash
# Sichert alle Docker-Volumes des Stacks in ein Zielverzeichnis.
# Aufruf (in der WSL):  bash scripts/backup-volumes.sh [Zielverzeichnis]
#
# Cron-Beispiel (täglich 03:00):
#   0 3 * * * bash "$HOME/UltimateTracker/scripts/backup-volumes.sh" >> "$HOME/UltimateTracker/backups/backup.log" 2>&1
#
# Restore (Beispiel audio-data):
#   docker run --rm -v ultimatetracker_audio-data:/data -v "$PWD":/backup alpine \
#     sh -c "rm -rf /data/* && tar xzf /backup/audio-data-<STAMP>.tgz -C /data"

set -euo pipefail

TARGET="${1:-$HOME/UltimateTracker/backups}"
PROJECT="${PROJECT:-ultimatetracker}"
STAMP="$(date +%Y%m%d-%H%M%S)"
VOLUMES=(audio-data traccar-data google-findmy-data findmy-bridge-data macless-data anisette-data)

mkdir -p "$TARGET"
echo "[backup] Ziel: $TARGET"

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
find "$TARGET" -name '*.tgz' -mtime +30 -print -delete 2>/dev/null || true

echo "[backup] Fertig."
