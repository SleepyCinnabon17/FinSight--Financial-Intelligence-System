import { expect, test } from '@playwright/test';

test('renders dashboard charts with mocked transaction analysis data', async ({ page }) => {
  await page.route('https://cdn.jsdelivr.net/npm/chart.js', async (route) => {
    await route.fulfill({
      contentType: 'application/javascript',
      body: `
        window.__chartCalls = [];
        window.Chart = class MockChart {
          constructor(ctx, config) {
            window.__chartCalls.push({ id: ctx.id || ctx.canvas?.id, type: config.type, labels: config.data.labels });
          }

          destroy() {}
        };
      `
    });
  });

  await page.route('**/api/v1/transactions', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: [
          {
            id: 'txn-1',
            date: '2026-05-10',
            merchant: 'Metro Market',
            category: 'Groceries',
            total: 1280,
            status: 'normal',
            items: []
          }
        ],
        error: null
      })
    });
  });

  await page.route('**/api/v1/analysis', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          total_spend: 1280,
          category_totals: { Groceries: 1280 },
          daily_trend: [['2026-05-10', 1280]],
          top_merchants: [['Metro Market', 1280]],
          merchant_totals: [['Metro Market', 1280]]
        },
        error: null
      })
    });
  });

  await page.goto('/');

  await expect(page.locator('#transaction-body tr')).toHaveCount(1);
  await expect(page.locator('#transaction-body')).toContainText('Metro Market');

  await expect
    .poll(() => page.evaluate(() => window.__chartCalls))
    .toEqual([
      { id: 'category-chart', type: 'doughnut', labels: ['Groceries'] },
      { id: 'trend-chart', type: 'line', labels: ['2026-05-10'] },
      { id: 'merchant-chart', type: 'bar', labels: ['Metro Market'] }
    ]);
});
