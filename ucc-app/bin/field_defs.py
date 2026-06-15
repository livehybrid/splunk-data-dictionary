"""Metadata field-definition CRUD for the Data Dictionary.

Lets admins manage which governance fields exist (the standard ones plus their own
custom fields). GET returns the standard defaults merged with any KV overrides /
custom fields; POST upserts a definition; DELETE removes a KV override (reverting a
standard field to its default, or deleting a custom field).

Field types: "select" (customisable, value-suggesting dropdown) and "boolean"
(Yes/No). Optional `options_source` ({"type":"macro"|"lookup","name":...}) feeds a
select's suggestions; `options` is an explicit list.
"""
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

COLLECTION = "field_defs"

# The built-in governance fields (match the catalogue editor's current set).
STANDARD_FIELDS = [
    {"_key": "data_owner", "label": "Data Owner", "type": "select",
     "options_source": {"type": "macro", "name": "data_owner_list"}, "order": 10},
    {"_key": "data_category", "label": "Data Category", "type": "select", "order": 20},
    {"_key": "pii_status", "label": "PII Status", "type": "boolean", "order": 30},
    {"_key": "export_classification", "label": "Export Classification", "type": "select",
     "options_source": {"type": "lookup", "name": "export_classification_options"}, "order": 40},
    {"_key": "service_owner", "label": "Service Owner", "type": "select",
     "options_source": {"type": "macro", "name": "data_owner_list"}, "order": 50},
    {"_key": "security_owner", "label": "Security Owner", "type": "select",
     "options_source": {"type": "macro", "name": "data_owner_list"}, "order": 60},
    {"_key": "escalation_contacts", "label": "Escalation Contacts", "type": "select",
     "options_source": {"type": "macro", "name": "operation_contacts_list"}, "order": 70},
]


def _normalize_path(req):
    path = req.get("path_info") or req.get("path") or req.get("uri") or ""
    if isinstance(path, (bytes, bytearray)):
        path = path.decode("utf-8", errors="replace")
    path = str(path).split("?")[0].rstrip("/")
    for prefix in ("/data_dictionary/field-defs", "/field-defs"):
        if path == prefix or path.startswith(prefix + "/"):
            path = path[len(prefix):].lstrip("/")
            break
    # For the wildcard (field-defs/*) stanza Splunk may pass just the key, so if no
    # prefix matched the path is already the key - return it as-is.
    return path.lstrip("/")


def _kv_doc_to_def(doc):
    out = {"_key": doc.get("_key"), "label": doc.get("label"), "type": doc.get("type"),
           "order": doc.get("order"), "standard": bool(doc.get("standard")),
           "hidden": bool(doc.get("hidden"))}
    for jsonfield in ("options", "options_source"):
        v = doc.get(jsonfield)
        if isinstance(v, str) and v.strip():
            try:
                out[jsonfield] = json.loads(v)
            except Exception:
                out[jsonfield] = v
        elif v is not None:
            out[jsonfield] = v
    return out


def _merged_defs(session_key):
    """Standard defaults overlaid with KV overrides, plus custom (KV-only) fields."""
    base = kv_base(session_key, COLLECTION)
    status, data = rest_get(base, session_key)
    kv_items = data if isinstance(data, list) else (data.get("item") or data.get("entry") or []) if isinstance(data, dict) else []
    kv_by_key = {d["_key"]: _kv_doc_to_def(d) for d in kv_items if isinstance(d, dict) and d.get("_key")}
    out = []
    seen = set()
    for std in STANDARD_FIELDS:
        merged = dict(std, standard=True)
        if std["_key"] in kv_by_key:
            for k, v in kv_by_key[std["_key"]].items():
                if v is not None:
                    merged[k] = v
            merged["standard"] = True
        out.append(merged)
        seen.add(std["_key"])
    for key, d in kv_by_key.items():
        if key not in seen:
            d["standard"] = False
            out.append(d)
    out.sort(key=lambda f: (f.get("order") if isinstance(f.get("order"), (int, float)) else 999, f.get("_key") or ""))
    return out


class FieldDefsHandler(PersistentServerConnectionApplication):
    def __init__(self, command_line=None, command_arg=None):
        super(FieldDefsHandler, self).__init__()

    def handle(self, in_string):
        try:
            req = json.loads(in_string) if in_string else {}
            session_key = get_session_key(req)
            if not session_key:
                return json_response({"error": "Missing session key"}, status=401)
            method = str(req.get("method") or "GET").upper()
            path = _normalize_path(req)
            base = kv_base(session_key, COLLECTION)

            if not path:
                if method != "GET":
                    return json_response({"error": "Method not allowed"}, status=405)
                return json_response({"field_defs": _merged_defs(session_key)})

            key = unquote(path.split("/")[0])
            keyed = "{}/{}".format(base, quote(key, safe=""))

            if method in ("POST", "PUT", "DELETE"):
                denied = forbidden_if_cannot_edit(session_key)
                if denied is not None:
                    return denied

            if method in ("POST", "PUT"):
                body = parse_body(req)
                doc = {"_key": key, "label": body.get("label") or key,
                       "type": body.get("type") or "select",
                       "standard": bool(body.get("standard")),
                       "hidden": bool(body.get("hidden")),
                       "order": body.get("order"),
                       "updated_at": int(time.time()),
                       "updated_by": current_user(session_key) or "unknown"}
                for jsonfield in ("options", "options_source"):
                    if body.get(jsonfield) is not None:
                        doc[jsonfield] = json.dumps(body[jsonfield]) if not isinstance(body[jsonfield], str) else body[jsonfield]
                status, data = _kvstore_post_json("{}/batch_save".format(base), get_system_key(req), [doc])
                return json_response(data, status=status)
            if method == "DELETE":
                status, data = rest_delete(keyed, get_system_key(req))
                return json_response(data, status=status)
            return json_response({"error": "Method not allowed"}, status=405)
        except Exception as e:
            return json_response({"error": str(e)}, status=500)
