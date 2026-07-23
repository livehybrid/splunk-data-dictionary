#!/usr/bin/env python3
"""SLIM-parity gate: verify every file referenced by app.manifest exists in the
packaged tarball.

Splunkbase runs SLIM validation on upload, which resolves manifest file
references (e.g. info.license.text -> ./LICENSES/Apache-2.0.txt). None of the
AppInspect check groups do this, so a manifest pointing at a file the package
does not ship passes CI and then fails on Splunkbase (seen 2026-07-23).

Usage: python3 scripts/verify_manifest_refs.py dist/<app>-<version>.tar.gz
"""
import json
import sys
import tarfile


def file_refs(node):
    """Yield every string value in the manifest that looks like an app-relative
    file reference (./...)."""
    if isinstance(node, dict):
        for v in node.values():
            yield from file_refs(v)
    elif isinstance(node, list):
        for v in node:
            yield from file_refs(v)
    elif isinstance(node, str) and node.startswith("./"):
        yield node


def main(tarball):
    with tarfile.open(tarball, "r:gz") as tf:
        names = tf.getnames()
        root = names[0].split("/")[0]
        try:
            manifest = json.load(tf.extractfile(f"{root}/app.manifest"))
        except KeyError:
            print(f"FAIL: {root}/app.manifest missing from {tarball}")
            return 1
        missing = []
        for ref in file_refs(manifest):
            member = f"{root}/{ref[2:]}"
            if member not in names:
                missing.append(ref)
        if missing:
            for ref in missing:
                print(f"FAIL: app.manifest references {ref} but the package does not ship it")
            return 1
    print(f"OK: all app.manifest file references resolve inside {tarball}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
