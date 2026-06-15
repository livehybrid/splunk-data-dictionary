# MCP tool auto-registration

Short version: install the app and the MCP tools show up. You don't run anything.
Here's how, and why it's built this way.

## Cloud does it for us

On Splunk Cloud there's a synced-apps registrar that reads an app's `tools.conf` on
install and registers each tool with the MCP Server. That's the whole story on Cloud:
ship `default/tools.conf` (every tool needs an `endpoint_name`) plus the source of
truth in `appserver/static/tool_input_payload_signatures.json`, and you're done. No app
code runs.

## Enterprise has to register itself

On-prem there's no synced-apps registrar, and older MCP Server builds don't even expose
a `tool_registration` endpoint, so nothing is going to register us. The app does it
itself, in `bin/autoregister.py`. `app.conf` wires it up:

```
[triggers]
reload.tools = http_post /data_dictionary/autoregister
```

splunkd POSTs to that endpoint on every app state change (install / enable / upgrade).
The handler reads `server/info` `instance_type`:

- `cloud` -> no-op, the platform already did it.
- anything else (Enterprise reports `None`) -> upsert the tool defs from the signatures
  file straight into the MCP Server's `mcp_tools` + `mcp_tools_enabled` KV collections.

It's idempotent (full-doc replace by `_key`) and runs under `passSystemAuth`, so it
already has the system session key - nobody has to log in or run a script.

## Things that cost me time, so they don't cost it again

- Use `http_post`, not `access_endpoints`. `access_endpoints` calls a `_reload()` method;
  a persistent REST handler only has `handle()`. `http_post` does a real POST it answers.
- Drop the `/services` prefix in the trigger URL. Splunk's own `[triggers]` reference
  endpoints that way (`reload.indexes = access_endpoints /data/indexes`), so it's
  `/data_dictionary/autoregister`, not `/services/data_dictionary/autoregister`.
- `in_string` into `handle()` is bytes. `json.loads` takes it; don't slice it as a str.
- `splunk.rest.simpleRequest` raises on 4xx even with `raiseAllErrors=False`, so the
  upsert tries update-by-key then falls back to insert inside a try/except.

`deploy/register_mcp_tools.py` is still around as a manual one-shot if you ever want to
register out of band, but you shouldn't need it.
