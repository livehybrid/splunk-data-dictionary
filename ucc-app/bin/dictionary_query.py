"""Data dictionary query endpoint for agents / Splunk MCP."""
import importlib.util
import json
import os
from urllib.parse import parse_qs

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

QUERY_LIMIT_DEFAULT = 100
QUERY_LIMIT_MAX = 500


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
    return merged


def _parse_query_string(req):
    path = req.get("path_info") or req.get("path") or req.get("uri") or ""
    if isinstance(path, (bytes, bytearray)):
        path = path.decode("utf-8", errors="replace")
    query = req.get("query") or req.get("query_string") or ""
    if isinstance(query, (bytes, bytearray)):
        query = query.decode("utf-8", errors="replace")
    if "?" in path:
        _, q = path.split("?", 1)
        query = q or query
    return parse_qs(query) if query else {}


def _int_param(params, name, default, min_v, max_v):
    raw = (params.get(name) or [None])[0]
    if raw is None or raw == "":
        return default
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return default
    return max(min_v, min(max_v, v))


def _row_matches_query(merged, base_row, q_lower):
    if not q_lower:
        return True
    blob = " ".join(
        str(x).lower()
        for x in [
            base_row.get("index"),
            base_row.get("sourcetype"),
            base_row.get("frozenTimePeriodInSecs"),
        ]
        + [merged.get(f) for f in METADATA_FIELD_IDS]
    )
    return q_lower in blob


class DictionaryQueryHandler(PersistentServerConnectionApplication):
    """GET /dictionary/query — filter catalog + merged metadata."""

    def __init__(self, command_line=None, command_arg=None):
        super(DictionaryQueryHandler, self).__init__()

    def handle(self, in_string):
        try:
            req = json.loads(in_string) if in_string else {}
            session_key = get_session_key(req)
            if not session_key:
                return json_response({"error": "Missing session key"}, status=401)
            method = str(req.get("method") or "GET").upper()
            if method != "GET":
                return json_response({"error": "Method not allowed"}, status=405)

            params = _parse_query_string(req)
            q_raw = (params.get("q") or params.get("query") or [""])[0] or ""
            q_lower = q_raw.strip().lower()
            index_filter = (params.get("index") or [""])[0] or ""
            st_filter = (params.get("sourcetype") or [""])[0] or ""
            limit = _int_param(params, "limit", QUERY_LIMIT_DEFAULT, 1, QUERY_LIMIT_MAX)
            offset = _int_param(params, "offset", 0, 0, 100000)

            catalog = load_catalog_lookup(session_key)
            if catalog is None:
                return json_response(
                    {
                        "total": 0,
                        "returned": 0,
                        "results": [],
                        "message": "Catalog lookup is empty or search failed. Run or schedule the Data Dictionary catalog saved search to populate data_dictionary_catalog.",
                    }
                )

            meta_map, err, err_status = _kv_map(session_key)
            if meta_map is None:
                return json_response(
                    {"error": "KV metadata list failed", "detail": err},
                    status=err_status if err_status != 200 else 500,
                )

            built = []
            for raw in catalog:
                base = _normalize_catalog_row(raw)
                if not base:
                    continue
                if index_filter and base["index"] != index_filter:
                    continue
                if st_filter and base["sourcetype"] != st_filter:
                    continue
                merged = _merge_row_metadata(meta_map, base["index"], base["sourcetype"])
                if not _row_matches_query(merged, base, q_lower):
                    continue
                built.append(
                    {
                        "index": base["index"],
                        "sourcetype": base["sourcetype"],
                        "frozenTimePeriodInSecs": base["frozenTimePeriodInSecs"],
                        "_key": base["_key"],
                        "metadata": merged,
                    }
                )

            total = len(built)
            page = built[offset : offset + limit]

            return json_response(
                {
                    "query": {
                        "q": q_raw,
                        "index": index_filter or None,
                        "sourcetype": st_filter or None,
                        "limit": limit,
                        "offset": offset,
                    },
                    "total": total,
                    "returned": len(page),
                    "results": page,
                }
            )
        except Exception as e:
            return json_response({"error": str(e)}, status=500)
