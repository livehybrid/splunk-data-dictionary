/**
 * Playwright globalSetup: provision RBAC test users + a custom field via the
 * Splunk mgmt API so the rbac / custom-field specs are deterministic.
 *
 * Needs SPLUNK_MGMT_URL (+ admin creds). If it is not set, or provisioning
 * fails, the dependent specs detect the missing state file and skip - they never
 * fail the run for a setup that could not happen.
 */
import {
    MGMT, EDIT_ROLE, EDITOR_USER, VIEWER_USER, TEST_PW,
    CUSTOM_FIELD, CUSTOM_FIELD_LABEL, mgmt, markProvisioned, clearProvisioned,
} from './fixtures/provision';

export default async function globalSetup() {
    clearProvisioned();
    if (!MGMT) {
        console.log('[global-setup] SPLUNK_MGMT_URL not set - RBAC/custom-field specs will skip.');
        return;
    }
    try {
        // Editor role carries the capability; viewer is the stock 'user' role.
        await mgmt('POST', '/services/authorization/roles', {
            form: { name: EDIT_ROLE, imported_roles: 'user', capabilities: 'edit_data_dictionary' },
        });
        // force-change-pass=false: otherwise Splunk Web sends a new user to the
        // change-password page on first login and the Playwright login never reaches the app.
        await mgmt('POST', '/services/authentication/users', {
            form: { name: EDITOR_USER, password: TEST_PW, roles: EDIT_ROLE, 'force-change-pass': 'false' },
        });
        await mgmt('POST', '/services/authentication/users', {
            form: { name: VIEWER_USER, password: TEST_PW, roles: 'user', 'force-change-pass': 'false' },
        });
        // Seed a custom field so the Fields page + catalogue editor show it.
        await mgmt('POST', `/services/data_dictionary/field-defs/${CUSTOM_FIELD}`, {
            json: { label: CUSTOM_FIELD_LABEL, type: 'select', options: ['Hot', 'Cold'], order: 95 },
        });

        // Confirm the editor user resolves the capability before we rely on it.
        const perms = await mgmt('GET', '/services/data_dictionary/permissions', { user: EDITOR_USER, pw: TEST_PW });
        if (!perms.body.includes('"can_edit": true')) {
            console.log('[global-setup] editor user did not resolve can_edit=true; specs will skip.', perms.body.slice(0, 200));
            return;
        }
        markProvisioned();
        console.log('[global-setup] provisioned RBAC users + custom field.');
    } catch (e) {
        console.log('[global-setup] provisioning failed; specs will skip.', String(e));
    }
}
