"""Options endpoint: run a macro or inputlookup search and return first column as options list for dropdowns."""
import json
import time

import splunk.rest as rest
from splunk.persistconn.application import PersistentServerConnectionApplication

import importlib.util
import os

_bin_dir = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("common", os.path.join(_bin_dir, "common.py"))
common = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(common)
json_response = common.json_response
get_session_key = common.get_session_key
rest_get = common.rest_get

POLL_INTERVAL = 0.3
POLL_TIMEOUT = 15


def _run_oneshot_and_get_first_column(session_key, search):
    """Run a oneshot search and return the first column values as a list."""
    response, content = rest.simpleRequest(
        "/services/search/jobs",
        sessionKey=session_key,
        method="POST",
        getargs={"output_mode": "json", "exec_mode": "oneshot"},
        postargs={"search": search},
        raiseAllErrors=False,
    )
    if response.status not in (200, 201):
        return None
    try:
        data = json.loads(content.decode("utf-8") if isinstance(content, (bytes, bytearray)) else content)
    except Exception:
        return None
    # Oneshot returns job info; we need results. Get sid and fetch results.
    sid = data.get("sid") or (data.get("entry") or [{}])[0].get("name") or (data.get("entry") or [{}])[0].get("id")
    if not sid:
        return None
    deadline = time.monotonic() + POLL_TIMEOUT
    while time.monotonic() < deadline:
        status, job_resp = rest_get("/services/search/jobs/{}".format(sid), session_key, getargs={"output_mode": "json"})
        if status != 200:
            return None
        entry = (job_resp.get("entry") or [{}])[0]
        content = entry.get("content") or {}
        if content.get("isDone"):
            break
        time.sleep(POLL_INTERVAL)
    else:
        return None
    status, results_resp = rest_get(
        "/services/search/jobs/{}/results".format(sid),
        session_key,
        getargs={"output_mode": "json", "count": "0"},
    )
    if status != 200:
        return None
    results = results_resp.get("results")
    if not isinstance(results, list):
        return []
    if not results:
        return []
    first = results[0]
    if not isinstance(first, dict):
        return []
    keys = list(first.keys())
    # Contact-style: name + email -> "Name (email)"
    if "name" in keys and "email" in keys:
        seen = set()
        options = []
        for row in results:
            name = (row.get("name") or "").strip()
            email = (row.get("email") or "").strip()
            if not name and not email:
                continue
            display = name + (" (" + email + ")" if email else "")
            if display and display not in seen:
                seen.add(display)
                options.append(display)
        return sorted(options)
    # Single column: prefer 'name', 'value', 'title', 'label', else first key
    col = next((k for k in ("name", "value", "title", "label") if k in keys), keys[0] if keys else None)
    if not col:
        return []
    seen = set()
    options = []
    for row in results:
        val = row.get(col)
        if val is None:
            continue
        s = str(val).strip()
        if s and s not in seen:
            seen.add(s)
            options.append(s)
    return sorted(options)


class OptionsHandler(PersistentServerConnectionApplication):
    def __init__(self, command_line=None, command_arg=None):
        super(OptionsHandler, self).__init__()

    def handle(self, in_string):
        try:
            req = json.loads(in_string) if in_string else {}
            session_key = get_session_key(req)
            if not session_key:
                return json_response({"error": "Missing session key"}, status=401)
            # Query params: macro=name or lookup=name (from query string or path)
            path = (req.get("path_info") or req.get("path") or req.get("uri") or "")
            if isinstance(path, (bytes, bytearray)):
                path = path.decode("utf-8", errors="replace")
            query = (req.get("query") or req.get("query_string") or "")
            if isinstance(query, (bytes, bytearray)):
                query = query.decode("utf-8", errors="replace")
            if "?" in path:
                _, q = path.split("?", 1)
                query = q or query
            from urllib.parse import parse_qs
            params = parse_qs(query) if query else {}
            macro = (params.get("macro") or [None])[0]
            lookup = (params.get("lookup") or [None])[0]
            if macro:
                # Invoke macro: | `macro_name`
                search = "| `{}`".format(macro.replace("`", ""))
            elif lookup:
                search = "| inputlookup {}".format(lookup.replace(" ", "").split(" ")[0])
            else:
                return json_response({"error": "Supply macro= or lookup= query parameter"}, status=400)
            options = _run_oneshot_and_get_first_column(session_key, search)
            if options is None:
                return json_response({"error": "Search failed", "options": []}, status=500)
            return json_response({"options": options})
        except Exception as e:
            return json_response({"error": str(e), "options": []}, status=500)
