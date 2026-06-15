# Data Dictionary - MCP Tools

The Data Dictionary app publishes **three tools** on the Splunk MCP Server so any
MCP client - **Splunk's own AI Assistant**, Claude, or any other agent - can query
the governance catalog with live grounding.

This doc covers what each tool does, its input schema, and **real, captured
request/response examples** from the live lab instance.

> All examples below were captured live against the lab instance
> (`data_dictionary_ping` → `catalog_rows: 296`).


## Wire protocol

```
POST https://<host>:8089/services/mcp
Authorization: Bearer <token>
Content-Type: application/json
Accept: application/json, text/event-stream

{"jsonrpc":"2.0","id":1,"method":"tools/call",
 "params":{"name":"data_dictionary_ping","arguments":{}}}
```

Tools return a `structuredContent` block shaped
`{results: [...], total_rows, truncated}`.

## Execution model

`data_dictionary_ping` runs as a small **SPL** template. `data_dictionary_query`
and `data_dictionary_index_metadata` run as **API** tools: the MCP server proxies a
`GET` to this app's own REST handlers
(`/services/data_dictionary/dictionary/query` and `…/dictionary/index/<index>`)
with `flat=1`. The handler returns a **bare JSON array** - one object per
(index, sourcetype) row, with the merged governance metadata flattened onto it -
which the MCP server turns into the `results` rows. This avoids the search sandbox
(no `| rest`) and means **any governance field flows through automatically**,
including admin-defined custom fields (see *Governance metadata* below).

### How the tools get registered

The tool definitions are the single source of truth in
`appserver/static/tool_input_payload_signatures.json`, declared restmap-side in
`default/tools.conf` (every tool needs an `endpoint_name`). How they reach the
Splunk MCP Server's registry depends on the platform:

- **Splunk Cloud** registers them **automatically on install** - a native
  synced-apps registrar reads the app's `tools.conf` and registers its MCP tools.
  Nothing app-side is required.
- **Splunk Enterprise** has no native registrar (and older MCP servers have no
  `tool_registration` endpoint), so the app self-registers via
  `bin/autoregister.py`: an instance-aware REST handler, fired by the `app.conf`
  `[triggers] reload.tools = http_post /data_dictionary/autoregister` on
  install/enable, that upserts the tools straight into the MCP Server's
  `mcp_tools` + `mcp_tools_enabled` KV collections. It detects the platform via
  `server/info` `instance_type` and no-ops on Cloud. Idempotent; also callable
  directly (`POST /services/data_dictionary/autoregister`).

`deploy/register_mcp_tools.py` remains as a manual one-shot equivalent for ad-hoc
registration.

## Governance metadata

Each result row carries the governance fields merged with **row → index →
sourcetype** precedence. The standard fields are data owner, data category, PII
status, export classification, service owner, security owner and escalation
contacts; admins can add their own **custom fields** (Fields page in the UI), and
those are returned by the query/index tools alongside the standard ones. Editing
metadata requires the `edit_data_dictionary` capability (reads are open) - see the
app README / RBAC notes.

---

## `data_dictionary_ping`

Lightweight health check which confirms the catalog lookup is reachable and reports
its row count. Call it first when troubleshooting MCP/UI connectivity.

**Input:** none.

**Example**

```jsonc
// request arguments
{}
```
```json
// result.structuredContent
{
  "results": [
    { "ok": "true", "app": "data_dictionary", "catalog_rows": "296" }
  ],
  "truncated": false,
  "total_rows": 1
}
```

---

## `data_dictionary_query`

Interrogates the dictionary: filter/search catalog rows with merged KV governance
metadata. All arguments are optional.

| Arg | Type | Default | Meaning |
|-----|------|---------|---------|
| `q` | string | `""` | Case-insensitive substring across index, sourcetype, and all metadata fields. Blank = list everything. |
| `index` | string | `""` | Substring match on the index column. |
| `sourcetype` | string | `""` | Substring match on the sourcetype column. |
| `limit` | integer | `50` | Max rows (1-500). |

**Example - free-text search**

```jsonc
// request arguments
{ "q": "dns", "limit": 2 }
```
```json
// result.structuredContent
{
  "results": [
    {
      "index": "_internal",
      "sourcetype": "ta-nextdns-api_HomeStream-2",
      "totalCount": "172",
      "firstTime": "1775698200",
      "lastTime": "1775698662",
      "recentTime": "1775698664",
      "_key": "index_sourcetype:_internal:ta-nextdns-api_HomeStream-2"
    },
    {
      "index": "pihole",
      "sourcetype": "NextDNS_API_Stats:devices",
      "totalCount": "137672",
      "firstTime": "1754950606",
      "lastTime": "1775698500",
      "recentTime": "1775698500",
      "_key": "index_sourcetype:pihole:NextDNS_API_Stats:devices"
    }
  ],
  "truncated": false,
  "total_rows": 2
}
```

Rows also carry the governance overlay fields when present: `data_owner`, `data_category`, `pii_status`, `export_classification`, `service_owner`,
`security_owner`, `escalation_contacts` (resolved with row → index → sourcetype precedence).

---

## `data_dictionary_index_metadata`

Returns the full dictionary for **one index**: every `(index, sourcetype)` catalog
row in it, with event counts and time range, merged with KV governance metadata.

| Arg | Type | Required | Meaning |
|-----|------|----------|---------|
| `index` | string | yes | Index name (no slashes/whitespace, ≤200 chars). |

**Example**

```jsonc
// request arguments
{ "index": "pihole" }
```
```json
// result.structuredContent (first 2 of 11 rows)
{
  "results": [
    {
      "index": "pihole",
      "sourcetype": "NextDNS_API_Stats:devices",
      "totalCount": "137672",
      "firstTime": "1754950606",
      "lastTime": "1775698500",
      "recentTime": "1775698500",
      "_key": "index_sourcetype:pihole:NextDNS_API_Stats:devices"
    },
    {
      "index": "pihole",
      "sourcetype": "NextDNS_API_Stats:dnssec",
      "totalCount": "137474",
      "firstTime": "1754950609",
      "lastTime": "1775698503",
      "recentTime": "1775698503",
      "_key": "index_sourcetype:pihole:NextDNS_API_Stats:dnssec"
    }
  ],
  "truncated": false,
  "total_rows": 11
}
```

---

## Any MCP client can call these tools

These three tools are registered on the shared Splunk MCP Server, so **any MCP consumer** can call them to ground answers in governance metadata
and external agents such as Claude. Whether a given assistant chooses to call them is that client's orchestration; this app's job is to publish 
accurate, well-described governance tools on the server. 

## Verification

```bash
# Static validation of the registered tool templates (no network, runs in CI):
pytest tests/test_tool_signatures.py -v

# Live integration against a real Splunk in Docker (the CI `integration` job):
npm run build && bash scripts/splunk-docker.sh up
SPLUNK_WEB_URL=http://127.0.0.1:8000 npm run test:integration
bash scripts/splunk-docker.sh down
```

| Layer | Test | Network |
|-------|------|---------|
| Tool registration invariants (ping SPL + no `\| rest`; query/index API → app REST + `flat=1`; flat schema; ids aligned with live) | `tests/test_tool_signatures.py` | none |
| App installs + REST handlers + React bundles render in real Splunk | `tests/integration/` (Playwright) | live Splunk in Docker (CI) |
