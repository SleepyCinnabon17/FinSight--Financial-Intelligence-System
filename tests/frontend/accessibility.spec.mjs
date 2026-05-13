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
      body: JSON.stringify({
        success: true,
        data: [
          {
            id: 'txn-1',
            date: '2026-05-10',
            merchant: 'Metro Market',
            category: 'Groceries',
            total: 1280,
            bill_number: 'B-1',
            payment_method: 'UPI',
            items: [],
            is_anomaly: false,
            is_duplicate: false
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
}

test('exposes accessible landmarks, live regions, and keyboard table controls', async ({ page }) => {
  await mockDashboard(page);
  await page.goto('/');

  await expect(page.getByRole('navigation', { name: 'Main sections' })).toBeVisible();
  await expect(page.getByRole('main')).toBeVisible();
  await expect(page.locator('#chat-bubbles')).toHaveAttribute('role', 'log');
  await expect(page.locator('#upload-status')).toHaveAttribute('aria-live', 'polite');
  await expect(page.locator('#toast-container')).toHaveAttribute('aria-live', 'polite');
  await expect(page.locator('#drop-zone')).toHaveAttribute('role', 'button');
  await expect(page.locator('#transaction-table th button.sort-button')).toHaveCount(5);

  await page.getByRole('tab', { name: 'Transactions' }).click();
  await page.locator('#transaction-body tr.transaction-row').focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('.details-row')).toBeVisible();
});

test('theme token text colors meet WCAG AA contrast against surfaces', async ({ page }) => {
  await mockDashboard(page);
  await page.goto('/');

  const results = await page.evaluate(() => {
    function parseHex(value) {
      const hex = value.trim().replace('#', '');
      const normalized = hex.length === 3 ? hex.split('').map((part) => part + part).join('') : hex;
      return [0, 2, 4].map((start) => Number.parseInt(normalized.slice(start, start + 2), 16) / 255);
    }

    function luminance(hex) {
      return parseHex(hex).map((channel) => {
        if (channel <= 0.03928) return channel / 12.92;
        return ((channel + 0.055) / 1.055) ** 2.4;
      }).reduce((total, channel, index) => total + channel * [0.2126, 0.7152, 0.0722][index], 0);
    }

    function contrast(foreground, background) {
      const lighter = Math.max(luminance(foreground), luminance(background));
      const darker = Math.min(luminance(foreground), luminance(background));
      return (lighter + 0.05) / (darker + 0.05);
    }

    const themes = ['dark', 'light'];
    const tokens = ['--text-primary', '--text-secondary', '--accent', '--success', '--warning', '--error', '--duplicate'];
    return themes.flatMap((theme) => {
      document.documentElement.dataset.theme = theme;
      const styles = getComputedStyle(document.documentElement);
      const surface = styles.getPropertyValue('--surface').trim();
      return tokens.map((token) => ({
        theme,
        token,
        ratio: contrast(styles.getPropertyValue(token).trim(), surface)
      }));
    });
  });

  for (const result of results) {
    expect(result.ratio, `${result.theme} ${result.token}`).toBeGreaterThanOrEqual(4.5);
  }
});
