/**
 * Playwright globalTeardown: remove everything global-setup provisioned.
 */
import {
    MGMT, EDIT_ROLE, EDITOR_USER, VIEWER_USER, CUSTOM_FIELD, mgmt, clearProvisioned,
} from './fixtures/provision';

export default async function globalTeardown() {
    if (MGMT) {
        try {
            await mgmt('DELETE', `/services/authentication/users/${EDITOR_USER}`);
            await mgmt('DELETE', `/services/authentication/users/${VIEWER_USER}`);
            await mgmt('DELETE', `/services/authorization/roles/${EDIT_ROLE}`);
            await mgmt('DELETE', `/services/data_dictionary/field-defs/${CUSTOM_FIELD}`);
        } catch (e) {
            console.log('[global-teardown] cleanup warning:', String(e));
        }
    }
    clearProvisioned();
}
