#!/usr/bin/env bash
# Spiegelt das Repo aus dem Windows-Dateisystem in die WSL-Distro.
#
# Aufruf (innerhalb der Distro "UltimateTracker"):
#   bash /mnt/d/Projekte/UltimateTracker/scripts/sync-to-wsl.sh
#
# Hinweis: server/.env wird nicht überschrieben (Tokens bleiben lokal erhalten).

set -euo pipefail

SRC="${SRC:-/mnt/d/Projekte/UltimateTracker}"
DST="${DST:-$HOME/UltimateTracker}"

if [[ ! -d "$SRC" ]]; then
  echo "Quelle nicht gefunden: $SRC" >&2
  exit 1
fi

mkdir -p "$DST"
rsync -a --delete \
  --exclude '.git/' \
  --exclude '.pio/' \
  --exclude '__pycache__/' \
  --exclude 'server/.env' \
  "$SRC/" "$DST/"

echo "Synchronisiert: $SRC -> $DST"
