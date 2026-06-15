"""Shared helpers for Data Dictionary REST handlers."""
import json
import ssl
import time
from http.client import HTTPSConnection, HTTPException
from urllib.parse import parse_qs

import splunk.rest as rest

SEARCH_INPUTLOOKUP_CATALOG = "| inputlookup data_dictionary_catalog"
CATALOG_POLL_INTERVAL = 0.5
CATALOG_POLL_TIMEOUT = 30

APP = 'data_dictionary'
KV_COLLECTION = 'metadata'


def json_response(payload, status=200):
    return {
        'status': status,
        'payload': json.dumps(payload),
        'headers': {'Content-Type': 'application/json'},
    }


def get_session_key(req):
    if not isinstance(req, dict):
        return None
    sess = req.get('session', {})
    if isinstance(sess, dict):
        sk = sess.get('authtoken') or sess.get('sessionKey') or sess.get('session_key')
        if sk and isinstance(sk, str):
            return sk
    for key in ('sessionKey', 'session_key'):
        if isinstance(req.get(key), str) and req.get(key):
            return req.get(key)
    headers = req.get('headers') or {}
    if isinstance(headers, dict):
        auth = headers.get('Authorization') or headers.get('authorization') or ''
        if isinstance(auth, str) and auth.startswith('Splunk '):
            token = auth[7:].strip()
            if token:
                return token
    return None


def get_system_key(req):
    """System auth token (from restmap passSystemAuth=true) for privileged KV
    writes performed AFTER an app-level capability check. The KV collections are
    ACL-locked to admin/sc_admin, so editing by a capability-holder who is not a
    collection-ACL admin has to run with system auth - the edit_data_dictionary
    capability is the access control, not the collection ACL. Falls back to the
    user's session key if no system token is present.
    """
    if isinstance(req, dict):
        sk = req.get('system_authtoken')
        if isinstance(sk, str) and sk:
            return sk
    return get_session_key(req)


def query_params(req):
    """Return {name: [values]} from a persistent-handler request.

    Robust to every shape Splunk uses for query params:
      * req['query'] as a list of [name, value] pairs (the form splunkd uses on
        the mgmt port 8089, i.e. when an MCP 'api' tool calls us with params=...);
      * req['query'] / req['query_string'] as a raw URL-encoded string;
      * a '?...' suffix tacked onto path_info (the Splunk Web :8000 proxy form).
    """
    q = req.get('query')
    if isinstance(q, (list, tuple)):
        out = {}
        for pair in q:
            if isinstance(pair, (list, tuple)) and pair:
                k = str(pair[0])
                v = pair[1] if len(pair) > 1 else ''
                out.setdefault(k, []).append('' if v is None else str(v))
        return out
    if isinstance(q, (bytes, bytearray)):
        q = q.decode('utf-8', errors='replace')
    if not isinstance(q, str) or not q:
        q = req.get('query_string') or ''
        if isinstance(q, (bytes, bytearray)):
            q = q.decode('utf-8', errors='replace')
    if not isinstance(q, str):
        q = ''
    if not q:
        path = req.get('path_info') or req.get('path') or req.get('uri') or ''
        if isinstance(path, (bytes, bytearray)):
            path = path.decode('utf-8', errors='replace')
        path = str(path)
        if '?' in path:
            q = path.split('?', 1)[1]
    return parse_qs(q) if q else {}


def parse_body(req):
    raw = req.get('payload')
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode('utf-8', errors='replace')
    if not raw or not isinstance(raw, str):
        return {}
    raw = raw.strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        pass
    try:
        parsed = parse_qs(raw, keep_blank_values=True)
        return {k: (v[0] if v else '') for k, v in parsed.items()}
    except Exception:
        pass
    return {}


def rest_get(path, session_key, getargs=None):
    response, content = rest.simpleRequest(
        path,
        sessionKey=session_key,
        method='GET',
        getargs=getargs or {},
        raiseAllErrors=False,
    )
    body = content.decode('utf-8') if isinstance(content, (bytes, bytearray)) else str(content)
    try:
        return response.status, json.loads(body) if body else {}
    except Exception:
        return response.status, {'raw': body}


def rest_post(path, session_key, body=None, getargs=None):
    postargs = {}
    if body is not None:
        # KV store expects JSON; support dict, list, or already-serialized string
        postargs['__json'] = json.dumps(body) if not isinstance(body, str) else body
    response, content = rest.simpleRequest(
        path,
        sessionKey=session_key,
        method='POST',
        getargs=getargs or {},
        postargs=postargs,
        raiseAllErrors=False,
    )
    resp_body = content.decode('utf-8') if isinstance(content, (bytes, bytearray)) else str(content)
    try:
        return response.status, json.loads(resp_body) if resp_body else {}
    except Exception:
        return response.status, {'raw': resp_body}


def _kvstore_post_json(path, session_key, json_body):
    """POST raw JSON to a KV store path (e.g. batch_save). KV store requires Content-Type: application/json."""
    host = '127.0.0.1'
    port = 8089
    payload = json.dumps(json_body) if not isinstance(json_body, str) else json_body
    body_bytes = payload.encode('utf-8')
    headers = {
        'Authorization': 'Splunk %s' % session_key,
        'Content-Type': 'application/json',
        'Content-Length': str(len(body_bytes)),
    }
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    conn = HTTPSConnection(host, port, timeout=30, context=ctx)
    try:
        conn.request('POST', path, body=body_bytes, headers=headers)
        resp = conn.getresponse()
        status = resp.status
        body = resp.read().decode('utf-8')
        try:
            return status, json.loads(body) if body else {}
        except Exception:
            return status, {'raw': body}
    except HTTPException as e:
        return 500, {'raw': str(e)}
    except Exception as e:
        return 500, {'raw': str(e)}
    finally:
        conn.close()


