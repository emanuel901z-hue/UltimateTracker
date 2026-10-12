#!/usr/bin/env bash
# Startet eine zweite, unabhängige Instanz des Stacks (Projekt "uttest") mit
# verschobenen Ports – zum Ausprobieren, ohne die laufende Instanz anzufassen.
#
# Aufruf (in der WSL):   bash scripts/start-test-instance.sh [--profile …] [dienst …]
# Beispiel:              bash scripts/start-test-instance.sh            # Kern-Stack
#                        bash scripts/start-test-instance.sh --profile tls
# Stoppen:               docker compose -p uttest down
# Logs:                  docker compose -p uttest logs -f audio-bridge
#
# Hinweis: Es wird dieselbe server/.env verwendet (gleiche Tokens). Die Datenbank
# startet leer – Traccar legt beim ersten Start einen neuen Admin an (der erste
# registrierte Benutzer wird Administrator).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/server"

PROJECT="${UT_TEST_PROJECT:-uttest}"

docker compose -p "$PROJECT" -f docker-compose.yml -f docker-compose.test.yml up -d "$@"

cat <<INFO

Test-Instanz läuft (Projekt: $PROJECT)
  Eltern-UI/API:  http://localhost:9085
  Traccar:        http://localhost:9082
  (optional, --profile tls)   HTTPS: https://localhost:8443
  (optional, --profile findmy) Anisette 7969, macless 7176, Google-WebUI 5321

Stoppen:  docker compose -p $PROJECT down
Logs:     docker compose -p $PROJECT logs -f audio-bridge
INFO
