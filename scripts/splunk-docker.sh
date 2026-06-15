#!/usr/bin/env bash
# Orchestrate a throwaway Splunk container with the built app installed, for live
# integration tests. Used by the integration CI job and locally.
#
#   scripts/splunk-docker.sh up     # build (if needed) + start Splunk + wait ready
#   scripts/splunk-docker.sh wait   # block until Splunk Web answers
#   scripts/splunk-docker.sh logs   # dump container logs (for CI debugging)
#   scripts/splunk-docker.sh down   # stop + remove the container
#
# Env:
#   SPLUNK_IMAGE     (default splunk/splunk:10.0)
#   SPLUNK_PASSWORD  (default Changeme1!)
#   WEB_PORT         host port -> 8000 (default 8000)
#   MGMT_PORT        host port -> 8089 (default 8089)
#   CONTAINER        container name (default dd_integration_splunk)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPLUNK_IMAGE="${SPLUNK_IMAGE:-splunk/splunk:10.0}"
SPLUNK_PASSWORD="${SPLUNK_PASSWORD:-Changeme1!}"
WEB_PORT="${WEB_PORT:-8000}"
MGMT_PORT="${MGMT_PORT:-8089}"
CONTAINER="${CONTAINER:-dd_integration_splunk}"

wait_ready() {
    # First boot (ansible + KV store init) can take 5+ min, especially on slower
    # CI runners — locally it's ~285s, so allow generous headroom (~10 min).
    echo "Waiting for Splunk Web on http://127.0.0.1:${WEB_PORT} (up to ~10 min)..."
    for i in $(seq 1 100); do
        code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${WEB_PORT}/en-US/account/login" || true)
        if echo "$code" | grep -qE '200|301|302|303'; then
            echo "Splunk Web is up (HTTP $code) after ~$((i * 6))s."
            return 0
        fi
        if ! docker ps --filter "name=${CONTAINER}" --filter status=running -q | grep -q .; then
            echo "ERROR: Splunk container exited during boot." >&2
            docker logs --tail 80 "$CONTAINER" >&2 || true
            return 1
        fi
        sleep 6
    done
    echo "ERROR: timed out waiting for Splunk Web." >&2
    docker logs --tail 80 "$CONTAINER" >&2 || true
    return 1
}

case "${1:-}" in
    up)
        if [ ! -f "$ROOT/stage/appserver/static/pages/home.js" ]; then
            echo "ERROR: stage/ not built. Run 'npm run build' first." >&2
            exit 1
        fi
        docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
        echo "Starting $SPLUNK_IMAGE as $CONTAINER (web ${WEB_PORT}, mgmt ${MGMT_PORT})..."
        docker run -d --name "$CONTAINER" \
            -p "${WEB_PORT}:8000" -p "${MGMT_PORT}:8089" \
            -e SPLUNK_START_ARGS=--accept-license \
            -e SPLUNK_GENERAL_TERMS=--accept-sgt-current-at-splunk-com \
            -e SPLUNK_PASSWORD="$SPLUNK_PASSWORD" \
            -v "$ROOT/stage:/opt/splunk/etc/apps/data_dictionary" \
            "$SPLUNK_IMAGE" >/dev/null
        wait_ready
        ;;
    wait)
        wait_ready
        ;;
    logs)
        docker logs --tail "${2:-120}" "$CONTAINER" || true
        ;;
    down)
        docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
        echo "Removed $CONTAINER."
        ;;
    *)
        echo "Usage: $0 {up|wait|logs|down}" >&2
        exit 2
        ;;
esac
