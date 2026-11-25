#!/usr/bin/env python3
"""Download one release of a Splunkbase app, for the integration harness.

    SPLUNKBASE_USERNAME=... SPLUNKBASE_PASSWORD=... \
        python3 scripts/fetch-splunkbase-app.py 7931 2.1.0 vendor/Splunk_MCP_Server.tgz

Used by CI to fetch the Splunk MCP Server (Splunkbase app 7931), which is
third-party and never committed. Logs in with the account the repo already
holds for publishing, downloads the release tarball and checks it is a gzip
tarball whose top directory is the expected app id (EXPECT_APP_ID, default
Splunk_MCP_Server). Credentials and the session token are never printed.

Exits non-zero on any failure: CI only runs this where the secrets exist, so a
missing download is a broken pipeline, not a reason to skip the MCP tests.
"""
import os
import re
import sys
import tarfile
import urllib.error
import urllib.parse
import urllib.request

LOGIN = "https://splunkbase.splunk.com/api/account:login"
DOWNLOAD = "https://splunkbase.splunk.com/app/{app}/release/{version}/download/"


def main(argv):
    if len(argv) != 4:
        sys.exit("usage: fetch-splunkbase-app.py <app id> <version> <output .tgz>")
    app, version, out = argv[1], argv[2], argv[3]
    user = os.environ.get("SPLUNKBASE_USERNAME", "")
    pw = os.environ.get("SPLUNKBASE_PASSWORD", "")
    if not (user and pw):
        sys.exit("SPLUNKBASE_USERNAME / SPLUNKBASE_PASSWORD are not set")

    data = urllib.parse.urlencode({"username": user, "password": pw}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(LOGIN, data=data), timeout=60) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        sys.exit(f"Splunkbase login failed: HTTP {e.code}")
    m = re.search(r"<id>([^<]+)</id>", body)
    if not m:
        sys.exit("Splunkbase login returned no session token")

    url = DOWNLOAD.format(app=app, version=version)
    req = urllib.request.Request(url, headers={"X-Auth-Token": m.group(1)})
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    try:
        with urllib.request.urlopen(req, timeout=300) as r, open(out, "wb") as fh:
            fh.write(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"download of app {app} {version} failed: HTTP {e.code}")

    want = os.environ.get("EXPECT_APP_ID", "Splunk_MCP_Server")
    try:
        with tarfile.open(out, "r:gz") as tar:
            tops = {n.split("/", 1)[0] for n in tar.getnames() if n.strip("/")}
    except tarfile.TarError as e:
        sys.exit(f"downloaded file is not a gzip tarball: {e}")
    if tops != {want}:
        sys.exit(f"tarball top directories are {sorted(tops)}, expected [{want!r}]")
    print(f"fetched Splunkbase app {app} {version} ({os.path.getsize(out)} bytes) -> {out}")


if __name__ == "__main__":
    main(sys.argv)
