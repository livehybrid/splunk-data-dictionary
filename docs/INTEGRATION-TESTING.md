# Integration testing harness

End-to-end tests that run against a **real Splunk** with the built app installed -
and, when supplied, the **Splunk MCP Server** - so the REST handlers, RBAC, custom
fields, the React UI, and the actual MCP tools are all exercised together.

Two layers:

| Layer | File(s) | What it proves | Needs |
|-------|---------|----------------|-------|
| Tool-signature invariants | `tests/test_tool_signatures.py` | Static: ping=SPL/no `\| rest`, query/index=API→`/dictionary/*`+`flat=1`, ids aligned | none (runs in unit CI) |
| Live REST + RBAC + MCP | `tests/test_mcp_live.py` | REST handlers answer; RBAC matrix (viewer 403 / editor 200 / reads open); custom field flows through; MCP tools answer over the wire | live Splunk (+ MCP Server for the protocol tests) |
| Live UI | `tests/integration/*.spec.ts` | React bundles render; RBAC badge/banner + hidden controls; Fields page lists standard + custom fields | live Splunk + Playwright |

## One command

```bash
# Build, boot Splunk in Docker, install + configure the MCP Server, register the
# tools, run the live pytest + Playwright suite, tear down:
npm run test:integration:full

# Leave the container up afterwards (inspect the UI), on non-clashing ports:
KEEP=1 WEB_PORT=18000 MGMT_PORT=18089 npm run test:integration:full
```

`scripts/integration-test.sh` orchestrates: `npm run build` →
`scripts/splunk-docker.sh up` → `scripts/integration-mcp.sh` →
`pytest tests/test_mcp_live.py` → `npm run test:integration` → teardown.

## The Splunk MCP Server (third-party)

The MCP Server is a Splunkbase app and is **not committed** (`vendor/` is
git-ignored). Supply it as a tarball to enable the MCP-server install + the
MCP-protocol tests:

```bash
# A tarball whose top-level dir is Splunk_MCP_Server/ (default location):
vendor/Splunk_MCP_Server.tgz
# …or point at one explicitly:
MCP_SERVER_TARBALL=/path/to/Splunk_MCP_Server.tgz npm run test:integration:full
```

`scripts/integration-mcp.sh` then `docker cp`s it into the container, restarts
Splunk, enables token auth, registers the Data Dictionary tools
(`deploy/register_mcp_tools.py`), and mints an `mcp`-audience token to
`.tmp/integration-mcp-token` for the protocol tests. **Without the tarball it
prints SKIP and exits 0** - the REST/RBAC/UI tests still run; only the
MCP-protocol tests skip.

## Running pieces individually

```bash
# Just the live pytest against an already-running Splunk (e.g. a lab box):
SPLUNK_MGMT_URL=https://host:8089 SPLUNK_PASSWORD=*** npm run test:live
# …add the MCP protocol tests:
SPLUNK_MCP_URL=https://host:8089/services/mcp SPLUNK_MCP_TOKEN=<jwt aud=mcp> ... npm run test:live

# Just Playwright against a running Splunk (SPLUNK_MGMT_URL lets global-setup
# provision the RBAC users + a custom field; without it those specs skip):
SPLUNK_WEB_URL=http://host:8000 SPLUNK_MGMT_URL=https://host:8089 \
  SPLUNK_USER=admin SPLUNK_PASSWORD=*** npm run test:integration
```

The live pytest and the Playwright global-setup each create their own throwaway
roles/users (and a custom field) and remove them in teardown, so they leave no
residue on the target instance.

## CI

The `integration` job in `.github/workflows/ci.yml` boots Splunk in Docker,
runs the MCP-setup step (a no-op without the vendored tarball), the live pytest,
and the Playwright suite. The signature-invariant unit test runs in the separate
`python` job with no network.
