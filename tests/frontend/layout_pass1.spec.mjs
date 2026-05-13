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

test('renders the cabinet desktop shell with marquee, reels, iDeck tabs, and KPI cards', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await mockDashboard(page);

  await page.goto('/');

  await expect(page.locator('.cabinet')).toBeVisible();
  await expect(page.locator('.marquee')).toBeVisible();
  await expect(page.locator('.reel-housing')).toBeVisible();
  await expect(page.locator('.ideck-nav [data-view-link]')).toHaveText(['01 Dashboard', '02 Upload', '03 Transactions', '04 Metrics', '05 Nova']);
  await expect(page.locator('.brand-sub')).toContainText('99% of gamblers give up before making it big. Be the 1%.');
  await expect(page.locator('#dashboard-view')).toBeVisible();
  await expect(page.locator('.kpi-card')).toHaveCount(4);
  await expect(page.locator('.kpi-card')).toContainText(['Total Spend', 'This Month', 'Anomalies Flagged', 'Bills Processed']);
  await expect(page.locator('#reels-track .reel-tape')).toHaveCount(5);
});
test('keeps iDeck navigation usable at mobile width without horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockDashboard(page);

  await page.goto('/');

  await expect(page.locator('.ideck-nav')).toBeVisible();
  await page.getByRole('tab', { name: 'Transactions' }).click();
  await expect(page.locator('#transactions-view')).toBeVisible();
  const hasOverflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(hasOverflow).toBe(false);
});

test('keeps the cabinet shell usable at tablet width', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 1024 });
  await mockDashboard(page);

  await page.goto('/');

  await expect(page.locator('.cabinet')).toBeVisible();
  await expect(page.locator('.ideck-nav')).toBeVisible();
  await expect(page.locator('.kpi-card')).toHaveCount(4);
  await page.getByRole('tab', { name: 'Nova' }).click();
  await expect(page.locator('#nova.nova-panel')).toBeVisible();
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

  await page.getByRole('tab', { name: 'Transactions' }).click();
  await expect(page.locator('.table-skeleton.skeleton-loader')).toHaveCount(1);
  await expect(page.locator('.transaction-empty-state')).toBeVisible();
  await expect(page.locator('.transaction-empty-state')).toContainText('No transactions yet.');
});

test('reduced-motion mode disables reel animation loops', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 1280, height: 900 });
  await mockDashboard(page);

  await page.goto('/');

  const animationName = await page.locator('#reel-0').evaluate((element) => getComputedStyle(element).animationName);
  expect(animationName).toBe('none');
});
