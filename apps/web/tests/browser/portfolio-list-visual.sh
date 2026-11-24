#!/usr/bin/env bash
set -euo pipefail

if [[ ${E2E_DISPOSABLE_STACK:-} != 1 ]]; then
  echo 'Set E2E_DISPOSABLE_STACK=1 for the disposable local stack.' >&2
  exit 1
fi

version=$(node -p 'require("./package-lock.json").packages["node_modules/playwright"].version')
image="portfolio-list-chromium:$version"
docker build --network host --platform linux/amd64 --build-arg "PLAYWRIGHT_VERSION=$version" \
  --tag "$image" - < tests/browser/portfolio-list.Dockerfile
container=$(docker run --platform linux/amd64 --detach --rm --init --ipc=host \
  --publish 127.0.0.1::3000 "$image")
trap 'docker stop "$container" >/dev/null' EXIT
address=$(docker port "$container" 3000/tcp)
for ((attempt = 0; attempt < 30; attempt++)); do
  if curl --silent --fail --max-time 2 "http://$address/" >/dev/null; then
    break
  fi
  sleep 1
done
curl --silent --show-error --fail --max-time 2 "http://$address/" >/dev/null

PW_TEST_CONNECT_WS_ENDPOINT="ws://$address/" PW_TEST_CONNECT_EXPOSE_NETWORK='<loopback>' \
  npx --no-install playwright test portfolio-list.e2e.ts "$@"
