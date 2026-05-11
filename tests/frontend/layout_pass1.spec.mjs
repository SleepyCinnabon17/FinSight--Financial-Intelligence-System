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

test('renders the pass 1 desktop shell with sidebar, KPI cards, and collapsible Nova panel', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await mockDashboard(page);

  await page.goto('/');

  await expect(page.locator('.app-shell')).toBeVisible();
  await expect(page.locator('.sidebar')).toBeVisible();
  await expect(page.locator('.sidebar-nav a')).toHaveText(['Dashboard', 'Transactions', 'Upload', 'Nova Chat']);
  await expect(page.locator('.kpi-card')).toHaveCount(4);
  await expect(page.locator('.kpi-card')).toContainText(['Total Spend', 'This Month', 'Anomalies Flagged', 'Bills Processed']);
  await expect(page.locator('#nova.nova-panel')).toBeVisible();

  await page.locator('.nova-toggle').click();
  await expect(page.locator('#nova')).toHaveClass(/is-collapsed/);
});

test('collapses sidebar behind hamburger at mobile width', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockDashboard(page);

  await page.goto('/');

  await expect(page.locator('#sidebar-toggle')).toBeVisible();
  await expect(page.locator('.sidebar')).not.toHaveClass(/is-open/);
  await page.locator('#sidebar-toggle').click();
  await expect(page.locator('.sidebar')).toHaveClass(/is-open/);
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
