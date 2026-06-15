/**
 * Live RBAC tests: a user WITHOUT the edit_data_dictionary capability sees a
 * read-only UI (badge + banner, no edit/run/add controls); a user WITH it (via a
 * role) sees the editor controls. Depends on global-setup having provisioned the
 * users - skips cleanly if it did not.
 */
import { test, expect } from '@playwright/test';
import { loginAs } from './fixtures/splunk-auth';
import { EDITOR_USER, VIEWER_USER, TEST_PW, CUSTOM_FIELD_LABEL, isProvisioned } from './fixtures/provision';

test.beforeEach(() => {
    test.skip(!isProvisioned(), 'RBAC users not provisioned (global-setup did not run / no SPLUNK_MGMT_URL)');
});

test.describe('read-only user', () => {
    test('home page shows a Read-only badge + banner and hides edit controls', async ({ page }) => {
        const app = await loginAs(page, VIEWER_USER, TEST_PW, 'home');
        await expect(app.getByRole('heading', { level: 2, name: /data dictionary/i })).toBeVisible({ timeout: 20000 });
        await expect(app.getByText('Read-only').first()).toBeVisible({ timeout: 15000 });
        await expect(app.getByText(/read-only access to the data dictionary/i)).toBeVisible({ timeout: 15000 });
        // Editor-only controls must be absent.
        await expect(app.getByRole('button', { name: /run catalog search/i })).toHaveCount(0);
        // Read controls remain.
        await expect(app.getByRole('button', { name: /refresh catalog and metadata/i })).toBeVisible();
    });

    test('Fields page hides "Add field" and shows the read-only banner', async ({ page }) => {
        const app = await loginAs(page, VIEWER_USER, TEST_PW, 'fields');
        await expect(app.getByRole('heading', { name: /data dictionary.*fields/i })).toBeVisible({ timeout: 20000 });
        await expect(app.getByText(/read-only access/i)).toBeVisible({ timeout: 15000 });
        await expect(app.getByRole('button', { name: /^add field$/i })).toHaveCount(0);
    });
});

test.describe('editor user', () => {
    test('home page shows an Editor badge and the Run catalog search control', async ({ page }) => {
        const app = await loginAs(page, EDITOR_USER, TEST_PW, 'home');
        await expect(app.getByRole('heading', { level: 2, name: /data dictionary/i })).toBeVisible({ timeout: 20000 });
        await expect(app.getByText('Editor').first()).toBeVisible({ timeout: 15000 });
        await expect(app.getByRole('button', { name: /run catalog search/i })).toBeVisible({ timeout: 15000 });
    });

    test('Fields page shows "Add field" and lists the seeded custom field', async ({ page }) => {
        const app = await loginAs(page, EDITOR_USER, TEST_PW, 'fields');
        await expect(app.getByRole('heading', { name: /data dictionary.*fields/i })).toBeVisible({ timeout: 20000 });
        await expect(app.getByRole('button', { name: /^add field$/i })).toBeVisible({ timeout: 15000 });
        await expect(app.getByText(CUSTOM_FIELD_LABEL).first()).toBeVisible({ timeout: 15000 });
    });
});
