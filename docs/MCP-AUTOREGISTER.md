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

## The tool name the server advertises is not always the one you registered

The MCP Server prefixes every tool name on load (`Tool._convert_from_new_schema`):
`_meta.name_prefix`, falling back to `_meta.external_app_id`, is prepended unless the
name already starts with it. `tools/list` publishes that prefixed name. `tools/call`
then looks the tool up by `_key` in `mcp_tools_enabled`.

So if you enable under the bare `name`, the two disagree and **every call fails** with
the name the server itself just advertised:

```
Tool 'data_dictionary_for_splunk_data_dictionary_ping' not found   (-32004)
```

Two halves to keeping them in sync, and this app does both:

- Each tool carries `"name_prefix": "data_dictionary"` in `_meta`. Our names already
  start with `data_dictionary_`, so the server uses them verbatim - short names, no
  `data_dictionary_for_splunk_` stutter.
- `autoregister.py` (and `deploy/register_mcp_tools.py`) derive the enabled `_key` with
  `mcp_name()`, which mirrors the server's rule, so the key is right even if a future
  tool name doesn't match the prefix.

`tests/test_tool_signatures.py::test_advertised_name_matches_registered_name` fails the
build if the two ever drift apart again.

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
