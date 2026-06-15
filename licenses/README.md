# licenses/

Third-party license attribution for this app, generated reproducibly so the
submission can show that every bundled library is open source.

- **THIRD-PARTY-LICENSES.md** — summary table of every production npm
  dependency (incl. transitive) with its version and SPDX license.
- **THIRD-PARTY-NOTICES.txt** — the full license text of each package.

## Regenerate

```bash
npm ci          # ensure node_modules matches package-lock.json
npm run licenses
```

The generator (`scripts/generate-licenses.mjs`) is dependency-free and
deterministic. CI regenerates this folder and flags it if it drifts from the
committed copy.

## Scope

The shipped app's Python (`bin/*.py`) uses only the Python standard library
plus modules provided by the Splunk platform at runtime (`splunk.*`), so there
are no bundled third-party Python libraries to attribute. Build/test-only
tooling (ucc-gen, webpack, pytest, ruff, Playwright) is not shipped in the app
package. This folder therefore covers the third-party code that actually ships:
the bundled JavaScript dependencies.
