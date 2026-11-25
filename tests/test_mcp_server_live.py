"""
The Data Dictionary's MCP tools, called through a real Splunk MCP Server.

CI (the `mcp` job) downloads the MCP Server from Splunkbase, installs it into the
Docker Splunk that runs this app, mints an MCP token and runs this file with
MCP_REQUIRED=1, which turns every "environment missing" skip into a failure:
the tests skipped unseen for months once, and a skip on main is a broken
pipeline, not a pass. Without MCP_REQUIRED (a laptop, the unit tier) they skip.

What is proved, in order:
  1. the app's own registration endpoint (bin/autoregister.py, the handler the
     app.conf [triggers] entry fires on install) writes every tool into the MCP
     Server's KV collections;
  2. tools/list advertises each tool under the name in the signatures file, with
     its input schema (the server prefixes names it does not recognise, and a
     name it advertises but cannot resolve fails every call with -32004);
  3. tools/call of each tool returns what the data says. The expected rows come
     from data this test seeds straight into the catalog lookup and the metadata
     KV collection, never from the app's REST handlers, which the API tools
     proxy to: comparing the MCP answer with the handler's would agree with any
     bug in the handler.
"""
from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import pytest

MGMT = (os.environ.get("SPLUNK_MGMT_URL") or "").rstrip("/")
PW = os.environ.get("SPLUNK_PASSWORD") or ""
ADMIN = os.environ.get("SPLUNK_USER") or "admin"
MCP_URL = (os.environ.get("SPLUNK_MCP_URL") or "").rstrip("/")
REQUIRED = os.environ.get("MCP_REQUIRED") == "1"

APP = "data_dictionary_for_splunk"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIGNATURES = json.load(open(os.path.join(
    REPO, "ucc-app", "appserver", "static", "tool_input_payload_signatures.json")))
KV_MCP = "/servicesNS/nobody/Splunk_MCP_Server/storage/collections/data"

PROBE = "ddmcp" + uuid.uuid4().hex[:8]          # unique per run
PROBE_INDEX = f"{PROBE}_idx"
PROBE_ST = f"{PROBE}:st"
PROBE_OWNER = f"{PROBE}-owner"
PROBE_CATEGORY = f"{PROBE}-category"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def _token():
    tok = os.environ.get("SPLUNK_MCP_TOKEN", "").strip()
    path = os.environ.get("MCP_TOKEN_FILE")
    if not tok and path and os.path.exists(path):
        tok = open(path).read().strip()
    return tok


_missing = [n for n, v in (("SPLUNK_MGMT_URL", MGMT), ("SPLUNK_PASSWORD", PW),
                           ("SPLUNK_MCP_URL", MCP_URL), ("an MCP token", _token())) if not v]
if _missing and REQUIRED:
    raise RuntimeError(f"MCP_REQUIRED=1 but {', '.join(_missing)} missing: the MCP harness did not run")
pytestmark = pytest.mark.skipif(bool(_missing), reason=f"live MCP env absent ({', '.join(_missing)})")


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def rest(method, path, *, form=None, data=None, params=None):
    import base64
    url = MGMT + path + ("?" + urllib.parse.urlencode(params) if params else "")
    headers = {"Authorization": "Basic " + base64.b64encode(f"{ADMIN}:{PW}".encode()).decode()}
    body = None
    if form is not None:
        body = urllib.parse.urlencode(form).encode()
    elif data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=120) as r:
            raw, status = r.read().decode("utf-8", "replace"), r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read().decode("utf-8", "replace"), e.code
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw


def spl(search):
    status, body = rest("POST", "/services/search/jobs", form={
        "search": search, "exec_mode": "oneshot", "output_mode": "json", "count": "0"})
    assert status == 200, f"search failed ({status}): {search}\n{str(body)[:400]}"
    return body.get("results", [])


class Mcp:
    """Minimal streamable-HTTP MCP client: initialize, then JSON-RPC calls that
    echo the mcp-session-id back. Responses may be plain JSON or SSE data lines."""

    def __init__(self):
        self.session = None
        self.next_id = 0

    def _post(self, payload):
        headers = {"Authorization": "Bearer " + _token(), "Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        req = urllib.request.Request(MCP_URL, data=json.dumps(payload).encode(), method="POST", headers=headers)
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, context=CTX, timeout=120) as r:
                    self.session = r.headers.get("mcp-session-id") or self.session
                    return r.status, r.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                return e.code, e.read().decode("utf-8", "replace")
            except (TimeoutError, urllib.error.URLError):
                # The first SPL-backed call on a fresh Splunk can outlast the read
                # timeout while search warms up.
                if attempt == 2:
                    raise
                time.sleep(5)

    def rpc(self, method, params=None):
        self.next_id += 1
        status, raw = self._post({"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params or {}})
        for line in raw.splitlines():
            line = line[5:].strip() if line.startswith("data:") else line.strip()
            try:
                doc = json.loads(line)
            except ValueError:
                continue
            if isinstance(doc, dict) and ("result" in doc or "error" in doc):
                return doc
        raise AssertionError(f"{method}: no JSON-RPC result (HTTP {status}): {raw[:400]}")

    def notify(self, method):
        self._post({"jsonrpc": "2.0", "method": method})

    def call(self, name, arguments):
        doc = self.rpc("tools/call", {"name": name, "arguments": arguments})
        assert "error" not in doc, f"tools/call {name}: {doc['error']}"
        result = doc["result"]
        text = result["content"][0]["text"]
        assert not result.get("isError"), f"tools/call {name} returned an error: {text[:400]}"
        return json.loads(text)


def rows_of(payload):
    rows = payload.get("results", payload) if isinstance(payload, dict) else payload
    assert isinstance(rows, list), f"expected a row list, got {str(payload)[:300]}"
    return rows


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def registered():
    """Run the app's own registration endpoint, as the [triggers] reload does."""
    # Start from nothing, so what is found afterwards was written by the app.
    for t in SIGNATURES:
        rest("DELETE", f"{KV_MCP}/mcp_tools/{urllib.parse.quote(t['tool_id'], safe='')}")
        rest("DELETE", f"{KV_MCP}/mcp_tools_enabled/{urllib.parse.quote(t['name'], safe='')}")
    status, body = rest("POST", "/services/data_dictionary/autoregister")
    assert status == 200 and isinstance(body, dict), f"autoregister: HTTP {status} {str(body)[:300]}"
    assert body.get("ok") is True, f"autoregister did not register: {body}"
    return body


@pytest.fixture(scope="module")
def mcp(registered):
    client = Mcp()
    doc = client.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                    "clientInfo": {"name": "dd-ci", "version": "1"}})
    assert "result" in doc, f"initialize failed: {doc}"
    client.notify("notifications/initialized")
    return client


