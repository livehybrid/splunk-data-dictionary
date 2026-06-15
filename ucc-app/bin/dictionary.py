"""Data dictionary index endpoint for agents / Splunk MCP."""
import importlib.util
import json
import os
from urllib.parse import unquote

from splunk.persistconn.application import PersistentServerConnectionApplication

_bin_dir = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("common", os.path.join(_bin_dir, "common.py"))
common = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(common)
json_response = common.json_response
get_session_key = common.get_session_key
rest_get = common.rest_get
kv_base = common.kv_base
load_catalog_lookup = common.load_catalog_lookup

METADATA_FIELD_IDS = [
    "data_owner",
    "data_category",
    "pii_status",
    "export_classification",
    "service_owner",
    "security_owner",
    "escalation_contacts",
]


def _row_key(index, sourcetype):
    return "index_sourcetype:{}:{}".format(index or "", sourcetype or "")


def _normalize_catalog_row(r):
    if not isinstance(r, dict):
        return None
    index = r.get("index") or r.get("Index") or ""
    sourcetype = r.get("sourcetype") or r.get("Sourcetype") or ""
    frozen = r.get("frozenTimePeriodInSecs") or ""
    return {
        "index": index,
        "sourcetype": sourcetype,
        "frozenTimePeriodInSecs": frozen,
        "_key": _row_key(index, sourcetype),
    }


def _kv_map(session_key):
    """Return dict _key -> document for the metadata KV collection."""
    base = kv_base(session_key)
    status, data = rest_get(base, session_key)
    if status != 200:
        return None, data, status
    items = data if isinstance(data, list) else (data.get("item") or data.get("entry") or [])
    if not isinstance(items, list):
        items = []
    out = {}
    for m in items:
        if isinstance(m, dict) and m.get("_key"):
            out[m["_key"]] = m
    return out, None, 200


def _merge_row_metadata(meta_map, index, sourcetype):
    """Overlay index / sourcetype / row KV docs for display (row wins, then index, then sourcetype)."""
    rk = _row_key(index, sourcetype)
    ik = "index:{}".format(index) if index else ""
    sk = "sourcetype:{}".format(sourcetype) if sourcetype else ""
    row_doc = meta_map.get(rk) or {}
    idx_doc = meta_map.get(ik) or {}
    st_doc = meta_map.get(sk) or {}
    merged = {}
    for fid in METADATA_FIELD_IDS:
        v = row_doc.get(fid)
        if v is None or (isinstance(v, str) and not v.strip()):
            v = idx_doc.get(fid)
        if v is None or (isinstance(v, str) and not v.strip()):
            v = st_doc.get(fid)
        if v is not None and not (isinstance(v, str) and not str(v).strip()):
            merged[fid] = v
    return merged, row_doc, idx_doc, st_doc


class DictionaryIndexHandler(PersistentServerConnectionApplication):
    """GET /dictionary/index/<index> — catalog rows for index + KV metadata (index + merged per row)."""

    def __init__(self, command_line=None, command_arg=None):
        super(DictionaryIndexHandler, self).__init__()

    def handle(self, in_string):
        try:
            req = json.loads(in_string) if in_string else {}
            session_key = get_session_key(req)
            if not session_key:
                return json_response({"error": "Missing session key"}, status=401)
            method = str(req.get("method") or "GET").upper()
            if method != "GET":
                return json_response({"error": "Method not allowed"}, status=405)

            path = req.get("path_info") or req.get("path") or req.get("uri") or ""
            if isinstance(path, (bytes, bytearray)):
                path = path.decode("utf-8", errors="replace")
            path = str(path).split("?")[0].rstrip("/")
            for prefix in ("/data_dictionary/dictionary/index", "/dictionary/index"):
                if path == prefix or path.startswith(prefix + "/"):
                    path = path[len(prefix) :].lstrip("/")
                    break
            index_name = unquote(path.split("/")[0]) if path else ""
            if not index_name:
                return json_response({"error": "Index name required in path /dictionary/index/<index>"}, status=400)

            catalog = load_catalog_lookup(session_key)
            if catalog is None:
                return json_response(
                    {
                        "index": index_name,
                        "index_metadata": {},
                        "rows": [],
                        "message": "Catalog lookup is empty or search failed. Run or schedule the Data Dictionary catalog saved search to populate data_dictionary_catalog.",
                    }
                )

            meta_map, err, err_status = _kv_map(session_key)
            if meta_map is None:
                return json_response(
                    {"error": "KV metadata list failed", "detail": err, "index": index_name},
                    status=err_status if err_status != 200 else 500,
                )

            rows_out = []
            for raw in catalog:
                base = _normalize_catalog_row(raw)
                if not base or base["index"] != index_name:
                    continue
                merged, row_doc, idx_doc, st_doc = _merge_row_metadata(
                    meta_map, base["index"], base["sourcetype"]
                )
                rows_out.append(
                    {
                        "index": base["index"],
                        "sourcetype": base["sourcetype"],
                        "frozenTimePeriodInSecs": base["frozenTimePeriodInSecs"],
                        "_key": base["_key"],
                        "metadata": merged,
                        "metadata_sources": {
                            "row": bool(row_doc),
                            "index": bool(idx_doc and any(idx_doc.get(f) for f in METADATA_FIELD_IDS)),
                            "sourcetype": bool(st_doc and any(st_doc.get(f) for f in METADATA_FIELD_IDS)),
                        },
                    }
                )

            ik = "index:{}".format(index_name)
            index_kv = dict(meta_map.get(ik) or {})

            return json_response(
                {
                    "index": index_name,
                    "index_metadata": index_kv,
                    "row_count": len(rows_out),
                    "rows": rows_out,
                }
            )
        except Exception as e:
            return json_response({"error": str(e)}, status=500)
