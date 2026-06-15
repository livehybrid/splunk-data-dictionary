"""Discovery indexes endpoint for Data Dictionary."""
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
rest_get = common.rest_get


class DiscoveryIndexesHandler(PersistentServerConnectionApplication):
    def __init__(self, command_line=None, command_arg=None):
        super(DiscoveryIndexesHandler, self).__init__()

    def handle(self, in_string):
        try:
            req = json.loads(in_string) if in_string else {}
            session_key = get_session_key(req)
            if not session_key:
                return json_response({'error': 'Missing session key'}, status=401)
            path = '/services/data/indexes'
            status, data = rest_get(path, session_key, getargs={'output_mode': 'json', 'count': '0'})
            if status != 200:
                return json_response(data, status=status)
            entries = data.get('entry') or []
            return json_response({
                'indexes': [
                    {
                        'name': e.get('name'),
                        'totalEventCount': e.get('content', {}).get('totalEventCount'),
                        'currentDBSizeMB': e.get('content', {}).get('currentDBSizeMB'),
                    }
                    for e in entries
                ],
            })
        except Exception as e:
            return json_response({'error': str(e)}, status=500)
