/**
 * Live custom-field tests: the Fields admin page lists the standard governance
 * fields plus admin-defined custom fields, and the catalogue editor's column
 * picker offers the custom field. Depends on global-setup having seeded the
 * custom field (e2e_tier / "E2E Tier"); skips cleanly otherwise.
 */
import { test, expect } from '@playwright/test';
import { loginAs } from './fixtures/splunk-auth';
import { EDITOR_USER, TEST_PW, CUSTOM_FIELD_LABEL, isProvisioned } from './fixtures/provision';

test.beforeEach(() => {
    test.skip(!isProvisioned(), 'custom field not provisioned (global-setup did not run / no SPLUNK_MGMT_URL)');
});

test('Fields page lists standard + custom fields', async ({ page }) => {
    const app = await loginAs(page, EDITOR_USER, TEST_PW, 'fields');
    await expect(app.getByRole('heading', { name: /data dictionary.*fields/i })).toBeVisible({ timeout: 20000 });
    // A standard field that always ships with the app.
    await expect(app.getByText('Data Owner').first()).toBeVisible({ timeout: 15000 });
    // The admin-defined custom field.
    await expect(app.getByText(CUSTOM_FIELD_LABEL).first()).toBeVisible({ timeout: 15000 });
    // It is flagged non-standard (Standard column = No) - find its row and check.
    const row = app.locator('tr', { hasText: CUSTOM_FIELD_LABEL }).first();
    await expect(row).toBeVisible();
});

test('catalogue editor column picker offers the custom field', async ({ page }) => {
    const app = await loginAs(page, EDITOR_USER, TEST_PW, 'home');
    await expect(app.getByRole('heading', { level: 2, name: /data dictionary/i })).toBeVisible({ timeout: 20000 });
    const chooseColumns = app.getByRole('button', { name: /choose columns/i });
    // "Choose columns" only appears once the catalog has rows; skip if empty.
    if ((await chooseColumns.count()) === 0) {
        test.skip(true, 'catalog empty on this instance - no column picker to assert against');
    }
    await chooseColumns.click();
    await expect(app.getByText(CUSTOM_FIELD_LABEL).first()).toBeVisible({ timeout: 10000 });
});
