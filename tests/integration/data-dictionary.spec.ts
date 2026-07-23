/**
 * Live integration tests for the Data Dictionary app, run against a real Splunk
 * instance (Docker) with the built app installed. Drives the actual React
 * bundles + REST handlers - not mocks.
 *
 * Run via: npm run test:integration  (after the app is built and Splunk is up).
 * See scripts/integration-up.sh / the integration CI job for orchestration.
 *
 * Assertions target UI that renders even with an empty catalog, so the suite is
 * deterministic on a freshly-booted Splunk.
 */
import { test, expect } from './fixtures/splunk-auth';

test.describe('Data Dictionary home page', () => {
    test('loads and shows the Data Dictionary heading', async ({ app }) => {
        await expect(
            app.getByRole('heading', { level: 2, name: /data dictionary/i })
        ).toBeVisible({ timeout: 20000 });
    });

    test('shows the description paragraph', async ({ app }) => {
        await expect(app.getByText(/browse and manage metadata/i)).toBeVisible({ timeout: 15000 });
    });

    test('REST stack is connected (toolbar renders)', async ({ app }) => {
        // The toolbar only renders once ping() succeeds (connected === true), so
        // this proves the app's persistent REST handlers are live in Splunk.
        await expect(
            app.getByRole('button', { name: /run catalog search/i })
        ).toBeVisible({ timeout: 20000 });
        await expect(
            app.getByRole('button', { name: /refresh catalog and metadata/i })
        ).toBeVisible({ timeout: 20000 });
    });

    test('"View unprocessed only" switch is visible and clickable', async ({ app, page }) => {
        const switchControl = app
            .getByRole('switch', { name: /view unprocessed only/i })
            .or(app.locator('[data-test="switch"]').filter({ hasText: /view unprocessed only/i }))
            .first();
        await expect(switchControl).toBeVisible({ timeout: 15000 });
        await switchControl.click();
        await page.waitForTimeout(500);
        await expect(switchControl).toBeVisible();
    });
});

test.describe('MCP tools page', () => {
    test('loads and shows the documentation heading', async ({ page, authenticated }) => {
        await authenticated;
        // Splunk sometimes aborts the first navigation with a client-side redirect
        // (net::ERR_ABORTED); retry once and wait for the real document.
        try {
            await page.goto('/app/data_dictionary_for_splunk/mcp_tools', {
                waitUntil: 'domcontentloaded',
                timeout: 30000,
            });
        } catch {
            await page.goto('/app/data_dictionary_for_splunk/mcp_tools', {
                waitUntil: 'domcontentloaded',
                timeout: 30000,
            });
        }
        await page.waitForLoadState('networkidle').catch(() => {});
        await page.waitForTimeout(2000);
        const hasIframe = (await page.locator('iframe').count()) > 0;
        const root = hasIframe ? page.frameLocator('iframe').first() : page;
        await expect(
            root.getByRole('heading', { level: 2, name: /ai and splunk mcp tools/i })
        ).toBeVisible({ timeout: 20000 });
        // The "Registered tools" table proves the page body rendered, not just the header.
        await expect(root.getByText(/registered mcp tools/i)).toBeVisible({ timeout: 15000 });
    });
});
