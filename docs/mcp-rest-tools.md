# MCP tools: SPL, `| rest`, and the REST-API execution type

> **Status: implemented.** The conclusion below (use the `api` execution type
> rather than `| rest`) was adopted - `data_dictionary_query` and
> `data_dictionary_index_metadata` now run as API tools proxying the app's REST
> handlers. See [`MCP-TOOLS.md`](./MCP-TOOLS.md) for the live tool reference and
> `deploy/register_mcp_tools.py` for registration. This doc is kept as the
> rationale / investigation record.

Findings from the live Splunk MCP Server (`Splunk_MCP_Server` app), to settle how
our tools should access data. Verified against the server's own `tool_manager.py`,
`splunk_api.py` and `default/safe_spl.json`, plus a live call.

## Can a tool use `| rest`? Yes - with a caveat

It is **blocked by default**, but it is **not absolutely forbidden**.

- Every SPL tool's query is checked against `safe_spl.json` → `safe_spl_commands`
  (143 commands). **`rest` is not in that list**, so a tool whose SPL contains
  `| rest` is rejected with `Forbidden command found: rest`. Verified live:
  `splunk_run_query("| rest /services/server/info …")` → `400 Forbidden command
  found: rest`.
- **But** the safety check is skipped for any tool whose name is in
  `safe_spl.json` → `exclude_tools` (`settings.safe_spl_exclude_tools`). The
  built-in `splunk_get_*` and `saia_*` tools are on that list. So **a registered
  SPL tool _can_ run `| rest` if its name is added to `exclude_tools`** on the MCP
  server.

So the developers are right that `| rest` can work - it just requires a
**server-admin change** to the MCP server's `safe_spl.json` (adding our tool name
to `exclude_tools`), which couples our tool to that server's configuration.

### Sample - a `| rest` SPL tool (requires the exclude entry)

```jsonc
{
  "name": "data_dictionary_rest_search",
  "description": "…",
  "inputSchema": { "type": "object", "properties": {}, "required": [] },
  "_meta": {
    "execution": {
      "type": "spl",
      "template": "| rest /services/data/indexes | fields title, frozenTimePeriodInSecs",
      "guardrails": false
    },
    "external_app_id": "data_dictionary"
  }
}
```
> Won't run until `data_dictionary_rest_search` is in the MCP server's
> `safe_spl.json` `exclude_tools`.

## The cleaner option: the **`api` execution type**

`tool_manager.py` supports two execution types: `spl` **and `api`**. An `api` tool
calls a Splunk REST endpoint **directly** (via `call_splunk_api` with the caller's
session key) - no SPL, so the `| rest` guardrail never applies. This is the proper
"run a REST API call as a tool" mechanism, and it's what the `saia_*` tools use.

Schema (`_meta.execution`): `type: "api"`, `method`, `endpoint`, optional
`headers`, `params`, `body`.

### Sample - back a DD tool with our own REST handler (recommended)

This calls the app's existing `dictionary/query` REST handler instead of running
SPL - useful when we want richer server-side logic (merging, RBAC, future
write-back) than a lookup query can express:

```jsonc
{
  "name": "data_dictionary_query_rest",
  "description": "Search the Data Dictionary for data + governance/ownership by keyword (REST-backed).",
  "inputSchema": {
    "type": "object",
    "properties": {
      "q": { "type": "string", "description": "Keyword across index, sourcetype and governance fields." }
    },
    "required": []
  },
  "_meta": {
    "execution": {
      "type": "api",
      "method": "GET",
      "endpoint": "/servicesNS/nobody/data_dictionary/data_dictionary/dictionary/query",
      "params": { "q": "$q$", "output_mode": "json" }
    },
    "external_app_id": "data_dictionary"
  }
}
```

## Recommendation

- For **read** tools that need data the lookups already hold → keep **SPL**
  (`inputlookup` + `lookup`); it's self-contained, needs no server config, and is
  what ships today.
- For tools that need **REST behaviour** (calling `/services/...`, or our own REST
  handlers for logic the lookup can't express - e.g. the future **write-back**
  tool, or RBAC-aware reads) → use the **`api` execution type**. It avoids the
  `| rest` guardrail entirely and runs with the caller's session/RBAC.
- Only use `| rest` in SPL if you specifically need to combine REST output with
  other SPL in one search **and** you can get the tool added to the server's
  `exclude_tools`.