@pytest.fixture(scope="module")
def probe_data():
    """One catalog row and one index-level metadata document, written straight
    into the lookup and the KV collection the app reads, then removed."""
    spl(f'| makeresults | eval index="{PROBE_INDEX}", sourcetype="{PROBE_ST}", frozenTimePeriodInSecs="86400" '
        '| fields - _time | outputlookup append=true data_dictionary_catalog')
    key = f"index:{PROBE_INDEX}"
    status, body = rest("POST", f"/servicesNS/nobody/{APP}/storage/collections/data/metadata",
                        data={"_key": key, "data_owner": PROBE_OWNER, "data_category": PROBE_CATEGORY})
    assert status in (200, 201), f"seeding metadata KV: {status} {str(body)[:300]}"
    assert any(r.get("index") == PROBE_INDEX for r in spl("| inputlookup data_dictionary_catalog")), \
        "probe row did not reach the catalog lookup"
    yield
    rest("DELETE", f"/servicesNS/nobody/{APP}/storage/collections/data/metadata/{urllib.parse.quote(key, safe='')}")
    spl(f'| inputlookup data_dictionary_catalog | where index!="{PROBE_INDEX}" | outputlookup data_dictionary_catalog')


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #
def test_autoregister_writes_every_tool(registered):
    got = {r["name"]: r for r in registered.get("results", [])}
    assert sorted(got) == sorted(t["name"] for t in SIGNATURES), registered
    for name, r in got.items():
        assert 200 <= int(r["mcp_tools"]) < 300 and 200 <= int(r["enabled"]) < 300, (name, r)
    # Read the server's KV back directly: the definition is stored and enabled.
    for t in SIGNATURES:
        status, doc = rest("GET", f"{KV_MCP}/mcp_tools/{urllib.parse.quote(t['tool_id'], safe='')}",
                           params={"output_mode": "json"})
        assert status == 200, f"{t['tool_id']} not in mcp_tools: {status}"
        assert doc.get("name") == t["name"]


def test_tools_list_advertises_each_tool_by_its_own_name(mcp):
    doc = mcp.rpc("tools/list")
    assert "error" not in doc, doc
    listed = {t["name"]: t for t in doc["result"]["tools"]}
    for t in SIGNATURES:
        assert t["name"] in listed, (
            f"{t['name']} not advertised; Data Dictionary-looking names listed: "
            f"{sorted(n for n in listed if 'dictionary' in n)}")
        schema = listed[t["name"]].get("inputSchema") or {}
        assert sorted(schema.get("properties", {})) == sorted(t["inputSchema"]["properties"]), t["name"]
        assert sorted(schema.get("required", [])) == sorted(t["inputSchema"].get("required", [])), t["name"]


# --------------------------------------------------------------------------- #
# Calls
# --------------------------------------------------------------------------- #
def test_ping_reports_the_app_and_catalog_size(mcp, probe_data):
    rows = rows_of(mcp.call("data_dictionary_ping", {}))
    assert len(rows) == 1, rows
    catalog = len(spl("| inputlookup data_dictionary_catalog"))
    assert rows[0].get("app") == APP, rows[0]
    assert str(rows[0].get("ok")) == "true", rows[0]
    assert int(rows[0].get("catalog_rows")) == catalog, (rows[0], catalog)


def test_query_finds_the_probe_by_its_owner(mcp, probe_data):
    rows = rows_of(mcp.call("data_dictionary_query", {"q": PROBE_OWNER}))
    assert [(r.get("index"), r.get("sourcetype")) for r in rows] == [(PROBE_INDEX, PROBE_ST)], rows
    assert rows[0].get("data_owner") == PROBE_OWNER, rows[0]
    assert rows[0].get("data_category") == PROBE_CATEGORY, rows[0]


def test_query_without_a_match_returns_nothing(mcp, probe_data):
    assert rows_of(mcp.call("data_dictionary_query", {"q": PROBE + "-no-such-thing"})) == []


def test_index_metadata_returns_the_probe_index(mcp, probe_data):
    rows = rows_of(mcp.call("data_dictionary_index_metadata", {"index": PROBE_INDEX}))
    assert [r.get("sourcetype") for r in rows] == [PROBE_ST], rows
    assert rows[0].get("data_owner") == PROBE_OWNER, rows[0]
