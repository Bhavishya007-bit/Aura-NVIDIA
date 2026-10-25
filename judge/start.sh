#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
docker info --format '{{.OSType}}'
docker compose version
fresh=false
if [[ ! -s .env.judge ]]; then
  (umask 077; touch .env.judge)
  fresh=true
fi
cleanup() {
  if [[ "$fresh" == true && -e .env.judge && ! -s .env.judge ]]; then rm -- .env.judge; fi
}
trap cleanup EXIT
compose=(docker compose --env-file .env.judge -f compose.yaml)
printf '%s\n' 'Building Aura. The first build downloads dependencies and may take several minutes.'
"${compose[@]}" build app
if [[ "$fresh" == true ]]; then
  rm -- .env.judge
  options=()
  if [[ "${1:-}" == '--vision' ]]; then options+=(--vision); fi
  docker compose -f compose.yaml run --rm --no-deps --user "$(id -u):$(id -g)" \
    -v "$PWD:/config" app python scripts/configure_judge.py "${options[@]}"
fi
if grep -q "^AURA_JUDGE_VISION_MODEL='gemma3:4b'$" .env.judge; then
  "${compose[@]}" --profile vision up -d vision
  "${compose[@]}" exec -T vision ollama pull gemma3:4b
fi
"${compose[@]}" up -d --wait --wait-timeout 240 db app
"${compose[@]}" run --rm --no-deps --user "$(id -u):$(id -g)" -v "$PWD:/config" \
  app python scripts/configure_judge.py --show-login
printf '%s\n' 'Open http://localhost:8888 in your browser.'
