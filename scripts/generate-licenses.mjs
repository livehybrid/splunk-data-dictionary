#!/usr/bin/env node
/**
 * Generate third-party license attribution for the app's PRODUCTION npm
 * dependencies (the libraries bundled into the shipped JS) into `licenses/`.
 *
 * Dependency-free and offline: reads the installed `node_modules` and the
 * production dependency closure from `npm ls --omit=dev`. Output is deterministic
 * (sorted, no timestamps) so a CI freshness check can diff it.
 *
 * Outputs:
 *   licenses/THIRD-PARTY-LICENSES.md  — summary table + SPDX counts
 *   licenses/THIRD-PARTY-NOTICES.txt  — full license text per package
 *   licenses/README.md                — what this is / how to regenerate
 *
 * Usage: npm run licenses
 */
import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const nodeModules = path.join(root, 'node_modules');
const outDir = path.join(root, 'licenses');

const rootPkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
const ROOT_NAME = rootPkg.name;

const LICENSE_FILE_RE = /^(licen[sc]e|copying|copyright|notice|unlicense)(\.|$)/i;

function normalizeLicense(pkg) {
    if (typeof pkg.license === 'string') return pkg.license;
    if (pkg.license && typeof pkg.license === 'object' && pkg.license.type) return pkg.license.type;
    if (Array.isArray(pkg.licenses)) {
        const types = pkg.licenses.map((l) => (typeof l === 'string' ? l : l.type)).filter(Boolean);
        if (types.length) return types.join(' OR ');
    }
    return 'UNKNOWN';
}

