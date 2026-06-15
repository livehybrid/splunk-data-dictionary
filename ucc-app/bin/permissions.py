"""Report the caller's Data Dictionary permissions to the UI.

GET /data_dictionary/permissions -> { username, can_edit, capability, roles }

The UI uses can_edit to hide / disable the edit controls. The server endpoints
enforce the same capability independently, so this is purely a UX hint.
"""
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
current_context = common.current_context
user_can_edit = common.user_can_edit
EDIT_CAPABILITY = common.EDIT_CAPABILITY


class PermissionsHandler(PersistentServerConnectionApplication):
    def __init__(self, command_line=None, command_arg=None):
        super(PermissionsHandler, self).__init__()

    def handle(self, in_string):
        try:
            req = json.loads(in_string) if in_string else {}
            session_key = get_session_key(req)
            if not session_key:
                return json_response({"error": "Missing session key"}, status=401)
            username, roles, _caps = current_context(session_key)
            return json_response(
                {
                    "username": username,
                    "roles": roles,
                    "can_edit": user_can_edit(session_key),
                    "capability": EDIT_CAPABILITY,
                }
            )
        except Exception as e:
            return json_response({"error": str(e)}, status=500)
