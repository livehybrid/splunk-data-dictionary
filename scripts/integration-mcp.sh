#!/usr/bin/env bash
# Install + configure the Splunk MCP Server in a running integration container,
# then register the Data Dictionary's MCP tools into it.
#
#   scripts/integration-mcp.sh
#
# The MCP Server app is third-party (Splunkbase) so it is NOT committed. Supply it
# as a tarball via MCP_SERVER_TARBALL (default vendor/Splunk_MCP_Server.tgz). If the
# tarball is absent the script prints SKIP and exits 0 — the rest of the harness
# (app install, REST, RBAC, custom-field tests) still runs without it.
#
# On success it writes an mcp-audience admin token to MCP_TOKEN_FILE so the live
# MCP tests can call the server.
#
# Env:
#   CONTAINER         container name           (default dd_integration_splunk)
#   MGMT_PORT         host port -> 8089        (default 8089)
#   SPLUNK_PASSWORD   admin password           (default Changeme1!)
#   MCP_SERVER_TARBALL  path to the app tgz    (default vendor/Splunk_MCP_Server.tgz)
#   MCP_TOKEN_FILE    where to write the token (default .tmp/integration-mcp-token)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER="${CONTAINER:-dd_integration_splunk}"
WEB_PORT="${WEB_PORT:-8000}"
MGMT_PORT="${MGMT_PORT:-8089}"
PW="${SPLUNK_PASSWORD:-Changeme1!}"
TARBALL="${MCP_SERVER_TARBALL:-$ROOT/vendor/Splunk_MCP_Server.tgz}"
MCP_TOKEN_FILE="${MCP_TOKEN_FILE:-$ROOT/.tmp/integration-mcp-token}"
MGMT="https://127.0.0.1:${MGMT_PORT}"

say() { echo "[integration-mcp] $*"; }

if [ ! -f "$TARBALL" ]; then
    say "SKIP: no MCP Server tarball at $TARBALL (set MCP_SERVER_TARBALL to enable MCP tests)."
    exit 0
fi

say "Installing MCP Server from $TARBALL into $CONTAINER ..."
docker cp "$TARBALL" "$CONTAINER:/tmp/mcp_server.tgz"
# Extract as root: the default exec user can't create dirs under /opt/splunk/etc/apps.
docker exec -u root "$CONTAINER" tar xzf /tmp/mcp_server.tgz -C /opt/splunk/etc/apps
# Files in the tarball carry the source host's uid; normalise to the container's splunk user.
docker exec -u root "$CONTAINER" chown -R splunk:splunk /opt/splunk/etc/apps/Splunk_MCP_Server

say "Restarting Splunk to load the MCP Server app ..."
# Restart the whole container rather than 'splunk restart' via docker exec: the
# container's entrypoint owns splunkd, so an out-of-band exec restart races it and
# can leave splunkd down on a fresh boot (the in-container restart needs the splunk
# user, and even then it is fragile). A container restart re-runs the entrypoint
# cleanly and re-maps the published ports; the extracted app persists in the
# writable layer. -t 60 gives splunkd time to stop gracefully before SIGKILL.
docker restart -t 60 "$CONTAINER" >/dev/null

say "Waiting for Splunk Web after restart ..."
WEB_PORT="$WEB_PORT" MGMT_PORT="$MGMT_PORT" CONTAINER="$CONTAINER" \
    bash "$ROOT/scripts/splunk-docker.sh" wait

say "Waiting for management API on $MGMT ..."
for i in $(seq 1 50); do
    code=$(curl -sk -o /dev/null -w '%{http_code}' -u "admin:$PW" "$MGMT/services/server/info?output_mode=json" || true)
    [ "$code" = "200" ] && { say "Management API up after ~$((i * 6))s."; break; }
    [ "$i" = "50" ] && { say "ERROR: timed out waiting for the management API."; exit 1; }
    sleep 6
done

say "Enabling token authentication ..."
curl -sk -u "admin:$PW" -X POST "$MGMT/services/admin/token-auth/tokens_auth" \
    -d disabled=false -o /dev/null -w '  tokens_auth HTTP %{http_code}\n' || true

say "Verifying MCP Server endpoint is registered ..."
mcp_ok=$(curl -sk -o /dev/null -w '%{http_code}' -u "admin:$PW" "$MGMT/services/mcp" || true)
say "  /services/mcp -> HTTP $mcp_ok (401/405/200 = present)"

say "Registering Data Dictionary tools into the MCP Server ..."
SPLUNK_HOST=127.0.0.1 SPLUNK_PORT="$MGMT_PORT" SPLUNK_PASSWORD="$PW" \
    python3 "$ROOT/deploy/register_mcp_tools.py"

say "Minting an mcp-audience admin token ..."
mkdir -p "$(dirname "$MCP_TOKEN_FILE")"
token=$(curl -sk -u "admin:$PW" -X POST "$MGMT/services/authorization/tokens?output_mode=json" \
    -d name=admin -d audience=mcp \
    | python3 -c "import sys,json; e=json.load(sys.stdin).get('entry') or []; print(e[0]['content'].get('token','') if e else '')")
if [ -n "$token" ]; then
    printf '%s' "$token" > "$MCP_TOKEN_FILE"
    say "Token written to $MCP_TOKEN_FILE (len ${#token})."
else
    say "WARNING: could not mint an mcp token; live MCP-protocol tests will skip."
fi

say "MCP Server setup complete."
