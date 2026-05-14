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

test('renders external SROIE metrics as the headline evaluator section', async ({ page }) => {
  await mockShell(page);
  await page.route('**/api/v1/benchmark/results', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          summary: {
            headline_source: 'external',
            external_available: true,
            synthetic_regression_available: true
          },
          external_benchmarks: {
            sroie: {
              available: true,
              dataset: 'ICDAR2019-SROIE',
              purpose: 'Real receipt field extraction benchmark',
              limit: 25,
              metrics: {
                merchant_accuracy: 0.72,
                date_parse_rate: 0.88,
                total_amount_accuracy_within_1: 0.64,
                field_extraction_accuracy: 0.7467,
                ocr_accuracy: 0.81,
                cer: 0.19,
                wer: 0.31,
                avg_pipeline_time_seconds: 4.21,
                samples_processed: 25
              }
            },
            cord: { available: false, status: 'not generated' },
            funsd: { available: false, status: 'not generated' }
          },
          synthetic_regression: {
            available: true,
            dataset: 'FinSight generated synthetic bills',
            purpose: 'Internal regression check only',
            metrics: {
              summary: { ocr_accuracy: 1, field_extraction_accuracy: 1, categorization_f1: 1 }
            }
          }
        },
        error: null
      })
    });
  });

  await page.goto('/');
  await page.getByRole('button', { name: 'Metrics' }).click();

  const toggle = page.locator('#benchmark-metrics-toggle');
  await expect(toggle).toBeVisible();
  await expect(toggle).toHaveText('Hide metrics');
  await expect(page.locator('#benchmark-metrics-body')).toBeVisible();
  await expect(page.locator('.metric-card')).toHaveCount(6);
  await expect(page.locator('#benchmark-metrics')).toContainText('SROIE Receipt Benchmark');
  await expect(page.locator('#benchmark-metrics')).toContainText('Merchant/Company Accuracy');
  await expect(page.locator('#benchmark-metrics')).toContainText('56%');
  await expect(page.locator('#benchmark-metrics')).toContainText('Total Amount Accuracy');
  await expect(page.locator('#benchmark-metrics')).toContainText('64%');
  await expect(page.locator('#benchmark-metrics')).toContainText('Avg Pipeline Time');
  await expect(page.locator('#benchmark-metrics')).toContainText('2.33s');
  await expect(page.locator('#benchmark-metrics')).toContainText('Synthetic Regression Check');
  await expect(page.locator('#benchmark-metrics')).toContainText('CORD OCR/Layout Robustness');
  await expect(page.locator('#benchmark-metrics')).toContainText('FUNSD Structure Stress Test');
  await expect(page.locator('#benchmark-metrics')).toContainText('Performance Comparison');
  await expect(page.locator('#synthetic-regression-body')).toBeHidden();
  await expect(page.locator('#benchmark-metrics-summary')).not.toContainText('100%');
});
test('shows a graceful external benchmark empty state when external results are unavailable', async ({ page }) => {
  await mockShell(page);
  await page.route('**/api/v1/benchmark/results', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          summary: {
            headline_source: 'external',
            external_available: false,
            synthetic_regression_available: true
          },
          external_benchmarks: {
            sroie: { available: false, status: 'not generated' },
            cord: { available: false, status: 'not generated' },
            funsd: { available: false, status: 'not generated' }
          },
          synthetic_regression: {
            available: true,
            dataset: 'FinSight generated synthetic bills',
            purpose: 'Internal regression check only',
            metrics: { summary: { ocr_accuracy: 1 } }
          }
        },
        error: null
      })
    });
  });

  await page.goto('/');
  await page.getByRole('button', { name: 'Metrics' }).click();

  await expect(page.locator('#benchmark-metrics-empty')).toBeHidden();
  await expect(page.locator('.metric-card')).toHaveCount(6);
  await expect(page.locator('#benchmark-metrics')).toContainText('Synthetic Regression Check');
  await expect(page.locator('#benchmark-metrics')).toContainText('Performance Comparison');
});
