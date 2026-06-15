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
query_params = common.query_params

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


_BOOKKEEPING = {"_key", "_user", "updated_by", "updated_at"}


def _has_governance(doc):
    """True if the KV doc carries any non-bookkeeping field with a value - i.e. it
    actually contributes governance metadata (standard or custom), not just a key."""
    return any(
        k not in _BOOKKEEPING and v not in (None, "") and str(v).strip()
        for k, v in (doc or {}).items()
    )


def _merge_row_metadata(meta_map, index, sourcetype):
    """Overlay index / sourcetype / row KV docs (row wins, then index, then sourcetype).

    Merges ALL governance fields present (standard + admin-defined custom), so
    custom fields flow through to agents too.
    """
    rk = _row_key(index, sourcetype)
    ik = "index:{}".format(index) if index else ""
    sk = "sourcetype:{}".format(sourcetype) if sourcetype else ""
    row_doc = meta_map.get(rk) or {}
    idx_doc = meta_map.get(ik) or {}
    st_doc = meta_map.get(sk) or {}
    field_ids = set()
    for d in (row_doc, idx_doc, st_doc):
        field_ids.update(k for k in d.keys() if k not in _BOOKKEEPING)
    merged = {}
    for fid in field_ids:
        v = row_doc.get(fid)
        if v is None or (isinstance(v, str) and not v.strip()):
            v = idx_doc.get(fid)
        if v is None or (isinstance(v, str) and not v.strip()):
            v = st_doc.get(fid)
        if v is not None and not (isinstance(v, str) and not str(v).strip()):
            merged[fid] = v
    return merged, row_doc, idx_doc, st_doc


class DictionaryIndexHandler(PersistentServerConnectionApplication):
    """GET /dictionary/index/<index> - catalog rows for index + KV metadata (index + merged per row)."""

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

            raw_path = req.get("path_info") or req.get("path") or req.get("uri") or ""
            if isinstance(raw_path, (bytes, bytearray)):
                raw_path = raw_path.decode("utf-8", errors="replace")
            raw_path = str(raw_path)
            params = query_params(req)
            flat = str((params.get("flat") or params.get("mcp") or [""])[0]).strip().lower() in ("1", "true", "yes")

            path = raw_path.split("?")[0].rstrip("/")
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
                            "row": _has_governance(row_doc),
                            "index": _has_governance(idx_doc),
                            "sourcetype": _has_governance(st_doc),
                        },
                    }
                )

            ik = "index:{}".format(index_name)
            index_kv = dict(meta_map.get(ik) or {})

            if flat:
                # Bare array of flattened rows for the MCP 'api' execution type,
                # which turns a JSON list into the tool's result rows. The index's
                # own metadata is folded into each row under index_* keys so an
                # agent sees both the per-sourcetype merge and the index defaults.
                index_meta = {
                    "index_" + k: v
                    for k, v in index_kv.items()
                    if k not in _BOOKKEEPING
                }
                flat_rows = [
                    dict(
                        {
                            "index": r["index"],
                            "sourcetype": r["sourcetype"],
                            "frozenTimePeriodInSecs": r["frozenTimePeriodInSecs"],
                            "_key": r["_key"],
                        },
                        **index_meta,
                        **r["metadata"],
                    )
                    for r in rows_out
                ]
                return json_response(flat_rows)

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
