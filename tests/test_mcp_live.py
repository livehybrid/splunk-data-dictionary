"""
Live integration tests against a running Splunk with the Data Dictionary app
installed (and, optionally, the Splunk MCP Server). Stdlib-only (urllib) so it
runs in the same pytest env as the unit tests - no `requests` dependency.

Gating (all auto-skip when the env is absent, so unit-only CI stays green):
  * SPLUNK_MGMT_URL (e.g. https://127.0.0.1:8089) + SPLUNK_PASSWORD
        -> REST handler + RBAC tests run.
  * SPLUNK_MCP_URL  (e.g. https://127.0.0.1:8089/services/mcp)
    + SPLUNK_MCP_TOKEN or MCP_TOKEN_FILE (an mcp-audience JWT)
        -> the MCP-protocol tests run too.

What it proves:
  * the persistent REST handlers are live (ping, flat query shape);
  * RBAC: a user WITHOUT edit_data_dictionary is 403 on every write but 200 on
    reads; a user WITH it (via a role) is 200 on writes;
  * (best effort, if the catalog has rows) a custom field flows through to the
    flat query output;
  * the MCP tools answer through the real MCP Server (ping/query).

The test creates its own throwaway role + users + field/metadata and removes them
in teardown, so it is self-contained and leaves no residue.
"""
from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

import pytest

MGMT = (os.environ.get("SPLUNK_MGMT_URL") or "").rstrip("/")
PW = os.environ.get("SPLUNK_PASSWORD") or ""
ADMIN_USER = os.environ.get("SPLUNK_USER") or "admin"
MCP_URL = (os.environ.get("SPLUNK_MCP_URL") or "").rstrip("/")

EDIT_ROLE = "dd_it_editor"
EDITOR_USER = "dd_it_editor_user"
VIEWER_USER = "dd_it_viewer_user"
TEST_PW = "dd-IT-passw0rd!"
CUSTOM_FIELD = "it_retention"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

pytestmark = pytest.mark.skipif(
    not (MGMT and PW),
    reason="SPLUNK_MGMT_URL + SPLUNK_PASSWORD not set (live integration env absent)",
)


def _basic(user, pw):
    import base64
    return "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()


def req(method, path, *, user=ADMIN_USER, pw=None, data=None, form=None, bearer=None, base=None):
    """Return (status, parsed_or_text). Never raises on HTTP error."""
    url = (base or MGMT) + path
    body = None
    headers = {}
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    else:
        headers["Authorization"] = _basic(user, PW if pw is None else pw)
    if form is not None:
        body = urllib.parse.urlencode(form, doseq=True).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, context=CTX, timeout=60) as resp:
            raw = resp.read().decode("utf-8", "replace")
            status = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        status = e.code
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw


# --------------------------------------------------------------------------- #
# Fixtures: throwaway role + users + a seeded custom field, all cleaned up.
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def rbac_env():
    # Editor role carrying the capability; viewer is the stock 'user' role.
    req("POST", "/services/authorization/roles",
        form={"name": EDIT_ROLE, "imported_roles": "user", "capabilities": "edit_data_dictionary"})
    req("POST", "/services/authentication/users",
        form={"name": EDITOR_USER, "password": TEST_PW, "roles": EDIT_ROLE})
    req("POST", "/services/authentication/users",
        form={"name": VIEWER_USER, "password": TEST_PW, "roles": "user"})
    # Seed a custom field + an index-level value (admin is an editor).
    req("POST", "/services/data_dictionary/field-defs/" + CUSTOM_FIELD,
        data={"label": "IT Retention", "type": "select", "options": ["Hot", "Cold"], "order": 90})
    req("POST", "/services/data_dictionary/metadata/" + urllib.parse.quote("index:_internal", safe=""),
        data={CUSTOM_FIELD: "Hot"})
    yield
    for u in (EDITOR_USER, VIEWER_USER):
        req("DELETE", "/services/authentication/users/" + u)
    req("DELETE", "/services/authorization/roles/" + EDIT_ROLE)
    req("DELETE", "/services/data_dictionary/field-defs/" + CUSTOM_FIELD)
    req("DELETE", "/services/data_dictionary/metadata/" + urllib.parse.quote("index:_internal", safe=""))


# --------------------------------------------------------------------------- #
# REST handler smoke
# --------------------------------------------------------------------------- #
def test_rest_ping_ok():
    status, body = req("GET", "/services/data_dictionary/ping")
    assert status == 200, body


def test_query_flat_returns_bare_array():
    status, body = req("GET", "/services/data_dictionary/dictionary/query?flat=1&limit=5")
    assert status == 200, body
    assert isinstance(body, list), f"flat=1 must return a bare JSON array, got {type(body)}"


def test_permissions_endpoint_reports_admin_editor():
    status, body = req("GET", "/services/data_dictionary/permissions")
    assert status == 200, body
    assert body.get("can_edit") is True
    assert body.get("capability") == "edit_data_dictionary"


# --------------------------------------------------------------------------- #
# RBAC matrix
# --------------------------------------------------------------------------- #
def test_viewer_can_read(rbac_env):
    for path in ("/services/data_dictionary/metadata",
                 "/services/data_dictionary/field-defs",
                 "/services/data_dictionary/dictionary/query?flat=1&limit=1"):
        status, body = req("GET", path, user=VIEWER_USER, pw=TEST_PW)
        assert status == 200, (path, status, body)


