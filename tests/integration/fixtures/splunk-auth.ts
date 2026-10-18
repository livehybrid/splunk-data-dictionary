/**
 * Playwright fixture: Splunk login + app context for live integration tests.
 *
 * Navigates to the app; if Splunk redirects to the login page, fills in
 * username/password and submits. Exposes `app` - the root locator (page, or the
 * first iframe if Splunk wraps the view) - so specs find the React UI directly.
 *
 * Env: SPLUNK_USER (default admin), SPLUNK_PASSWORD (default Changeme1!).
 */
import { test as base, expect, FrameLocator, Page } from '@playwright/test';

const SPLUNK_USER = process.env.SPLUNK_USER || 'admin';
const SPLUNK_PASSWORD = process.env.SPLUNK_PASSWORD || 'Changeme1!';

type Fixtures = {
    authenticated: void;
    app: Page | FrameLocator;
};

export async function login(page: Page, user = SPLUNK_USER, pw = SPLUNK_PASSWORD) {
    // Splunk redirects an unauthenticated view to the login page client-side, so
    // checking straight after navigation can see the app URL and skip the login
    // (10.6 CI, 2026-10-18: the next view landed on the login form). Let the page
    // settle before deciding.
    await page.waitForLoadState('networkidle').catch(() => {});
    const url = page.url();
    const loginVisible =
        /login|account|sso/i.test(url) ||
        (await page
            .locator('input[name="username"], input[name="password"], input#username, input#password')
            .first()
            .isVisible()
            .catch(() => false));
    if (!loginVisible) return;
    const username = page
        .locator('input[name="username"]')
        .or(page.locator('input#username'))
        .or(page.getByRole('textbox', { name: /user/i }));
    const password = page
        .locator('input[name="password"]')
        .or(page.locator('input#password'))
        .or(page.getByRole('textbox', { name: /password/i }));
    await username.first().waitFor({ state: 'visible', timeout: 15000 });
    await username.first().fill(user);
    await password.first().fill(pw);
    await page.getByRole('button', { name: /sign in|log in|login/i }).first().click();
    // Match on the PATH: the login page's own URL carries
    // ?return_to=/app/data_dictionary_for_splunk/..., so a whole-URL regex for
    // /app/ matched before sign-in had finished and the next view hit the login form.
    await page.waitForURL((u) => !/\/account\/login/.test(u.pathname), { timeout: 30000 });
}

/** The React root - the page, or the first iframe if Splunk wraps the view. */
export async function appRoot(page: Page): Promise<Page | FrameLocator> {
    await page.waitForLoadState('networkidle').catch(() => {});
    await page.waitForTimeout(3000);
    const hasIframe = (await page.locator('iframe').count()) > 0;
    return hasIframe ? page.frameLocator('iframe').first() : page;
}

/**
 * Log in as a specific user and open a Data Dictionary view. Each Playwright test
 * gets a fresh context, so there is no prior session to clear. Returns the React
 * root locator for that view.
 */
export async function loginAs(
    page: Page,
    user: string,
    pw: string,
    view: 'home' | 'fields' | 'mcp_tools' = 'home'
): Promise<Page | FrameLocator> {
    await page.goto(`/app/data_dictionary_for_splunk/${view}`, { waitUntil: 'commit', timeout: 30000 });
    await page.waitForLoadState('domcontentloaded').catch(() => {});
    await login(page, user, pw);
    await page.goto(`/app/data_dictionary_for_splunk/${view}`, { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => {});
    return appRoot(page);
}

export const test = base.extend<Fixtures>({
    authenticated: [
        async ({ page }, use) => {
            await page.goto('/app/data_dictionary_for_splunk/home', { waitUntil: 'commit', timeout: 30000 });
            await page.waitForLoadState('domcontentloaded').catch(() => {});
            await login(page);
            await use();
        },
        { scope: 'test' },
    ],
    app: [
        async ({ page, authenticated }, use) => {
            await authenticated;
            await page.waitForLoadState('networkidle').catch(() => {});
            await page.waitForTimeout(3000);
            const hasIframe = (await page.locator('iframe').count()) > 0;
            const root: Page | FrameLocator = hasIframe ? page.frameLocator('iframe').first() : page;
            await use(root);
        },
        { scope: 'test' },
    ],
});

export { expect };
