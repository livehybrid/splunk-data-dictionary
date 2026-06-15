"""Dispatch the Data Dictionary catalog-build saved search.

The home page "Run catalog search" button POSTs here to (re)populate the
data_dictionary_catalog lookup on demand instead of waiting for the schedule.
"""
import importlib.util
import json
import os
from urllib.parse import quote

import splunk.rest as rest
from splunk.persistconn.application import PersistentServerConnectionApplication

_bin_dir = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("common", os.path.join(_bin_dir, "common.py"))
common = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(common)
json_response = common.json_response
get_session_key = common.get_session_key
get_system_key = common.get_system_key
forbidden_if_cannot_edit = common.forbidden_if_cannot_edit

APP = "data_dictionary"
SAVED_SEARCH = "Data Dictionary - Build Catalog"


class BuildCatalogHandler(PersistentServerConnectionApplication):
    def __init__(self, command_line=None, command_arg=None):
        super(BuildCatalogHandler, self).__init__()

    def handle(self, in_string):
        try:
            req = json.loads(in_string) if in_string else {}
            session_key = get_session_key(req)
            if not session_key:
                return json_response({"error": "Missing session key"}, status=401)
            method = str(req.get("method") or "POST").upper()
            if method not in ("POST", "GET"):
                return json_response({"error": "Method not allowed"}, status=405)

            denied = forbidden_if_cannot_edit(session_key)
            if denied is not None:
                return denied

            path = "/servicesNS/nobody/{}/saved/searches/{}/dispatch".format(
                APP, quote(SAVED_SEARCH, safe="")
            )
            # Capability check passed; dispatch with system auth so a capability-holder
            # who is not a saved-search/lookup-ACL admin can still rebuild the catalog.
            response, content = rest.simpleRequest(
                path,
                sessionKey=get_system_key(req),
                method="POST",
                postargs={"trigger_actions": "0", "output_mode": "json"},
                raiseAllErrors=False,
            )
            if response.status not in (200, 201):
                detail = (
                    content.decode("utf-8", "replace")
                    if isinstance(content, (bytes, bytearray))
                    else str(content)
                )
                status = response.status if response.status >= 400 else 500
                return json_response(
                    {
                        "error": "Failed to dispatch saved search",
                        "status": response.status,
                        "detail": detail[:500],
                    },
                    status=status,
                )

            sid = None
            try:
                data = json.loads(
                    content.decode("utf-8") if isinstance(content, (bytes, bytearray)) else content
                )
                sid = data.get("sid") or (data.get("entry") or [{}])[0].get("name")
            except Exception:
                pass
            return json_response({"dispatched": True, "sid": sid, "saved_search": SAVED_SEARCH})
        except Exception as e:
            return json_response({"error": str(e)}, status=500)
