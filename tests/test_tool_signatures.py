"""
Static validation of the MCP tool registration file
(`appserver/static/tool_input_payload_signatures.json`).

No network needed: this parses the JSON the Splunk MCP Server registers from and
asserts the invariants the server enforces at load/exec time.

History:
  * Round 2 (commit 1ecdd44) fixed three SPL-template bugs: the `| rest` sandbox
    rejection, the argument-quoting bug, and SPL tools carrying API fields.
  * Post-submission the two read tools were migrated SPL -> API execution
    (they proxy to the app's own REST handlers, which return a flat JSON array
    that the MCP server turns into result rows). `data_dictionary_ping` stays SPL.

So the current invariants are:
  - ping            : execution.type == "spl", non-empty template, no `| rest`
                      (or other sandbox-forbidden command), no API fields.
  - query / index   : execution.type == "api", GET + an /services/data_dictionary
                      endpoint, no SPL template, params carry flat=1 so the handler
                      returns the bare array the API executor expects.
  - all tools       : flat ($ref-free) input schema; identifiers aligned with the
                      live registration (tool_id == "data_dictionary_for_splunk:<name>",
                      external_app_id == required_app == "data_dictionary_for_splunk").
  - no optional string arg carries the old pre-quoted `'""'` default - that was an
    SPL-quoting hack; for an API tool it would send a literal `""` query value.

The buildable source (`ucc-app/`) is checked so a rebuild can't silently
reintroduce a regression.
"""
from __future__ import annotations

import json
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIG_REL = os.path.join("appserver", "static", "tool_input_payload_signatures.json")
COPIES = {
    "ucc-app": os.path.join(REPO, "ucc-app", SIG_REL),
}

APP = "data_dictionary_for_splunk"
EXPECTED_APP_ID = "data_dictionary_for_splunk"
REST_ROOT = "data_dictionary"  # restRoot kept when the app id was renamed - endpoint paths did not change
SPL_TOOLS = {"data_dictionary_ping"}
API_TOOLS = {"data_dictionary_query", "data_dictionary_index_metadata"}

# SPL commands the MCP search sandbox forbids (the original failure was `rest`).
FORBIDDEN_SPL_COMMANDS = ["rest", "script", "sendemail", "runshellscript", "delete"]


def _load(path: str) -> list:
    with open(path) as fh:
        return json.load(fh)


def _all_tools():
    """(copy_name, tool_dict) for every tool in every copy that exists."""
    for name, path in COPIES.items():
        if not os.path.exists(path):
            continue
        for tool in _load(path):
            yield name, tool


def _string_props_not_required(tool: dict):
    schema = tool.get("inputSchema", {})
    required = set(schema.get("required", []))
    for field, spec in schema.get("properties", {}).items():
        if spec.get("type") == "string" and field not in required:
            yield field, spec


def test_signature_files_exist():
    assert os.path.exists(COPIES["ucc-app"]), "buildable signatures (ucc-app/) missing"


def test_expected_dd_tools_present():
    tools = {t["name"] for _, t in _all_tools()}
    for expected in SPL_TOOLS | API_TOOLS:
        assert expected in tools, f"{expected} not registered"


def test_identifiers_aligned_with_live_registration():
    """tool_id / external_app_id / required_app must match the live KV registration
    so the file is a faithful, re-runnable registration source."""
    for copy_name, tool in _all_tools():
        name = tool["name"]
        assert tool.get("tool_id") == f"{APP}:{name}", (
            f"[{copy_name}] {name}: tool_id should be '{APP}:{name}', got {tool.get('tool_id')!r}"
        )
        meta = tool.get("_meta", {})
        assert meta.get("external_app_id") == EXPECTED_APP_ID, (
            f"[{copy_name}] {name}: external_app_id should be '{EXPECTED_APP_ID}'"
        )
        assert meta.get("required_app") == EXPECTED_APP_ID, (
            f"[{copy_name}] {name}: required_app should be '{EXPECTED_APP_ID}'"
        )


def test_external_app_id_present():
    for copy_name, tool in _all_tools():
        assert tool.get("_meta", {}).get("external_app_id"), (
            f"[{copy_name}] {tool['name']}: missing _meta.external_app_id (immutable + required)"
        )


def _advertised_name(tool: dict) -> str:
    """The name the MCP Server publishes for a tool.

    Mirrors Tool._convert_from_new_schema in the Splunk MCP Server: the stored
    `name` is prefixed with `_meta.name_prefix` (falling back to
    `_meta.external_app_id`) unless it already carries that prefix.
    """
    meta = tool.get("_meta", {})
    prefix = (meta.get("name_prefix") or meta.get("external_app_id") or "").strip()
    name = tool["name"]
    if prefix and not name.startswith(f"{prefix}_"):
        return f"{prefix}_{name}"
    return name