def rest_delete(path, session_key):
    response, content = rest.simpleRequest(
        path,
        sessionKey=session_key,
        method='DELETE',
        raiseAllErrors=False,
    )
    body = content.decode('utf-8') if isinstance(content, (bytes, bytearray)) else str(content)
    try:
        return response.status, json.loads(body) if body else {}
    except Exception:
        return response.status, {'raw': body}


def kv_base(session_key, collection=None):
    return '/servicesNS/nobody/{}/storage/collections/data/{}'.format(
        APP, collection or KV_COLLECTION
    )


def load_catalog_lookup(session_key):
    """
    Run | inputlookup data_dictionary_catalog and return result rows (list of dicts), or None on failure.
    Shared by discovery_catalog and dictionary MCP-oriented endpoints.
    """
    response, content = rest.simpleRequest(
        "/services/search/jobs",
        sessionKey=session_key,
        method="POST",
        getargs={"output_mode": "json"},
        postargs={"search": SEARCH_INPUTLOOKUP_CATALOG},
        raiseAllErrors=False,
    )
    if response.status not in (200, 201):
        return None
    try:
        create_resp = json.loads(content.decode("utf-8") if isinstance(content, (bytes, bytearray)) else content)
    except Exception:
        return None
    sid = create_resp.get("sid") or ((create_resp.get("entry") or [{}])[0].get("name"))
    if not sid:
        return None
    deadline = time.monotonic() + CATALOG_POLL_TIMEOUT
    while time.monotonic() < deadline:
        status, job_resp = rest_get(
            "/services/search/jobs/{}".format(sid),
            session_key,
            getargs={"output_mode": "json"},
        )
        if status != 200:
            return None
        entry = (job_resp.get("entry") or [{}])[0]
        content = entry.get("content") or {}
        if content.get("isDone"):
            break
        time.sleep(CATALOG_POLL_INTERVAL)
    else:
        return None
    status, results_resp = rest_get(
        "/services/search/jobs/{}/results".format(sid),
        session_key,
        getargs={"output_mode": "json", "count": "0"},
    )
    if status != 200:
        return None
    results = results_resp.get("results") if isinstance(results_resp.get("results"), list) else []
    return results


def run_oneshot_search(session_key, search, earliest=None, latest=None, max_count=0):
    """
    Run an arbitrary SPL search via /services/search/jobs and return result rows
    (list of dicts) or None on failure.
    """
    postargs = {"search": search}
    if earliest:
        postargs["earliest_time"] = earliest
    if latest:
        postargs["latest_time"] = latest
    response, content = rest.simpleRequest(
        "/services/search/jobs",
        sessionKey=session_key,
        method="POST",
        getargs={"output_mode": "json"},
        postargs=postargs,
        raiseAllErrors=False,
    )
    if response.status not in (200, 201):
        return None
    try:
        create_resp = json.loads(content.decode("utf-8") if isinstance(content, (bytes, bytearray)) else content)
    except Exception:
        return None
    sid = create_resp.get("sid") or ((create_resp.get("entry") or [{}])[0].get("name"))
    if not sid:
        return None
    deadline = time.monotonic() + CATALOG_POLL_TIMEOUT
    while time.monotonic() < deadline:
        status, job_resp = rest_get(
            "/services/search/jobs/{}".format(sid),
            session_key,
            getargs={"output_mode": "json"},
        )
        if status != 200:
            return None
        entry = (job_resp.get("entry") or [{}])[0]
        c = entry.get("content") or {}
        if c.get("isDone"):
            break
        time.sleep(CATALOG_POLL_INTERVAL)
    else:
        return None
    status, results_resp = rest_get(
        "/services/search/jobs/{}/results".format(sid),
        session_key,
        getargs={"output_mode": "json", "count": str(max_count)},
    )
    if status != 200:
        return None
    return results_resp.get("results") if isinstance(results_resp.get("results"), list) else []


def current_context(session_key):
    """Return (username, roles, capabilities) for the calling user.

    One call to /services/authentication/current-context; empty tuple on failure.
    """
    try:
        status, data = rest_get('/services/authentication/current-context', session_key, getargs={'output_mode': 'json'})
        if status != 200:
            return '', [], []
        content = ((data.get('entry') or [{}])[0].get('content')) or {}
        username = content.get('username') or content.get('realname') or ''
        roles = content.get('roles') or []
        caps = content.get('capabilities') or []
        if isinstance(roles, str):
            roles = [roles]
        if isinstance(caps, str):
            caps = [caps]
        return username, list(roles), list(caps)
    except Exception:
        return '', [], []


def current_user(session_key):
    return current_context(session_key)[0]


# Custom capability gating all Data Dictionary metadata edits. Granted to admin
# in authorize.conf; admins assign it to whichever roles should be able to edit.
EDIT_CAPABILITY = 'edit_data_dictionary'


def user_can_edit(session_key):
    """True if the caller may mutate dictionary metadata / field definitions.

    Either they hold the explicit edit_data_dictionary capability, or they are a
    full admin (admin_all_objects) - so superusers are never locked out even
    before the capability is assigned to any role.
    """
    _, _roles, caps = current_context(session_key)
    return EDIT_CAPABILITY in caps or 'admin_all_objects' in caps


def forbidden_if_cannot_edit(session_key):
    """Return a 403 json_response if the caller lacks edit rights, else None."""
    if user_can_edit(session_key):
        return None
    return json_response(
        {
            'error': 'forbidden',
            'message': 'You do not have permission to edit the Data Dictionary. '
                       'Ask an administrator to grant the "{}" capability to your role.'.format(EDIT_CAPABILITY),
            'capability': EDIT_CAPABILITY,
        },
        status=403,
    )
