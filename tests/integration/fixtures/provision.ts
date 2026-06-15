/**
 * Mgmt-API helpers + shared constants for provisioning RBAC test users and a
 * custom field, used by global-setup / global-teardown and the RBAC/custom-field
 * specs. Talks to the Splunk management API (SPLUNK_MGMT_URL) with admin creds.
 *
 * Self-signed TLS is accepted (local Splunk), scoped to this process.
 */
import fs from 'fs';
import path from 'path';

process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';

export const MGMT = (process.env.SPLUNK_MGMT_URL || '').replace(/\/$/, '');
export const ADMIN_USER = process.env.SPLUNK_USER || 'admin';
export const ADMIN_PW = process.env.SPLUNK_PASSWORD || 'Changeme1!';

export const EDIT_ROLE = 'dd_e2e_editor_role';
export const EDITOR_USER = 'dd_e2e_editor';
export const VIEWER_USER = 'dd_e2e_viewer';
export const TEST_PW = 'dd-E2E-passw0rd!';
export const CUSTOM_FIELD = 'e2e_tier';
export const CUSTOM_FIELD_LABEL = 'E2E Tier';

// Marker so specs know provisioning succeeded (else they skip rather than fail).
export const STATE_FILE = path.join(__dirname, '..', '.rbac-state.json');

function authHeader(user: string, pw: string) {
    return 'Basic ' + Buffer.from(`${user}:${pw}`).toString('base64');
}

export async function mgmt(
    method: string,
    apiPath: string,
    opts: { form?: Record<string, string>; json?: unknown; user?: string; pw?: string } = {}
): Promise<{ status: number; body: string }> {
    const headers: Record<string, string> = {
        Authorization: authHeader(opts.user || ADMIN_USER, opts.pw || ADMIN_PW),
    };
    let body: string | undefined;
    if (opts.form) {
        headers['Content-Type'] = 'application/x-www-form-urlencoded';
        body = new URLSearchParams(opts.form).toString();
    } else if (opts.json !== undefined) {
        headers['Content-Type'] = 'application/json';
        body = JSON.stringify(opts.json);
    }
    const res = await fetch(`${MGMT}${apiPath}`, { method, headers, body });
    return { status: res.status, body: await res.text() };
}

export function markProvisioned() {
    fs.writeFileSync(STATE_FILE, JSON.stringify({ provisioned: true, at: Date.now() }));
}

export function clearProvisioned() {
    try {
        fs.unlinkSync(STATE_FILE);
    } catch {
        /* ignore */
    }
}

export function isProvisioned(): boolean {
    try {
        return JSON.parse(fs.readFileSync(STATE_FILE, 'utf8')).provisioned === true;
    } catch {
        return false;
    }
}
