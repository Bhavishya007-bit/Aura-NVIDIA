#!/bin/sh
set -eu
dockerd-entrypoint.sh --host=unix:///var/run/docker.sock --host=tcp://0.0.0.0:2375 --tls=false &
daemon=$!
trap 'kill "$daemon" 2>/dev/null || true' INT TERM EXIT
export DOCKER_HOST=unix:///var/run/docker.sock
attempt=0
until docker info >/dev/null 2>&1; do
  kill -0 "$daemon" 2>/dev/null || exit 1
  attempt=$((attempt + 1))
  [ "$attempt" -lt 90 ] || exit 1
  sleep 1
done
docker build -t aura-code:1 /opt/aura-code
touch /tmp/aura-code-ready
wait "$daemon"
