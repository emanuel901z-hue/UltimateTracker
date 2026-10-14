#!/usr/bin/env bash
# Wird von smartd über `-M exec` aufgerufen, wenn eine Platte auffällig wird.
# Argumente von smartd: Gerät, Status, Meldung (werden mitgeschickt).
#
# Einrichten (siehe docs/operations-manucloud.md):
#   /etc/smartd.conf:  DEVICESCAN -a -o on -S on -M exec /usr/local/bin/ut-smart-alert.sh

set -u
HERE=$(cd "$(dirname "$0")" && pwd)
exec "$HERE/ut-alert.sh" "manucloud: SMART-Warnung" "Festplatte meldet ein Problem: $*" 4
