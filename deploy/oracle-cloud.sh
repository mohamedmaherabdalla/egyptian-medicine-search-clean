#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-egyptian-medicine-algorithm-6}"
CONTAINER_NAME="${CONTAINER_NAME:-medicine-search-a6}"
PUBLIC_PORT="${PUBLIC_PORT:-80}"
MEMORY_LIMIT="${MEMORY_LIMIT:-3g}"

docker build --tag "${IMAGE_NAME}" .

if docker container inspect "${CONTAINER_NAME}" >/dev/null 2>&1; then
  docker container rm --force "${CONTAINER_NAME}"
fi

docker run \
  --detach \
  --name "${CONTAINER_NAME}" \
  --restart unless-stopped \
  --memory "${MEMORY_LIMIT}" \
  --cpus 2 \
  --publish "${PUBLIC_PORT}:7860" \
  --env PORT=7860 \
  "${IMAGE_NAME}"

for attempt in $(seq 1 24); do
  if curl --fail --silent "http://127.0.0.1:${PUBLIC_PORT}/health" >/dev/null; then
    curl --fail --silent "http://127.0.0.1:${PUBLIC_PORT}/api/runtime"
    printf '\nAlgorithm 6 is ready on port %s.\n' "${PUBLIC_PORT}"
    exit 0
  fi
  sleep 5
done

docker logs "${CONTAINER_NAME}"
printf 'Algorithm 6 did not become healthy within 120 seconds.\n' >&2
exit 1
