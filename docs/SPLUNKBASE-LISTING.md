# Splunkbase listing copy — Data Dictionary

Drafted 2026-07-23 for the v0.1.0 Splunkbase submission. Splunkbase's exact field
names/limits can shift — check the live submission form and trim to fit, but this
covers every field it's asked for historically.

## App name

Data Dictionary

## Summary (short description — aim for ~200 characters, shown on tiles/search)

> Catalogs your Splunk indexes and sourcetypes with governance metadata (data
> owner, PII status, export classification, security owner) and exposes it to
> AI agents as MCP tools.

(188 characters)

## Categories

Pick the closest 2–3 from the dropdown at submission time. Best fits, in order:

1. **IT Operations**
2. **Utilities**
3. **Artificial Intelligence** (if offered — the MCP/agent angle is the differentiator)

## Supported Splunk platform

- Splunk Enterprise 9.x+ (targets 10.x)
- Splunk Cloud (Victoria experience) — 9.x+
- Requires KV Store enabled (default on search heads)

## Pricing / Support type

- Free, Apache-2.0 licensed
- Support: Developer Support (community, via GitHub issues) — not Splunk Support

## Full description

Data Dictionary catalogs your Splunk indexes and sourcetypes and attaches
governance metadata to them — Data Owner, PII Status, Export Classification,
Service Owner, Security Owner, Escalation Contacts — then exposes that catalog
to AI agents as Splunk MCP tools, so questions like *"who do I need sign-off
from to get access to the finance indexes?"* can be answered straight from any
MCP-capable AI assistant, not just from someone who already knows Splunk.

Built on the official Splunk UCC framework and `@splunk/react-ui`.

**Key features**

- **Catalog** — every `(index, sourcetype)` pair in your environment, built
  automatically by a scheduled search or on demand from the UI.
- **Governance metadata** — stored in KV Store, inherited row → index →
  sourcetype, so you set a value once and it cascades. Also exposed as a plain
  SPL lookup (`data_dictionary_metadata`) for use in your own searches.
- **Catalog editor UI** — a native Splunk React page to browse and edit
  metadata: filter by index/sourcetype, per-row view/edit, dropdowns that
  suggest existing values, PII Status as Yes/No, and an "Apply to" scope (one
  sourcetype / everything in an index / only the un-set rows).
- **Custom fields** — admins can define their own governance fields (Select or
  Boolean) beyond the built-in set; custom fields flow automatically into the
  editor and into the MCP tools.
- **RBAC** — browsing and the MCP query tools are open to everyone; every
  metadata write requires the `edit_data_dictionary` capability, enforced
  server-side (granted to `admin` by default).
- **MCP tools for AI agents** — `data_dictionary_query` (search the catalog +
  governance by keyword), `data_dictionary_index_metadata` (full governance
  record for a named index), `data_dictionary_ping` (health check). All
  read-only today.

**Why**

Data ownership and compliance answers are usually scattered across wikis,
spreadsheets and tribal knowledge. Data Dictionary keeps that information next
to the data itself, inside Splunk — and via MCP, makes it queryable in plain
language by anyone with an MCP-enabled AI client.

**Requirements**

- Splunk Enterprise or Cloud, 9.x+ (targets 10.x)
- KV Store enabled (default on search heads)
- Optional: a Splunk MCP Server that imports the app's tool signatures, to
  expose the three MCP tools to AI agents

## Setup / installation instructions field

1. Install the app (**Apps → Manage Apps → Install app from file**, or push it
   via deployment server / Splunk Cloud self-service install).
2. Open the Data Dictionary app and run **"Data Dictionary - Build Catalog"**
   from the home page (or let the scheduled search populate it) to seed the
   catalog from your existing indexes and sourcetypes.
3. Edit governance metadata for the rows that matter — set a value on an index
   or sourcetype and it cascades to everything under it unless overridden per
   row.
4. Optional: go to **Fields** to define your own governance fields if the
   built-in set (Data Owner, PII Status, Export Classification, Service Owner,
   Security Owner, Escalation Contacts) doesn't cover everything you track.
5. Assign the `edit_data_dictionary` capability to whichever roles should be
   able to curate metadata — everyone else gets read-only browsing.
6. Optional: if you run a Splunk MCP Server, point it at this app so
   `data_dictionary_query`, `data_dictionary_index_metadata` and
   `data_dictionary_ping` become available to your AI agents.

## Release notes (v0.1.0 — initial public release)

- Catalog build (scheduled search + on-demand) over indexes/sourcetypes.
- Governance metadata: KV Store-backed, row → index → sourcetype inheritance,
  plus a plain-SPL lookup.
- React catalog editor UI with suggested-value dropdowns and an "Apply to"
  scope.
- Admin-defined custom governance fields (Select/Boolean).
- RBAC via the `edit_data_dictionary` capability.
- Three MCP tools (`data_dictionary_query`, `data_dictionary_index_metadata`,
  `data_dictionary_ping`), executed as API tools against the app's own REST
  handlers.
- AppInspect precert clean (0 errors, 0 failures).

## Support / links

- Source, issues, documentation: https://github.com/livehybrid/splunk-data-dictionary
- License: Apache-2.0

## Screenshots to upload

From `docs/screenshots/`:

- `01-catalog-home.png` — the catalog home page / list view.
- `02-edit-metadata.png` — editing governance metadata for a row (suggested
  caption: *"Browse, filter and edit index/sourcetype governance metadata
  directly in Splunk."*).
- `03-claude-chat.png` — Claude answering an ownership/sign-off question via
  the MCP tools (suggested caption: *"Ask an AI agent who owns a data source,
  its PII status or who to get sign-off from — answered live from the
  catalog."*).
