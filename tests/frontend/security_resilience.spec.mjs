import { expect, test } from '@playwright/test';

async function mockChart(page, body = null) {
  await page.route('https://cdn.jsdelivr.net/npm/chart.js', async (route) => {
    await route.fulfill({
      contentType: 'application/javascript',
      body:
        body ||
        `
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
}

async function mockDashboard(page, transactions = []) {
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
          total_spend: 0,
          category_totals: { Groceries: 10 },
          daily_trend: [['2026-05-10', 10]],
          top_merchants: [['Demo', 10]],
          merchant_totals: [['Demo', 10]]
        },
        error: null
      })
    });
  });
}

function extractionPayload() {
  return {
    merchant: { value: 'Demo Merchant', confidence: 0.9, raw_text: 'Demo Merchant' },
    date: { value: '2026-05-10', confidence: 0.9, raw_text: '2026-05-10' },
    subtotal: { value: 10, confidence: 0.9, raw_text: '10' },
    tax: { value: 0, confidence: 0.9, raw_text: '0' },
    total: { value: 10, confidence: 0.9, raw_text: '10' },
    payment_method: { value: 'UPI', confidence: 0.9, raw_text: 'UPI' },
    bill_number: { value: 'B-1', confidence: 0.9, raw_text: 'B-1' },
    items: { value: [], confidence: 0.9, raw_text: '' },
    extraction_model: 'test',
    ocr_engine: 'test',
    raw_ocr_text: 'Demo Merchant 10',
    metadata: {}
  };
}

test('renders API-controlled transaction text without executing markup', async ({ page }) => {
  await mockChart(page);
  await mockDashboard(page, [
    {
      id: 'txn-xss',
      date: '2026-05-10',
      merchant: '<img src=x onerror="window.__xssFired = true">',
      category: '<script>window.__xssFired = true</script>',
      total: 10,
      items: [{ name: '<svg onload="window.__xssFired = true">', total_price: 10 }],
      is_anomaly: false,
      is_duplicate: false
    }
  ]);

  await page.goto('/');

  await expect(page.locator('#transaction-body')).toContainText('<img src=x onerror="window.__xssFired = true">');
  await expect(page.locator('#transaction-body img')).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => window.__xssFired === true)).toBe(false);
});

test('blocks invalid confirmation edits with inline field errors', async ({ page }) => {
  await mockChart(page);
  await mockDashboard(page);

  let confirmRequests = 0;
  await page.route('**/api/v1/upload', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: [{ file_name: 'bill.png', upload_id: 'upload-1', extraction: extractionPayload() }],
        error: null
      })
    });
  });
  await page.route('**/api/v1/transactions/confirm', async (route) => {
    confirmRequests += 1;
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: {}, error: null })
    });
  });

  await page.goto('/');
  await page.locator('#file-input').setInputFiles({
    name: 'bill.png',
    mimeType: 'image/png',
    buffer: Buffer.from('fake image bytes')
  });

  await expect(page.locator('#extraction-preview')).toBeVisible();
  await page.locator('#extraction-preview input[name="merchant"]').fill('');
  await page.locator('#extraction-preview input[name="total"]').fill('abc');
  await page.locator('#extraction-preview input[name="date"]').fill('10/05/2026');
  await page.locator('#extraction-preview button', { hasText: 'Confirm' }).click();

  await expect(page.locator('#extraction-preview [data-field-error="merchant"]')).toContainText('Merchant is required.');
  await expect(page.locator('#extraction-preview [data-field-error="total"]')).toContainText('Amount must be a valid number.');
  await expect(page.locator('#extraction-preview [data-field-error="date"]')).toContainText('Date must use YYYY-MM-DD.');
  expect(confirmRequests).toBe(0);
});

test('shows a degraded chart state when chart rendering fails', async ({ page }) => {
  await mockChart(
    page,
    `
      window.Chart = class BrokenChart {
        constructor() {
          throw new Error('chart render failed');
        }
      };
    `
  );
  await mockDashboard(page);

  await page.goto('/');

  await expect(page.locator('#charts')).toContainText('Charts are temporarily unavailable.');
});
