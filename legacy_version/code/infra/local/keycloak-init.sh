#!/bin/bash
set -euo pipefail
# A disposable one-shot process owns schema migration and first realm import.
# The public Keycloak container only receives the runtime database credential.
/opt/keycloak/bin/kc.sh start-dev --import-realm &
keycloak_pid=$!
trap 'kill -TERM "$keycloak_pid" 2>/dev/null || true' EXIT
for attempt in {1..120}; do
  if ! kill -0 "$keycloak_pid" 2>/dev/null; then
    wait "$keycloak_pid"
    exit 1
  fi
  if (exec 3<>/dev/tcp/127.0.0.1/9000; printf 'GET /health/ready HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n' >&3; read -r status <&3; [[ "$status" == *"200 OK"* ]]) 2>/dev/null; then
    kill -TERM "$keycloak_pid"
    wait "$keycloak_pid" || true
    trap - EXIT
    echo 'Identity schema migration and realm import completed.'
    exit 0
  fi
  sleep 2
done
echo 'Identity initialization did not become ready.' >&2
exit 1
