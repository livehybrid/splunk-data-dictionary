"""Ping endpoint for Data Dictionary."""
import importlib.util
import json
import os

from splunk.persistconn.application import PersistentServerConnectionApplication

# Load common from same directory (Splunk does not add app bin/ to sys.path)
_bin_dir = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("common", os.path.join(_bin_dir, "common.py"))
common = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(common)
json_response = common.json_response
get_session_key = common.get_session_key

APP = 'data_dictionary_for_splunk'


class PingHandler(PersistentServerConnectionApplication):
    def __init__(self, command_line=None, command_arg=None):
        super(PingHandler, self).__init__()

    def handle(self, in_string):
        try:
            req = json.loads(in_string) if in_string else {}
            session_key = get_session_key(req)
            if not session_key:
                return json_response({'error': 'Missing session key'}, status=401)
            return json_response({'ok': True, 'app': APP})
        except Exception as e:
            return json_response({'error': str(e)}, status=500)
