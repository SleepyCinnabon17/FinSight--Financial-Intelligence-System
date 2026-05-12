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
  await page.getByRole('link', { name: 'Transactions' }).click();

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

test('resets demo transactions after a second confirmation click', async ({ page }) => {
  await mockChart(page);
  let transactions = [
    {
      id: 'txn-reset-1',
      date: '2026-05-10',
      merchant: 'Reset Store',
      category: 'Groceries',
      total: 420,
      items: [],
      is_anomaly: false,
      is_duplicate: false
    },
    {
      id: 'txn-reset-2',
      date: '2026-05-11',
      merchant: 'Reset Cafe',
      category: 'Food',
      total: 580,
      items: [],
      is_anomaly: true,
      is_duplicate: false
    }
  ];
  const deletedIds = [];

  await page.route('**/api/v1/transactions/*', async (route) => {
    const id = route.request().url().split('/').pop();
    deletedIds.push(id);
    transactions = transactions.filter((transaction) => transaction.id !== id);
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { deleted: true }, error: null })
    });
  });

  await page.route('**/api/v1/transactions', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: transactions, error: null })
    });
  });

  await page.route('**/api/v1/analysis', async (route) => {
    const total = transactions.reduce((sum, transaction) => sum + transaction.total, 0);
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          total_spend: total,
          transaction_count: transactions.length,
          anomalies: transactions.filter((transaction) => transaction.is_anomaly),
          category_totals: transactions.reduce((totals, transaction) => {
            totals[transaction.category] = (totals[transaction.category] || 0) + transaction.total;
            return totals;
          }, {}),
          daily_trend: transactions.map((transaction) => [transaction.date, transaction.total]),
          top_merchants: transactions.map((transaction) => [transaction.merchant, transaction.total]),
          merchant_totals: transactions.map((transaction) => [transaction.merchant, transaction.total])
        },
        error: null
      })
    });
  });

  await page.goto('/');
  await page.getByRole('link', { name: 'Transactions' }).click();

  const resetButton = page.locator('#reset-demo-data');
  await expect(resetButton).toBeVisible();
  await expect(resetButton).toHaveText('Reset demo');
  await expect(page.locator('#transaction-body tr')).toHaveCount(2);
  await expect(page.locator('.kpi-card strong')).toHaveText([/1,000\.00/, /1,000\.00/, '1', '2']);

  await resetButton.click();
  await expect(resetButton).toHaveText('Click again to reset');
  expect(deletedIds).toEqual([]);

  await resetButton.click();

  await expect(page.locator('#transaction-body tr')).toHaveCount(0);
  await expect(page.locator('.transaction-empty-state')).toBeVisible();
  await expect(page.locator('.kpi-card strong')).toHaveText([/0\.00/, /0\.00/, '0', '0']);
  await expect(page.locator('#toast-container')).toContainText('Demo data reset.');
  expect(deletedIds.sort()).toEqual(['txn-reset-1', 'txn-reset-2']);
});

test('reset demo button disarms and reports delete failures', async ({ page }) => {
  await mockChart(page);
  let transactions = [
    {
      id: 'txn-reset-fail',
      date: '2026-05-10',
      merchant: 'Protected Store',
      category: 'Groceries',
      total: 420,
      items: [],
      is_anomaly: false,
      is_duplicate: false
    }
  ];
  let deleteRequests = 0;

  await page.route('**/api/v1/transactions/*', async (route) => {
    deleteRequests += 1;
    await route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ success: false, data: null, error: { message: 'Delete failed' } })
    });
  });

  await page.route('**/api/v1/transactions', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: transactions, error: null })
    });
  });

  await page.route('**/api/v1/analysis', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          total_spend: transactions.reduce((sum, transaction) => sum + transaction.total, 0),
          transaction_count: transactions.length,
          anomalies: [],
          category_totals: { Groceries: 420 },
          daily_trend: [['2026-05-10', 420]],
          top_merchants: [['Protected Store', 420]],
          merchant_totals: [['Protected Store', 420]]
        },
        error: null
      })
    });
  });

  await page.goto('/');
  await page.getByRole('link', { name: 'Transactions' }).click();

  const resetButton = page.locator('#reset-demo-data');
  await resetButton.click();
  await expect(resetButton).toHaveText('Click again to reset');
  await expect(resetButton).toHaveText('Reset demo', { timeout: 6000 });

  await resetButton.click();
  await resetButton.click();

  await expect(page.locator('#toast-container .toast.error')).toContainText('Could not reset demo data.');
  await expect(page.locator('#transaction-body tr')).toHaveCount(1);
  expect(deleteRequests).toBe(1);
});
