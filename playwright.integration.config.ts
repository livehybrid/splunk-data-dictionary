import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright config for LIVE integration tests against a real Splunk instance
 * with the built app installed (see the integration CI job + scripts/splunk-docker.sh).
 *
 * Point it at Splunk with SPLUNK_WEB_URL (default http://127.0.0.1:8000).
 * Credentials come from SPLUNK_USER / SPLUNK_PASSWORD (see the auth fixture).
 */
const baseURL = process.env.SPLUNK_WEB_URL || 'http://127.0.0.1:8000';

export default defineConfig({
    testDir: './tests/integration',
    fullyParallel: false,
    forbidOnly: !!process.env.CI,
    retries: process.env.CI ? 2 : 1,
    workers: 1,
    timeout: 60000,
    reporter: process.env.CI ? [['line'], ['html', { open: 'never' }]] : 'line',
    use: {
        baseURL,
        ignoreHTTPSErrors: true,
        trace: 'on-first-retry',
        screenshot: 'only-on-failure',
        testIdAttribute: 'data-test',
    },
    projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