def test_advertised_name_matches_registered_name():
    """tools/list advertises the prefixed name; tools/call looks the tool up by the
    mcp_tools_enabled _key, which registration writes from `name`. If the two
    diverge, every call fails -32004 for the exact name tools/list just handed the
    client. Regression: without `_meta.name_prefix` the server advertised
    'data_dictionary_for_splunk_data_dictionary_ping' while the enabled row was
    keyed 'data_dictionary_ping'.
    """
    for copy_name, tool in _all_tools():
        advertised = _advertised_name(tool)
        assert advertised == tool["name"], (
            f"[{copy_name}] {tool['name']}: MCP would advertise {advertised!r} but "
            f"registration enables {tool['name']!r} - set _meta.name_prefix to a "
            f"prefix the tool name already carries"
        )


def test_input_schema_is_flat_no_refs():
    for copy_name, tool in _all_tools():
        blob = json.dumps(tool.get("inputSchema", {}))
        assert "$ref" not in blob, f"[{copy_name}] {tool['name']}: inputSchema uses $ref"
        assert "$defs" not in blob and "definitions" not in blob, (
            f"[{copy_name}] {tool['name']}: inputSchema uses nested definitions"
        )


def test_execution_type_matches_expected():
    for copy_name, tool in _all_tools():
        name = tool["name"]
        exec_type = tool.get("_meta", {}).get("execution", {}).get("type")
        if name in SPL_TOOLS:
            assert exec_type == "spl", f"[{copy_name}] {name}: expected spl execution, got {exec_type!r}"
        elif name in API_TOOLS:
            assert exec_type == "api", f"[{copy_name}] {name}: expected api execution, got {exec_type!r}"


def test_spl_tools_have_clean_template_and_no_api_fields():
    for copy_name, tool in _all_tools():
        if tool["name"] not in SPL_TOOLS:
            continue
        execu = tool.get("_meta", {}).get("execution", {})
        tmpl = execu.get("template", "")
        assert tmpl, f"[{copy_name}] {tool['name']}: empty execution template"
        low = tmpl.lower()
        for cmd in FORBIDDEN_SPL_COMMANDS:
            assert f"| {cmd}" not in low and f"|{cmd}" not in low, (
                f"[{copy_name}] {tool['name']}: template uses forbidden `| {cmd}` "
                f"(MCP sandbox rejects it)"
            )
        # SPL tools must not carry API execution fields - the loader rejects them.
        for api_field in ("method", "endpoint", "url", "path", "params", "body"):
            assert api_field not in execu, (
                f"[{copy_name}] {tool['name']}: SPL tool must not define execution.{api_field}"
            )


def test_api_tools_proxy_to_app_rest_handlers():
    """API tools must be a GET to one of this app's dictionary REST endpoints,
    carry no SPL template, and request flat=1 so the handler returns the bare
    array the API executor turns into result rows."""
    for copy_name, tool in _all_tools():
        if tool["name"] not in API_TOOLS:
            continue
        execu = tool.get("_meta", {}).get("execution", {})
        assert execu.get("method", "").upper() == "GET", (
            f"[{copy_name}] {tool['name']}: API tool should be GET"
        )
        endpoint = execu.get("endpoint", "")
        assert isinstance(endpoint, str) and endpoint.startswith(f"/services/{REST_ROOT}/dictionary/"), (
            f"[{copy_name}] {tool['name']}: endpoint should target /services/{REST_ROOT}/dictionary/*, "
            f"got {endpoint!r}"
        )
        assert "template" not in execu, (
            f"[{copy_name}] {tool['name']}: API tool must not define an SPL template"
        )
        params = execu.get("params") or {}
        assert isinstance(params, dict), f"[{copy_name}] {tool['name']}: params must be an object"
        assert str(params.get("flat")) == "1", (
            f"[{copy_name}] {tool['name']}: params must request flat=1 for the API executor"
        )


def test_index_metadata_endpoint_has_index_placeholder():
    for copy_name, tool in _all_tools():
        if tool["name"] != "data_dictionary_index_metadata":
            continue
        endpoint = tool["_meta"]["execution"].get("endpoint", "")
        assert "$index$" in endpoint, (
            f"[{copy_name}] data_dictionary_index_metadata: endpoint must template the index "
            f"as $index$, got {endpoint!r}"
        )


def test_query_params_template_each_optional_arg():
    for copy_name, tool in _all_tools():
        if tool["name"] != "data_dictionary_query":
            continue
        params = tool["_meta"]["execution"].get("params") or {}
        for arg in ("q", "index", "sourcetype", "limit"):
            assert params.get(arg) == f"${arg}$", (
                f"[{copy_name}] data_dictionary_query: params[{arg!r}] should be '${arg}$' "
                f"so the MCP server substitutes/drops it, got {params.get(arg)!r}"
            )


def test_no_legacy_pre_quoted_string_defaults():
    """The old SPL-quoting hack ('""' defaults) must not survive on API tools - it
    would send a literal `""` as the query value instead of being dropped."""
    for copy_name, tool in _all_tools():
        for field, spec in _string_props_not_required(tool):
            assert spec.get("default") != '""', (
                f"[{copy_name}] {tool['name']}.{field}: legacy pre-quoted '\"\"' default must be "
                f"removed (API tools drop unfilled optional params)"
            )


if __name__ == "__main__":  # allow `python tests/test_tool_signatures.py`
    raise SystemExit(pytest.main([__file__, "-v"]))