function repoUrl(pkg) {
    const r = pkg.repository;
    let url = '';
    if (typeof r === 'string') url = r;
    else if (r && typeof r === 'object' && r.url) url = r.url;
    url = url.replace(/^git\+/, '').replace(/^git:\/\//, 'https://').replace(/\.git$/, '');
    // Expand host shorthands like "owner/repo" or "github:owner/repo".
    const shorthand = url.match(/^(?:(github|gitlab|bitbucket):)?([\w.-]+\/[\w.-]+)$/);
    if (shorthand) {
        const host = { gitlab: 'gitlab.com', bitbucket: 'bitbucket.org' }[shorthand[1]] || 'github.com';
        url = `https://${host}/${shorthand[2]}`;
    }
    return url || pkg.homepage || '';
}

function findLicenseText(dir) {
    let entries;
    try {
        entries = fs.readdirSync(dir);
    } catch {
        return null;
    }
    const candidates = entries.filter((e) => LICENSE_FILE_RE.test(e));
    // Prefer an exact "LICENSE"/"LICENCE" over NOTICE/COPYRIGHT extras.
    candidates.sort((a, b) => {
        const score = (n) => (/^licen[sc]e/i.test(n) ? 0 : /^copying/i.test(n) ? 1 : 2);
        return score(a) - score(b) || a.localeCompare(b);
    });
    for (const c of candidates) {
        const p = path.join(dir, c);
        try {
            if (fs.statSync(p).isFile()) {
                const txt = fs.readFileSync(p, 'utf8').trim();
                if (txt) return { file: c, text: txt };
            }
        } catch {
            /* ignore */
        }
    }
    return null;
}

// Build a map of name@version -> install dir by walking node_modules (handles
// hoisting + nested node_modules so every resolved version is found).
function indexInstalled() {
    const map = new Map();
    const stack = [nodeModules];
    while (stack.length) {
        const cur = stack.pop();
        let names;
        try {
            names = fs.readdirSync(cur, { withFileTypes: true });
        } catch {
            continue;
        }
        for (const d of names) {
            if (!d.isDirectory()) continue;
            if (d.name === '.bin' || d.name === '.cache') continue;
            const full = path.join(cur, d.name);
            if (d.name.startsWith('@')) {
                // scope dir: recurse one level into the scoped packages
                stack.push(full);
                continue;
            }
            const pjPath = path.join(full, 'package.json');
            if (fs.existsSync(pjPath)) {
                try {
                    const pj = JSON.parse(fs.readFileSync(pjPath, 'utf8'));
                    if (pj.name && pj.version) {
                        const key = `${pj.name}@${pj.version}`;
                        if (!map.has(key)) map.set(key, { dir: full, pkg: pj });
                    }
                } catch {
                    /* ignore unreadable package.json */
                }
            }
            const nested = path.join(full, 'node_modules');
            if (fs.existsSync(nested)) stack.push(nested);
        }
    }
    return map;
}

// Production dependency closure (incl. transitive) from npm.
function prodClosure() {
    let json;
    try {
        json = execSync('npm ls --omit=dev --all --json', { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
    } catch (e) {
        // npm ls exits non-zero on benign warnings but still prints JSON on stdout.
        json = e.stdout || '';
    }
    const tree = JSON.parse(json || '{}');
    const set = new Set();
    (function walk(node) {
        const deps = node.dependencies || {};
        for (const [name, info] of Object.entries(deps)) {
            if (!info || !info.version) continue;
            const key = `${name}@${info.version}`;
            if (set.has(key)) continue;
            set.add(key);
            walk(info);
        }
    })(tree);
    return set;
}

function main() {
    const installed = indexInstalled();
    const closure = [...prodClosure()].filter((k) => !k.startsWith(`${ROOT_NAME}@`)).sort();

    const records = [];
    const missing = [];
    for (const key of closure) {
        const hit = installed.get(key);
        if (!hit) {
            missing.push(key);
            continue;
        }
        const { dir, pkg } = hit;
        const lic = findLicenseText(dir);
        records.push({
            name: pkg.name,
            version: pkg.version,
            license: normalizeLicense(pkg),
            repo: repoUrl(pkg),
            homepage: pkg.homepage || '',
            licenseFile: lic ? lic.file : null,
            licenseText: lic ? lic.text : null,
        });
    }
    records.sort((a, b) => `${a.name}@${a.version}`.localeCompare(`${b.name}@${b.version}`));

    // SPDX tally
    const tally = {};
    for (const r of records) tally[r.license] = (tally[r.license] || 0) + 1;
    const tallyLines = Object.entries(tally)
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
        .map(([lic, n]) => `- ${lic}: ${n}`);

    fs.mkdirSync(outDir, { recursive: true });

    // THIRD-PARTY-LICENSES.md
    const mdRows = records
        .map((r) => {
            const link = r.repo || r.homepage;
            const pkgCell = link ? `[${r.name}](${link})` : r.name;
            return `| ${pkgCell} | ${r.version} | ${r.license} |`;
        })
        .join('\n');
    const md = [
        '# Third-party licenses',
        '',
        `This app bundles the following **production** npm dependencies (${records.length} packages, `,
        'including transitive) into its JavaScript. All are open source. Full license',
        'texts are in [`THIRD-PARTY-NOTICES.txt`](./THIRD-PARTY-NOTICES.txt).',
        '',
        '> Generated by `npm run licenses` (scripts/generate-licenses.mjs). Do not edit by hand.',
        '',
        '## License summary',
        '',
        ...tallyLines,
        '',
        '## Packages',
        '',
        '| Package | Version | License |',
        '| --- | --- | --- |',
        mdRows,
        '',
    ].join('\n');
    fs.writeFileSync(path.join(outDir, 'THIRD-PARTY-LICENSES.md'), md);

    // THIRD-PARTY-NOTICES.txt
    const sep = '\n' + '='.repeat(80) + '\n';
    const notices = [
        'THIRD-PARTY SOFTWARE NOTICES AND INFORMATION',
        '',
        'This file lists the production npm dependencies bundled into the Data',
        'Dictionary Splunk app and their license texts. Generated by',
        '`npm run licenses` — do not edit by hand.',
        '',
    ];
    for (const r of records) {
        notices.push(sep.trim());
        notices.push(`${r.name}@${r.version}`);
        notices.push(`License: ${r.license}`);
        if (r.repo) notices.push(`Repository: ${r.repo}`);
        notices.push('');
        notices.push(r.licenseText || `(No license file shipped in the package; declared license: ${r.license})`);
        notices.push('');
    }
    fs.writeFileSync(path.join(outDir, 'THIRD-PARTY-NOTICES.txt'), notices.join('\n') + '\n');

    // README.md
    const readme = [
        '# licenses/',
        '',
        'Third-party license attribution for this app, generated reproducibly so the',
        'submission can show that every bundled library is open source.',
        '',
        '- **THIRD-PARTY-LICENSES.md** — summary table of every production npm',
        '  dependency (incl. transitive) with its version and SPDX license.',
        '- **THIRD-PARTY-NOTICES.txt** — the full license text of each package.',
        '',
        '## Regenerate',
        '',
        '```bash',
        'npm ci          # ensure node_modules matches package-lock.json',
        'npm run licenses',
        '```',
        '',
        'The generator (`scripts/generate-licenses.mjs`) is dependency-free and',
        'deterministic. CI regenerates this folder and flags it if it drifts from the',
        'committed copy.',
        '',
        '## Scope',
        '',
        "The shipped app's Python (`bin/*.py`) uses only the Python standard library",
        'plus modules provided by the Splunk platform at runtime (`splunk.*`), so there',
        'are no bundled third-party Python libraries to attribute. Build/test-only',
        'tooling (ucc-gen, webpack, pytest, ruff, Playwright) is not shipped in the app',
        'package. This folder therefore covers the third-party code that actually ships:',
        'the bundled JavaScript dependencies.',
        '',
    ].join('\n');
    fs.writeFileSync(path.join(outDir, 'README.md'), readme);

    console.log(`Wrote licenses/ for ${records.length} production packages.`);
    console.log('License summary:');
    tallyLines.forEach((l) => console.log('  ' + l.slice(2)));
    if (missing.length) {
        console.warn(`\nWARNING: ${missing.length} package(s) in the prod closure were not found in node_modules:`);
        missing.forEach((m) => console.warn('  ' + m));
        console.warn('Run `npm ci` and re-run to resolve.');
    }
}

main();
