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
  await page.getByRole('tab', { name: 'Transactions' }).click();

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
  await page.getByRole('tab', { name: 'Upload' }).click();
  await page.locator('#file-input').setInputFiles({
    name: 'bill.png',
    mimeType: 'image/png',
    buffer: Buffer.from('fake image bytes')
  });
  await page.locator('#process-btn').click();

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
test('shows upload previews, progress states, and confirm/discard toasts', async ({ page }) => {
  await mockChart(page);
  await mockDashboard(page);

  let uploadIndex = 0;
  let confirmRequests = 0;
  let discardRequests = 0;

  await page.route('**/api/v1/upload', async (route) => {
    uploadIndex += 1;
    await new Promise((resolve) => setTimeout(resolve, 400));
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: [{ file_name: 'bill.pdf', upload_id: `upload-${uploadIndex}`, extraction: extractionPayload() }],
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
  await page.route('**/api/v1/transactions/discard', async (route) => {
    discardRequests += 1;
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: {}, error: null })
    });
  });

  await page.goto('/');
  await page.getByRole('tab', { name: 'Upload' }).click();
  await page.locator('#file-input').setInputFiles([
    {
      name: 'bill.png',
      mimeType: 'image/png',
      buffer: Buffer.from('fake image bytes')
    },
    {
      name: 'statement.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('%PDF-1.4 fake pdf bytes')
    }
  ]);
  await expect(page.locator('#process-btn')).toHaveClass(/ready/);
  await page.locator('#process-btn').click();

  await expect(page.locator('#preview-strip img')).toHaveCount(1);
  await expect(page.locator('#preview-strip')).toContainText('statement.pdf');
  await expect(page.locator('#upload-status')).toContainText('Processing OCR');
  await expect(page.locator('#upload-status')).toContainText('Extraction ready for review.');

  await page.locator('#extraction-preview button', { hasText: 'Confirm' }).click();
  await expect(page.locator('#toast-container')).toContainText('Transaction confirmed.');
  expect(confirmRequests).toBe(1);

  await page.locator('#file-input').setInputFiles({
    name: 'statement.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.4 second fake pdf bytes')
  });
  await page.locator('#process-btn').click();
  await expect(page.locator('#extraction-preview')).toBeVisible();
  await page.locator('#extraction-preview button', { hasText: 'Discard' }).click();
  await expect(page.locator('#toast-container')).toContainText('Upload discarded.');
  expect(discardRequests).toBe(1);
});

test('shows a non-blocking upload toast on network failure', async ({ page }) => {
  await mockChart(page);
  await mockDashboard(page);

  await page.route('**/api/v1/upload', async (route) => {
    await route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ success: false, data: null, error: { message: 'OCR service unavailable' } })
    });
  });

  await page.goto('/');
  await page.getByRole('tab', { name: 'Upload' }).click();
  await page.locator('#file-input').setInputFiles({
    name: 'bill.png',
    mimeType: 'image/png',
    buffer: Buffer.from('fake image bytes')
  });
  await page.locator('#process-btn').click();

  await expect(page.locator('#upload-status')).toContainText('OCR service unavailable');
  await expect(page.locator('#toast-container .toast.error')).toContainText('OCR service unavailable');
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
