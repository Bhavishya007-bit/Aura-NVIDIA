#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
docker compose --env-file .env.judge -f compose.yaml --profile vision down
printf '%s\n' 'Aura stopped. Your local plans, study materials and account are preserved.'
