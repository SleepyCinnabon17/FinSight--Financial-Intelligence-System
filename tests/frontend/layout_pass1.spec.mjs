import { expect, test } from '@playwright/test';

async function mockDashboard(page) {
  await page.route('https://cdn.jsdelivr.net/npm/chart.js', async (route) => {
    await route.fulfill({
      contentType: 'application/javascript',
      body: `
        window.Chart = class MockChart {
          constructor() {}
          destroy() {}
          resize() {}
        };
      `
    });
  });

  await page.route('**/api/v1/transactions', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: [], error: null })
    });
  });

  await page.route('**/api/v1/analysis', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          total_spend: 0,
          category_totals: {},
          daily_trend: [],
          top_merchants: [],
          merchant_totals: []
        },
        error: null
      })
    });
  });
}

test('renders the Enigma-style network shell with dashboard, terminal Nova, and popup controls', async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await mockDashboard(page);

  await page.goto('/');

  await expect(page.locator('.cabinet.network-shell')).toBeVisible();
  await expect(page.locator('.network-bg')).toBeVisible();
  await expect(page.locator('.ideck-nav')).toHaveCount(0);
  await expect(page.locator('.cab-rail')).toHaveCount(0);
  await expect(page.locator('.brand-title')).toContainText('FinSight');
  await expect(page.locator('.hero-gradient')).toContainText('Know where your money went.');
  await expect(page.locator('.hero-tagline')).toContainText('Upload receipts, reveal leaks, and let Nova explain your spending');
  await expect(page.locator('.hero-terminal')).toBeVisible();
  await expect(page.locator('.hero-terminal')).toContainText('99% of gamblers give up before making it big. Be the 1%.');
  await expect(page.locator('.hero-terminal #nova')).toBeVisible();
  await expect(page.locator('#nova-view')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Transactions' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Metrics' })).toBeVisible();
  await expect(page.locator('.kpi-card')).toHaveCount(4);
  await expect(page.locator('#upload-view')).toBeHidden();

  const order = await page.evaluate(() => {
    const rect = (selector) => document.querySelector(selector).getBoundingClientRect().top;
    return {
      dashboard: rect('#dashboard-view'),
      terminal: rect('.hero-terminal')
    };
  });
  expect(order.terminal).toBeLessThan(order.dashboard);
});

test('keeps popup buttons usable at mobile width without horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockDashboard(page);

  await page.goto('/');

  await page.getByRole('button', { name: 'Transactions' }).click();
  await expect(page.locator('#transactions-view')).toBeVisible();
  await expect(page.getByRole('dialog', { name: 'Transactions' })).toBeVisible();
  const hasOverflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(hasOverflow).toBe(false);
});

test('keeps the network layout usable at tablet width', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 1024 });
  await mockDashboard(page);

  await page.goto('/');

  await expect(page.locator('.cabinet.network-shell')).toBeVisible();
  await expect(page.locator('.top-actions')).toBeVisible();
  await expect(page.locator('.kpi-card')).toHaveCount(4);
  await expect(page.locator('.hero-terminal #nova')).toBeVisible();
  await page.getByRole('button', { name: 'Upload', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Upload a Receipt' })).toBeVisible();
});

test('toggles light and dark theme with localStorage persistence', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await mockDashboard(page);

  await page.goto('/');

  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.locator('.theme-toggle').click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await expect.poll(() => page.evaluate(() => window.localStorage.getItem('finsight-theme'))).toBe('light');

  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
});

test('includes skeleton shells and shows transaction empty state with no data', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await mockDashboard(page);

  await page.goto('/');

  await expect(page.locator('.kpi-card .skeleton-loader')).toHaveCount(4);
  await expect(page.locator('.chart-skeleton.skeleton-loader')).toHaveCount(3);
  await expect(page.locator('.chat-skeleton.skeleton-loader')).toHaveCount(1);

  await page.getByRole('button', { name: 'Transactions' }).click();
  await expect(page.locator('.table-skeleton.skeleton-loader')).toHaveCount(1);
  await expect(page.locator('.transaction-empty-state')).toBeVisible();
  await expect(page.locator('.transaction-empty-state')).toContainText('No transactions yet.');
});

test('reduced-motion mode disables terminal cursor animation', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 1280, height: 900 });
  await mockDashboard(page);

  await page.goto('/');

  await expect(page.locator('.terminal-cursor')).toHaveCount(0);
});
