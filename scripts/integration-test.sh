#!/usr/bin/env bash
# Full local integration run, end to end:
#   build the app -> boot Splunk in Docker -> install + configure the Splunk MCP
#   Server and register the Data Dictionary tools -> run the live pytest
#   (REST + RBAC + MCP protocol) and the Playwright UI suite (rendering, RBAC,
#   custom fields) -> tear down.
#
#   scripts/integration-test.sh
#
# The MCP Server app is third-party; supply it via MCP_SERVER_TARBALL
# (default vendor/Splunk_MCP_Server.tgz). Without it, the MCP-server install and
# the MCP-protocol tests are skipped; everything else still runs.
#
# Env (all optional):
#   WEB_PORT (8000) MGMT_PORT (8089)  host ports — override to avoid clashing with
#                                     a host Splunk, e.g. WEB_PORT=18000 MGMT_PORT=18089
#   SPLUNK_PASSWORD (Changeme1!)      container admin password
#   KEEP=1                            leave the container running after the tests
#   SKIP_BUILD=1                      reuse an existing stage/ build
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export WEB_PORT="${WEB_PORT:-8000}"
export MGMT_PORT="${MGMT_PORT:-8089}"
export SPLUNK_PASSWORD="${SPLUNK_PASSWORD:-Changeme1!}"
export CONTAINER="${CONTAINER:-dd_integration_splunk}"
KEEP="${KEEP:-0}"
MCP_TOKEN_FILE="$ROOT/.tmp/integration-mcp-token"
export MCP_TOKEN_FILE

step() { echo; echo "=========== $* ==========="; }

cleanup() {
    if [ "$KEEP" = "1" ]; then
        echo "KEEP=1 — leaving $CONTAINER running (web http://127.0.0.1:$WEB_PORT, mgmt https://127.0.0.1:$MGMT_PORT)."
    else
        scripts/splunk-docker.sh down || true
    fi
}
trap cleanup EXIT

if [ "${SKIP_BUILD:-0}" != "1" ] || [ ! -f stage/appserver/static/pages/home.js ]; then
    step "Build app (ucc-gen + webpack)"
    npm run build
fi

step "Boot Splunk + install the Data Dictionary app"
scripts/splunk-docker.sh up

step "Install + configure the Splunk MCP Server and register tools"
scripts/integration-mcp.sh || echo "(MCP setup skipped or failed — continuing without MCP-protocol tests)"

step "Live pytest: REST handlers + RBAC + MCP protocol"
SPLUNK_MGMT_URL="https://127.0.0.1:$MGMT_PORT" \
SPLUNK_MCP_URL="https://127.0.0.1:$MGMT_PORT/services/mcp" \
SPLUNK_USER=admin SPLUNK_PASSWORD="$SPLUNK_PASSWORD" \
MCP_TOKEN_FILE="$MCP_TOKEN_FILE" \
    python3 -m pytest tests/test_mcp_live.py -v

step "Playwright UI suite: rendering + RBAC + custom fields"
SPLUNK_WEB_URL="http://127.0.0.1:$WEB_PORT" \
SPLUNK_MGMT_URL="https://127.0.0.1:$MGMT_PORT" \
SPLUNK_USER=admin SPLUNK_PASSWORD="$SPLUNK_PASSWORD" \
    npm run test:integration

step "Done"
echo "Integration run complete."
