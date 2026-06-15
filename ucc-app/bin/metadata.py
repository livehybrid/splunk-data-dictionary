"""Metadata CRUD endpoint for Data Dictionary."""
import importlib.util
import json
import os
import time
from urllib.parse import quote, unquote

from splunk.persistconn.application import PersistentServerConnectionApplication

_bin_dir = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("common", os.path.join(_bin_dir, "common.py"))
common = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(common)
json_response = common.json_response
get_session_key = common.get_session_key
get_system_key = common.get_system_key
parse_body = common.parse_body
rest_get = common.rest_get
rest_delete = common.rest_delete
kv_base = common.kv_base
current_user = common.current_user
forbidden_if_cannot_edit = common.forbidden_if_cannot_edit
_kvstore_post_json = common._kvstore_post_json


def _normalize_path(req):
    path = req.get('path_info') or req.get('path') or req.get('uri') or ''
    if isinstance(path, (bytes, bytearray)):
        path = path.decode('utf-8', errors='replace')
    path = str(path).split('?')[0].rstrip('/')
    # Strip leading /metadata or /data_dictionary/.../metadata
    for prefix in ('/data_dictionary/metadata', '/metadata'):
        if path == prefix or path.startswith(prefix + '/'):
            path = path[len(prefix):].lstrip('/')
            break
    return path


class MetadataHandler(PersistentServerConnectionApplication):
    def __init__(self, command_line=None, command_arg=None):
        super(MetadataHandler, self).__init__()

    def handle(self, in_string):
        try:
            req = json.loads(in_string) if in_string else {}
            session_key = get_session_key(req)
            if not session_key:
                return json_response({'error': 'Missing session key'}, status=401)
            method = str(req.get('method') or 'GET').upper()
            path = _normalize_path(req)
            body = parse_body(req)
            base = kv_base(session_key)

            # List: GET /metadata
            if not path or path == '':
                if method != 'GET':
                    return json_response({'error': 'Method not allowed'}, status=405)
                status, data = rest_get(base, session_key)
                if status != 200:
                    return json_response(data, status=status)
                items = data if isinstance(data, list) else (data.get('item') or data.get('entry') or [])
                if not isinstance(items, list):
                    items = []
                return json_response({'metadata': items})

            # Keyed: GET/POST/PUT/DELETE /metadata/<key>
            raw_key = path.split('/')[0] if path else ''
            key = unquote(raw_key) if raw_key else ''
            if not key:
                return json_response({'error': 'Metadata key required'}, status=400)
            keyed_path = '{}/{}'.format(base, quote(key, safe=''))

            if method == 'GET':
                try:
                    status, data = rest_get(keyed_path, session_key)
                    if status == 404:
                        return json_response({'_key': key})
                    return json_response(data, status=status)
                except Exception as e:
                    err = str(e)
                    if '404' in err or 'Could not find object' in err or 'not find' in err.lower():
                        return json_response({'_key': key})
                    raise
            if method in ('POST', 'PUT'):
                denied = forbidden_if_cannot_edit(session_key)
                if denied is not None:
                    return denied
                doc = dict(body)
                doc['_key'] = key
                doc['updated_at'] = int(time.time())
                doc['updated_by'] = current_user(session_key) or 'unknown'
                # Capability check passed; perform the write with system auth so a
                # capability-holder who is not a collection-ACL admin can still save.
                # Use KV store batch_save for upsert: create if missing, update if exists.
                # KV store requires Content-Type: application/json and raw JSON; use _kvstore_post_json.
                batch_path = '{}/batch_save'.format(base)
                status, data = _kvstore_post_json(batch_path, get_system_key(req), [doc])
                return json_response(data, status=status)
            if method == 'DELETE':
                denied = forbidden_if_cannot_edit(session_key)
                if denied is not None:
                    return denied
                status, data = rest_delete(keyed_path, get_system_key(req))
                return json_response(data, status=status)
            return json_response({'error': 'Method not allowed'}, status=405)
        except Exception as e:
            return json_response({'error': str(e)}, status=500)
