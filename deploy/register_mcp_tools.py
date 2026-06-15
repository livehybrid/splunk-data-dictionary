#!/usr/bin/env python3
"""Register the Data Dictionary's MCP tools into the Splunk MCP Server from the
single source of truth: appserver/static/tool_input_payload_signatures.json.

The Splunk MCP Server does not read that file at call time - tools live in two KV
collections in the Splunk_MCP_Server app, registered once:
  - mcp_tools          : the full tool definition (name, schema, _meta.execution)
  - mcp_tools_enabled  : { _key: <name>, tool_id, collision_ids: [] }

Each tool is written with a FULL-doc replace (POST by _key), never a PUT/merge, so
a stale field from a previous shape can't linger (e.g. an old SPL `template` on a
now-API tool, which the loader rejects). `_meta.external_app_id` is immutable in
the loader, so the value in the signatures file must match what is already live.

Usage:  python3 deploy/register_mcp_tools.py            # register/enable all tools
        python3 deploy/register_mcp_tools.py --remove   # deregister (cleanup)
Env: SPLUNK_HOST (default 127.0.0.1), SPLUNK_PORT (default 8089),
     SPLUNK_PASSWORD (admin).
"""
import base64
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

HOST = os.environ.get("SPLUNK_HOST", "127.0.0.1").strip() or "127.0.0.1"
PORT = os.environ.get("SPLUNK_PORT", "8089").strip() or "8089"
PW = os.environ.get("SPLUNK_PASSWORD", "")
BASE = f"https://{HOST}:{PORT}/servicesNS/nobody/Splunk_MCP_Server/storage/collections/data"

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIG = os.path.join(REPO, "ucc-app", "appserver", "static", "tool_input_payload_signatures.json")


def _ctx():
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


def _req(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    r.add_header("Authorization", "Basic " + base64.b64encode(f"admin:{PW}".encode()).decode())
    try:
        with urllib.request.urlopen(r, context=_ctx(), timeout=30) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def _enc(key):
    return urllib.parse.quote(key, safe="")


def _tools():
    with open(SIG) as fh:
        return json.load(fh)


def register():
    for tool in _tools():
        name = tool["name"]
        tool_id = tool.get("tool_id") or f"data_dictionary:{name}"
        doc = dict(tool)
        doc["_key"] = tool_id
        doc["tool_id"] = tool_id
        doc.pop("_user", None)
        # Full-doc replace into mcp_tools.
        s, _ = _req("POST", f"{BASE}/mcp_tools/{_enc(tool_id)}", doc)
        if s >= 400:
            s, _ = _req("POST", f"{BASE}/mcp_tools", doc)
        # Enable.
        en = {"_key": name, "tool_id": tool_id, "collision_ids": []}
        s2, _ = _req("POST", f"{BASE}/mcp_tools_enabled/{_enc(name)}", en)
        if s2 >= 400:
            s2, _ = _req("POST", f"{BASE}/mcp_tools_enabled", en)
        print(f"  {name}: mcp_tools={s} enabled={s2} ({tool['_meta']['execution']['type']})")


def remove():
    for tool in _tools():
        name = tool["name"]
        tool_id = tool.get("tool_id") or f"data_dictionary:{name}"
        _req("DELETE", f"{BASE}/mcp_tools/{_enc(tool_id)}")
        _req("DELETE", f"{BASE}/mcp_tools_enabled/{_enc(name)}")
        print(f"  removed {name}")


if __name__ == "__main__":
    if not PW:
        print("SPLUNK_PASSWORD not set", file=sys.stderr)
        sys.exit(1)
    (remove if "--remove" in sys.argv else register)()
    print("done.")
