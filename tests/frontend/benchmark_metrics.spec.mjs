import { expect, test } from '@playwright/test';

async function mockShell(page) {
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
          transaction_count: 0,
          anomalies: [],
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

test('renders collapsible benchmark metrics from generated results', async ({ page }) => {
  await mockShell(page);
  await page.route('**/api/v1/benchmark/results', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          summary: {
            ocr_accuracy: 0.942,
            field_extraction_accuracy: 0.917,
            categorization_f1: 0.88,
            duplicate_detection_rate: 1,
            anomaly_recall: 0.8,
            avg_pipeline_time_seconds: 8.3,
            bills_processed: 47
          },
          ocr: {
            cer: 0.058,
            wer: 0.09,
            field_detection_rate: 0.92
          },
          extraction: {
            date_parse_rate: 1,
            amount_accuracy_within_1_inr: 0.95
          },
          chatbot: {
            status: 'requires source logging or mocked chat evaluation cases'
          }
        },
        error: null
      })
    });
  });

  await page.goto('/');

  const toggle = page.locator('#benchmark-metrics-toggle');
  await expect(toggle).toBeVisible();
  await expect(page.locator('#benchmark-metrics-body')).toBeHidden();

  await toggle.click();

  await expect(toggle).toHaveText('Hide metrics');
  await expect(page.locator('#benchmark-metrics-body')).toBeVisible();
  await expect(page.locator('.metric-card')).toHaveCount(6);
  await expect(page.locator('#benchmark-metrics')).toContainText('OCR Accuracy');
  await expect(page.locator('#benchmark-metrics')).toContainText('94.2%');
  await expect(page.locator('#benchmark-metrics')).toContainText('Categorization F1');
  await expect(page.locator('#benchmark-metrics')).toContainText('88%');
  await expect(page.locator('#benchmark-metrics')).toContainText('Avg Pipeline Time');
  await expect(page.locator('#benchmark-metrics')).toContainText('8.30s');
  await expect(page.locator('#benchmark-metrics-details')).toContainText('Bills Processed');
  await expect(page.locator('#benchmark-metrics-details')).toContainText('47');
});

test('shows a graceful metrics empty state when results are unavailable', async ({ page }) => {
  await mockShell(page);
  await page.route('**/api/v1/benchmark/results', async (route) => {
    await route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({
        success: false,
        data: null,
        error: { code: 'benchmark_results_unavailable', message: 'Run the benchmark to populate system metrics.' }
      })
    });
  });

  await page.goto('/');
  await page.locator('#benchmark-metrics-toggle').click();

  await expect(page.locator('#benchmark-metrics-empty')).toBeVisible();
  await expect(page.locator('#benchmark-metrics-empty')).toHaveText('Run the benchmark to populate system metrics.');
  await expect(page.locator('.metric-card')).toHaveCount(0);
});
