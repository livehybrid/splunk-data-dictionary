# Redeploy - Data Dictionary MCP tool fix

This document gives the **exact** steps to apply the Round-2 fix for the two
broken MCP tools (`data_dictionary_query`, `data_dictionary_index_metadata`) to a
running Splunk instance, plus a verification MCP call.

> **DO NOT run this blindly against the shared lab instance `192.168.0.222`.**
> Other agents use it. Coordinate first. The steps below are written for whoever
> owns the maintenance window.

## What changed and why

The two failing tools returned `Forbidden command found: rest` (and a parse error)
when called via the Splunk MCP Server. Root cause: their **MCP execution
templates** in `appserver/static/tool_input_payload_signatures.json` ran
`| rest splunk_server=local /servicesNS/...` SPL. The Splunk MCP search sandbox
**forbids the `rest` command**, so the search was rejected before it reached the
app's REST handler. (`data_dictionary_ping` happened to work only intermittently
for the same reason.)

The fix replaces the `| rest`-based templates with **pure SPL** that reads the
catalog lookup and overlays KV governance metadata:

- `| inputlookup data_dictionary_catalog` for the 296 catalog rows.
- `| lookup data_dictionary_metadata _key OUTPUT ...` (row, index, sourcetype
  overlays) for governance metadata.

Supporting change: a new **KV-store lookup definition** `data_dictionary_metadata`
(over the existing `[metadata]` collection) was added to
`default/transforms.conf` so the `| lookup` works without `| rest`.

Files changed (relative to the app root `$SPLUNK_HOME/etc/apps/data_dictionary_for_splunk`):

| File | Change |
|------|--------|
| `appserver/static/tool_input_payload_signatures.json` | `| rest` templates → `| inputlookup` + `| lookup` SPL |
| `default/transforms.conf` | add `[data_dictionary_metadata]` kvstore lookup |

The Python REST handlers in `bin/` are **unchanged** - they already used KV REST
(`splunk.rest.simpleRequest`) and never used `| rest` SPL. Only the MCP execution
templates and the lookup definition needed fixing.

## Step 1 - back up the current files

```bash
APP=/opt/splunk/etc/apps/data_dictionary_for_splunk
sudo -u splunk cp "$APP/appserver/static/tool_input_payload_signatures.json" \
  "$APP/appserver/static/tool_input_payload_signatures.json.bak.$(date +%s)"
sudo -u splunk cp "$APP/default/transforms.conf" \
  "$APP/default/transforms.conf.bak.$(date +%s)"
```

## Step 2 - copy the fixed files from this repo

Run from the repo root (`splunk-data-dictionary/`):

```bash
APP=/opt/splunk/etc/apps/data_dictionary_for_splunk
sudo -u splunk cp app/appserver/static/tool_input_payload_signatures.json \
  "$APP/appserver/static/tool_input_payload_signatures.json"
sudo -u splunk cp app/default/transforms.conf "$APP/default/transforms.conf"
```

If you cannot `sudo -u splunk`, add this sudoers line (skill guidance) first:

```
aios ALL=(splunk) NOPASSWD: /bin/cp
```

## Step 3 - reload (preferred) or restart

`transforms.conf` and the static MCP signature JSON can be picked up **without a
full restart**:

```bash
# Reload the app's conf (transforms, tools registration):
curl -sk -u admin:<password> \
  https://127.0.0.1:8089/servicesNS/nobody/data_dictionary_for_splunk/admin/transforms-lookup/_reload
curl -sk -u admin:<password> \
  https://127.0.0.1:8089/services/apps/local/data_dictionary_for_splunk/_reload

# Tell the MCP server to re-read tool signatures (it caches them). If the MCP
# server does not hot-reload signatures, bounce only the MCP app/server process,
# NOT all of splunkd. As a last resort:
#   sudo systemctl restart splunkd
```

> The static `tool_input_payload_signatures.json` is read by the Splunk MCP
> Server. If a `_reload` does not refresh the tool templates, the MCP server
> needs to re-read the file (restart of the MCP server component). Avoid a full
> `splunkd` restart on the shared box unless coordinated.

## Step 4 - verify via MCP

Use the working MCP recipe (token in `/opt/aios/.hackathon-secrets.env`):

```bash
set -a; . /opt/aios/.hackathon-secrets.env; set +a
mcp(){ curl -sk --max-time 60 -X POST "$SPLUNK_MCP_URL" \
  -H "Authorization: Bearer $SPLUNK_TOKEN" -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" -d "$1" | sed 's/^data: //'; }

# Was: "Forbidden command found: rest" - should now return rows:
mcp '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"data_dictionary_index_metadata","arguments":{"index":"pihole"}}}'

# Was: rest parse error - should now return up to `limit` rows:
mcp '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"data_dictionary_query","arguments":{"q":"dns","limit":20}}}'

# Health: should return ok=true plus catalog_rows (e.g. 296):
mcp '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"data_dictionary_ping","arguments":{}}}'
```

**Pass criteria:** none of the three returns `"Forbidden command found: rest"` or a
`rest` parse error; `data_dictionary_index_metadata` returns pihole sourcetype
rows; `data_dictionary_ping` returns `catalog_rows >= 1`.

## Rollback

```bash
APP=/opt/splunk/etc/apps/data_dictionary_for_splunk
sudo -u splunk cp "$APP/appserver/static/tool_input_payload_signatures.json.bak.<ts>" \
  "$APP/appserver/static/tool_input_payload_signatures.json"
sudo -u splunk cp "$APP/default/transforms.conf.bak.<ts>" "$APP/default/transforms.conf"
# then _reload as in Step 3.
```


---

## RESOLVED 2026-06-10 - actual root cause and fix applied

The file-copy + `_reload` approach above was **not sufficient**: the Splunk MCP
Server does not read `tool_input_payload_signatures.json` at call time. Tools
live in the **KV Store** (`Splunk_MCP_Server/mcp_tools` collection), registered
once; the static file is only the registration source. Two further bugs were
found and fixed when re-registering:

1. **Argument quoting.** MCP Server 1.2.0 JSON-quotes string arguments before
   template substitution (`$q$` → `"dns"`, quotes included). Templates must NOT
   add their own quotes: `| search index=$index$`, `lower($q$)`. The previous
   templates produced `index=""pihole""` (0 rows) and `lower(""dns"")` (parse
   error).
2. **Defaults bypass quoting** - optional string args need pre-quoted defaults
   (`"default": "\"\""` in inputSchema) so the template stays valid when the
   arg is omitted. `limit` defaults to 50.
3. **SPL tools must not carry API execution fields** (`method`/`endpoint`/...)
   - the loader rejects the tool outright ("SPL tools cannot define API
   execution fields"), which silently removes it from tools/list. A PUT to
   `/services/mcp_tools` MERGES `_meta.execution`, so updating an old API-shaped
   doc leaves stale fields behind: replace the whole KV doc instead.

Fix applied live by full KV-doc replace per tool (admin REST →
`storage/collections/data/mcp_tools/<tool_id>`), preserving the stored
`_meta.external_app_id` (immutable, required by the loader). All three
verification calls below now pass: index_metadata returns pihole rows, query
matches "dns", ping reports catalog_rows=296. The signature JSON in this repo
now contains the corrected quote-aware templates, so future registrations are
correct from the file.