def test_viewer_permissions_can_edit_false(rbac_env):
    status, body = req("GET", "/services/data_dictionary/permissions", user=VIEWER_USER, pw=TEST_PW)
    assert status == 200, body
    assert body.get("can_edit") is False


@pytest.mark.parametrize("method,path,data", [
    ("POST", "/services/data_dictionary/metadata/" + urllib.parse.quote("index:_internal", safe=""), {"it_retention": "Cold"}),
    ("DELETE", "/services/data_dictionary/metadata/" + urllib.parse.quote("index:_internal", safe=""), None),
    ("POST", "/services/data_dictionary/field-defs/zzz_blocked", {"label": "x"}),
    ("POST", "/services/data_dictionary/build-catalog", None),
])
def test_viewer_writes_are_forbidden(rbac_env, method, path, data):
    status, body = req(method, path, user=VIEWER_USER, pw=TEST_PW, data=data)
    assert status == 403, f"viewer should be 403 on {method} {path}, got {status}: {body}"


def test_editor_can_write(rbac_env):
    status, body = req(
        "POST",
        "/services/data_dictionary/metadata/" + urllib.parse.quote("index:_internal", safe=""),
        user=EDITOR_USER, pw=TEST_PW, data={CUSTOM_FIELD: "Hot"},
    )
    assert status == 200, f"editor write should succeed, got {status}: {body}"


# --------------------------------------------------------------------------- #
# Custom field flows through the flat query (needs catalog rows -> best effort)
# --------------------------------------------------------------------------- #
def _catalog_has_internal():
    status, body = req("GET", "/services/data_dictionary/dictionary/query?flat=1&index=_internal&limit=1")
    return status == 200 and isinstance(body, list) and len(body) > 0


def test_custom_field_flows_through(rbac_env):
    if not _catalog_has_internal():
        # Try to populate the catalog on demand, then poll briefly.
        req("POST", "/services/data_dictionary/build-catalog")
        deadline = time.time() + 90
        while time.time() < deadline and not _catalog_has_internal():
            time.sleep(5)
    if not _catalog_has_internal():
        pytest.skip("catalog has no _internal rows yet (build-catalog not populated)")
    status, rows = req("GET", "/services/data_dictionary/dictionary/query?flat=1&index=_internal&limit=50")
    assert status == 200 and rows
    assert any(r.get(CUSTOM_FIELD) == "Hot" for r in rows), \
        f"custom field {CUSTOM_FIELD} should flow through to the flat query rows"


# --------------------------------------------------------------------------- #
# MCP protocol (only when an mcp-audience token is available)
# --------------------------------------------------------------------------- #
def _mcp_token():
    tok = os.environ.get("SPLUNK_MCP_TOKEN")
    if tok:
        return tok.strip()
    path = os.environ.get("MCP_TOKEN_FILE")
    if path and os.path.exists(path):
        with open(path) as fh:
            return fh.read().strip()
    return ""


mcp_gate = pytest.mark.skipif(
    not (MCP_URL and _mcp_token()),
    reason="SPLUNK_MCP_URL + token (SPLUNK_MCP_TOKEN / MCP_TOKEN_FILE) not set",
)


def _mcp_call(name, arguments, attempts=3):
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": name, "arguments": arguments}}
    body = json.dumps(payload).encode()
    # On a freshly-restarted Splunk the first SPL-backed tool call (ping dispatches
    # a search job) can exceed the read timeout while the search subsystem warms up.
    # Retry on timeout: the first attempt warms it, a later attempt then succeeds.
    raw = None
    for attempt in range(attempts):
        r = urllib.request.Request(MCP_URL, data=body, method="POST", headers={
            "Authorization": "Bearer " + _mcp_token(),
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        })
        try:
            with urllib.request.urlopen(r, context=CTX, timeout=90) as resp:
                raw = resp.read().decode("utf-8", "replace")
            break
        except (TimeoutError, urllib.error.URLError) as exc:
            is_timeout = isinstance(exc, TimeoutError) or isinstance(
                getattr(exc, "reason", None), (TimeoutError, OSError))
            if not is_timeout or attempt == attempts - 1:
                raise
            time.sleep(5)
    for line in raw.splitlines():
        line = line[6:] if line.startswith("data: ") else line
        line = line.strip()
        if not line:
            continue
        try:
            doc = json.loads(line)
        except ValueError:
            continue
        if "result" in doc or "error" in doc:
            return doc
    raise AssertionError(f"no JSON-RPC result in MCP response: {raw[:300]}")


def _mcp_rows(doc):
    assert "error" not in doc, doc["error"]
    content = doc["result"]["content"][0]["text"]
    inner = json.loads(content)
    return inner.get("results", inner if isinstance(inner, list) else [])


@mcp_gate
def test_mcp_ping():
    rows = _mcp_rows(_mcp_call("data_dictionary_ping", {}))
    assert rows and rows[0].get("app") == "data_dictionary_for_splunk"


@mcp_gate
def test_mcp_query_returns_rows():
    doc = _mcp_call("data_dictionary_query", {"limit": 5})
    assert "error" not in doc, doc.get("error")
    rows = _mcp_rows(doc)
    assert isinstance(rows, list)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
