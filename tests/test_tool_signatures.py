"""
Static validation of the MCP tool registration file
(`appserver/static/tool_input_payload_signatures.json`).

This is the regression guard for the three bugs that broke the live tools and
were fixed in round 2 (commit 1ecdd44). It needs **no network** — it parses the
JSON the Splunk MCP Server registers from and asserts the invariants the server
enforces at load/exec time:

  1. No forbidden SPL commands in the execution template. The MCP search sandbox
     rejects `| rest` (the original "Forbidden command found: rest" failure), so
     no template may contain it.
  2. Flat, `$ref`-free input schema (Anthropic/!MCP reject complex/`$ref` schemas).
  3. `_meta.execution.type == "spl"` with a non-empty template, and SPL tools must
     NOT define API execution fields (method/endpoint) — the loader rejects those.
  4. `external_app_id` present (immutable + required by the registration model).
  5. Optional string args (NOT in `required`) carry a PRE-QUOTED default (`'""'`).
     The server JSON-quotes string args before `$arg$` substitution; a bare
     ``"default": ""`` would substitute to an empty/unquoted token and break the
     SPL (`index=` / `lower()` with nothing), so optional string defaults must be
     the two-character string `""`.

The buildable source (`ucc-app/`) is checked so a rebuild can't silently
reintroduce the bug.
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
    for expected in (
        "data_dictionary_ping",
        "data_dictionary_query",
        "data_dictionary_index_metadata",
    ):
        assert expected in tools, f"{expected} not registered"


def test_no_forbidden_spl_commands_in_templates():
    """Regression guard for 'Forbidden command found: rest'."""
    for copy_name, tool in _all_tools():
        tmpl = tool.get("_meta", {}).get("execution", {}).get("template", "")
        low = tmpl.lower()
        for cmd in FORBIDDEN_SPL_COMMANDS:
            # Match the command as a pipe segment: `| rest ...`.
            assert f"| {cmd}" not in low and f"|{cmd}" not in low, (
                f"[{copy_name}] {tool['name']}: template uses forbidden `| {cmd}` "
                f"(MCP sandbox rejects it)"
            )


def test_execution_is_spl_with_template_and_no_api_fields():
    for copy_name, tool in _all_tools():
        execu = tool.get("_meta", {}).get("execution", {})
        assert execu.get("type") == "spl", f"[{copy_name}] {tool['name']}: execution.type != spl"
        assert execu.get("template"), f"[{copy_name}] {tool['name']}: empty execution template"
        # SPL tools must not carry API execution fields — the loader rejects them
        # ("SPL tools cannot define API execution fields").
        for api_field in ("method", "endpoint", "url", "path"):
            assert api_field not in execu, (
                f"[{copy_name}] {tool['name']}: SPL tool must not define execution.{api_field}"
            )


def test_external_app_id_present():
    for copy_name, tool in _all_tools():
        assert tool.get("_meta", {}).get("external_app_id"), (
            f"[{copy_name}] {tool['name']}: missing _meta.external_app_id (immutable + required)"
        )


def test_input_schema_is_flat_no_refs():
    for copy_name, tool in _all_tools():
        blob = json.dumps(tool.get("inputSchema", {}))
        assert "$ref" not in blob, f"[{copy_name}] {tool['name']}: inputSchema uses $ref"
        assert "$defs" not in blob and "definitions" not in blob, (
            f"[{copy_name}] {tool['name']}: inputSchema uses nested definitions"
        )


def test_optional_string_args_have_pre_quoted_defaults():
    """
    Regression guard for the quoting bug: the server JSON-quotes string args
    before `$arg$` substitution, so an optional string arg's DEFAULT must already
    be a quoted-empty token (`""`) — otherwise the substituted SPL is malformed
    (e.g. `index=` or `lower()` with nothing).
    """
    for copy_name, tool in _all_tools():
        for field, spec in _string_props_not_required(tool):
            if "default" not in spec:
                continue
            assert spec["default"] == '""', (
                f"[{copy_name}] {tool['name']}.{field}: optional string default must be "
                f'the pre-quoted token \'""\' (got {spec["default"]!r})'
            )


def test_query_template_substitution_well_formed():
    """
    The data_dictionary_query template must reference each optional arg via
    `$arg$` exactly where a quoted string is expected, so the server's JSON
    quoting lands correctly (no `index=$index$` style un-lowered bare compares).
    """
    for copy_name, tool in _all_tools():
        if tool["name"] != "data_dictionary_query":
            continue
        tmpl = tool["_meta"]["execution"]["template"]
        # q/index/sourcetype are wrapped in lower(...) so the JSON-quoted value
        # sits inside a function call, not bare next to `=`.
        for arg in ("$q$", "$index$", "$sourcetype$"):
            assert f"lower({arg})" in tmpl, (
                f"[{copy_name}] data_dictionary_query: expected lower({arg}) in template"
            )


if __name__ == "__main__":  # allow `python tests/test_tool_signatures.py`
    raise SystemExit(pytest.main([__file__, "-v"]))
