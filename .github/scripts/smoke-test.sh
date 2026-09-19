#!/usr/bin/env bash
# Boot an image against an empty data dir and require /health to answer.
# A green build says nothing about startup: import-time crashes and broken
# migrations only show up here.
# Usage: smoke-test.sh <image> [host-port]
set -u
IMAGE="$1"
PORT="${2:-8080}"
NAME="owui-smoke-$$"

docker run -d --name "$NAME" -p "127.0.0.1:$PORT:8080" -e WEBUI_AUTH=false "$IMAGE" >/dev/null || exit 1
trap 'docker rm -f "$NAME" >/dev/null 2>&1' EXIT

for i in $(seq 1 60); do
	code=$(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/health")
	if [ "$code" = 200 ]; then
		config=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/api/config")
		echo "healthy after ~$((i * 5))s, /api/config=$config, version=$(curl -s -m 5 "http://127.0.0.1:$PORT/api/version")"
		[ "$config" = 200 ] && exit 0
		break
	fi
	[ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" = true ] || break
	sleep 5
done

echo "smoke test FAILED for $IMAGE; container log tail:"
docker logs "$NAME" 2>&1 | tail -60
exit 1
