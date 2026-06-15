"""Discovery catalog endpoint: runs inputlookup data_dictionary_catalog and returns JSON."""
import importlib.util
import json
import os

from splunk.persistconn.application import PersistentServerConnectionApplication

_bin_dir = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("common", os.path.join(_bin_dir, "common.py"))
common = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(common)
json_response = common.json_response
get_session_key = common.get_session_key
load_catalog_lookup = common.load_catalog_lookup


class DiscoveryCatalogHandler(PersistentServerConnectionApplication):
    def __init__(self, command_line=None, command_arg=None):
        super(DiscoveryCatalogHandler, self).__init__()

    def handle(self, in_string):
        try:
            req = json.loads(in_string) if in_string else {}
            session_key = get_session_key(req)
            if not session_key:
                return json_response({"error": "Missing session key"}, status=401)
            results = load_catalog_lookup(session_key)
            if results is None:
                return json_response({
                    "catalog": [],
                    "message": "Catalog lookup is empty or search failed. Run or schedule the Data Dictionary catalog saved search to populate the lookup.",
                })
            return json_response({"catalog": results})
        except Exception as e:
            return json_response({"error": str(e), "catalog": []}, status=500)
