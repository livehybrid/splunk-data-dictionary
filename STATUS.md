# STATUS — Splunk Data Dictionary

_Honest state of the app for the Splunk Agentic Ops Hackathon 2026 (Platform &
Developer Experience + "Best Use of Splunk MCP Server")._

## TL;DR

A focused **catalog + MCP governance tools** app. You can **clone, build, test and
package** it today: `npm run build` produces an installable `stage/`, `npm run
package` an AppInspect-clean tarball. The catalog UI (browse/edit governance
metadata) and the three **Splunk MCP tools** are deployed and working on the live
instance, and the MCP tools answer ownership/sign-off/PII questions grounded in the
catalog.

## What works (verified)

- ✅ **Catalog UI** — React page in Splunk: index/sourcetype table with governance
  columns, per-row view/edit icon actions, value-suggesting dropdowns, PII Status
  as Yes/No, and an "Apply to" scope (this sourcetype / all in index / only un-set).
  Deployed and verified live (`docs/screenshots/`).
- ✅ **Governance metadata** — KV-store backed, merged row → index → sourcetype, with
  a kvstore lookup (`data_dictionary_metadata`) so it reads in pure SPL.
- ✅ **MCP tools live** — `data_dictionary_query`, `data_dictionary_index_metadata`,
  `data_dictionary_ping` registered on the Splunk MCP Server and answering. They
  execute as **SPL** over the catalog + governance lookups (no `| rest`,
  sandbox-safe). Descriptions are governance-worded so agents select them for
  ownership/sign-off/PII questions. Verified live, e.g.
  `data_dictionary_query("cultivar")` → the index's owners + escalation contacts.
- ✅ **REST API** — persistent handlers (`ucc-app/bin/`) power the UI and are callable
  directly: ping, discovery, metadata CRUD, dictionary/index, dictionary/query,
  options, build-catalog.
- ✅ **Build + package** — `ucc-gen` (official UCC) + Webpack → `stage/` → tarball.
- ✅ **AppInspect precert** — 0 errors, 0 failures (1 informational future_failure:
  the `python.required = python3` 10.2 deprecation notice).
- ✅ **CI/CD** — `ci.yml` reuses the shared `livehybrid/deploy-splunk-app-action`
  AppInspect workflows (wrapping Splunk's official actions), plus a live-Splunk
  Docker integration job, third-party license attribution, and a tag-driven release
  that publishes the tarball to a GitHub Release. See the README.
- ✅ **Tests** — `pytest` tool-signature invariants (live MCP tests auto-skip without
  creds) + Playwright integration tests against a real Splunk in Docker.

## What's deployed vs in the repo

- `ucc-app/` is the single buildable source of truth; `npm run build` produces the
  deployed app from it. The on-disk `tool_input_payload_signatures.json` is the
  source the MCP Server imports into its `mcp_tools` KV collection.

## What's next

1. **Modernise `python.required`** to clear the AppInspect `future` deprecation, so
   the `future` tag can be added to the AppInspect CLI matrix.
2. **Splunk version test matrix** (`splunk/addonfactory-test-matrix-action`).
3. **Seeded-catalog integration coverage** — drive the metadata edit + "Apply to
   index" scope in the live-Splunk Playwright suite.
4. Short demo video.

## History

This app previously bundled an experimental "AI Concierge" (an in-app/CLI LLM agent
+ governance scorecard). It was removed to keep the app a focused, honestly-scoped
**catalog + MCP governance tools** deliverable; the agentic value now lives where it
belongs — in the MCP tools any agent (Splunk AI Assistant, Claude, …) can call.
