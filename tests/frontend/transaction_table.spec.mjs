import { expect, test } from '@playwright/test';

async function mockChart(page) {
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
}

async function mockDashboard(page) {
  await page.route('**/api/v1/transactions', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: [
          {
            id: 'txn-normal',
            date: '2026-05-10',
            merchant: 'Everyday Store',
            category: 'Groceries',
            total: 420,
            bill_number: 'B-100',
            payment_method: 'UPI',
            items: [{ name: 'Staples', total_price: 420 }],
            is_anomaly: false,
            is_duplicate: false
          },
          {
            id: 'txn-anomaly',
            date: '2026-05-09',
            merchant: 'Odd Merchant',
            category: 'Travel',
            total: 9000,
            bill_number: 'A-1',
            payment_method: 'Card',
            items: [{ name: 'Late booking', total_price: 9000 }],
            is_anomaly: true,
            is_duplicate: false
          },
          {
            id: 'txn-duplicate',
            date: '2026-05-08',
            merchant: 'Dupe Store',
            category: 'Utilities',
            total: 1300,
            bill_number: 'D-1',
            payment_method: 'Cash',
            items: [{ name: 'Bill copy', total_price: 1300 }],
            is_anomaly: false,
            is_duplicate: true
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
          total_spend: 10720,
          category_totals: { Groceries: 420, Travel: 9000, Utilities: 1300 },
          daily_trend: [['2026-05-10', 420]],
          top_merchants: [['Odd Merchant', 9000]],
          merchant_totals: [['Odd Merchant', 9000]]
        },
        error: null
      })
    });
  });
}

test('renders polished transaction status chips and inline resolution actions', async ({ page }) => {
  await mockChart(page);
  await mockDashboard(page);

  let dismissRequests = 0;
  let duplicateRequests = 0;
  await page.route('**/api/v1/transactions/txn-anomaly/dismiss-anomaly', async (route) => {
    dismissRequests += 1;
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: {}, error: null })
    });
  });
  await page.route('**/api/v1/duplicate/confirm', async (route) => {
    duplicateRequests += 1;
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: {}, error: null })
    });
  });

  await page.goto('/');

  await expect(page.locator('.status-badge')).toHaveCount(3);
  await expect(page.locator('.status-badge .status-icon')).toHaveCount(3);
  await expect(page.locator('.status-badge.normal')).toContainText('normal');
  await expect(page.locator('.status-badge.anomaly')).toContainText('anomaly');
  await expect(page.locator('.status-badge.duplicate')).toContainText('duplicate');

  await page.locator('#transaction-body tr', { hasText: 'Odd Merchant' }).first().click();
  await expect(page.locator('.details-row .details-panel')).toContainText('Late booking');
  await page.locator('.details-row button', { hasText: 'Dismiss' }).click();
  expect(dismissRequests).toBe(1);

  await page.locator('#transaction-body tr', { hasText: 'Dupe Store' }).first().click();
  await expect(page.locator('.details-row .details-panel')).toContainText('Bill copy');
  await page.locator('.details-row button', { hasText: 'Keep both' }).click();
  expect(duplicateRequests).toBe(1);
});
