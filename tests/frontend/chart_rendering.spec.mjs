import { expect, test } from '@playwright/test';

test('renders dashboard charts with mocked transaction analysis data', async ({ page }) => {
  await page.route('https://cdn.jsdelivr.net/npm/chart.js', async (route) => {
    await route.fulfill({
      contentType: 'application/javascript',
      body: `
        window.__chartCalls = [];
        window.__resizeCalls = [];
        window.Chart = class MockChart {
          constructor(ctx, config) {
            this.id = ctx.id || ctx.canvas?.id;
            window.__chartCalls.push({
              id: this.id,
              type: config.type,
              labels: config.data.labels,
              colors: config.data.datasets[0].backgroundColor,
              tickColor: config.options.scales?.x?.ticks?.color || null
            });
          }

          destroy() {}
          resize() {
            window.__resizeCalls.push(this.id);
          }
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
          transaction_count: 1,
          anomalies: [{ id: 'txn-1' }],
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

  await expect(page.locator('.kpi-card strong')).toHaveText([/1,280\.00/, /1,280\.00/, '1', '1']);

  await expect
    .poll(() => page.evaluate(() => window.__chartCalls))
    .toEqual([
      {
        id: 'category-chart',
        type: 'doughnut',
        labels: ['Groceries'],
        colors: ['#c9a84c', '#00e566', '#ff5b6e', '#e8d9b5', '#00d4ff', '#ffb000'],
        tickColor: null
      },
      {
        id: 'trend-chart',
        type: 'line',
        labels: ['2026-05-10'],
        colors: ['#c9a84c', '#00e566', '#ff5b6e', '#e8d9b5', '#00d4ff', '#ffb000'],
        tickColor: '#b8a882'
      },
      {
        id: 'merchant-chart',
        type: 'bar',
        labels: ['Metro Market'],
        colors: ['#c9a84c', '#00e566', '#ff5b6e', '#e8d9b5', '#00d4ff', '#ffb000'],
        tickColor: '#b8a882'
      }
    ]);

  await page.getByRole('tab', { name: 'Transactions' }).click();
  await expect(page.locator('#transaction-body tr')).toHaveCount(1);
  await expect(page.locator('#transaction-body')).toContainText('Metro Market');

  await page.setViewportSize({ width: 768, height: 900 });
  await expect.poll(() => page.evaluate(() => window.__resizeCalls.length)).toBeGreaterThan(0);
});
test('shows chart empty states instead of rendering empty datasets', async ({ page }) => {
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

  await page.goto('/');

  await expect(page.locator('.chart-empty-state')).toHaveCount(3);
  await expect(page.locator('#charts')).toContainText('No category spend yet.');
  await expect.poll(() => page.evaluate(() => window.__chartCalls)).toEqual([]);
});
