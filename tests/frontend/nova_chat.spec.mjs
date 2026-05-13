import { expect, test } from '@playwright/test';

async function mockShellData(page) {
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

async function installChatStreamMock(page) {
  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);
    const encoder = new TextEncoder();
    const eventChunk = (value) => encoder.encode(`data: ${value}${String.fromCharCode(10)}${String.fromCharCode(10)}`);
    window.__chatAbortObserved = false;
    window.__chatRequests = [];
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: async (value) => {
          window.__copied = value;
        }
      }
    });

    window.fetch = (input, options = {}) => {
      const url = typeof input === 'string' ? input : input.url;
      if (!url.endsWith('/api/v1/chat')) {
        return nativeFetch(input, options);
      }

      const payload = JSON.parse(options.body || '{}');
      window.__chatRequests.push(payload.message);
      const timers = [];
      const stream = new ReadableStream({
        start(controller) {
          const abort = () => {
            window.__chatAbortObserved = true;
            timers.forEach((timer) => clearTimeout(timer));
            try {
              controller.error(new DOMException('Aborted', 'AbortError'));
            } catch (error) {
              return;
            }
          };
          options.signal?.addEventListener('abort', abort, { once: true });
          if (payload.message.includes('long')) {
            timers.push(
              setTimeout(() => {
                controller.enqueue(eventChunk('delayed token'));
              }, 1000)
            );
            return;
          }
          timers.push(
            setTimeout(() => {
              controller.enqueue(eventChunk('Nova '));
            }, 40)
          );
          timers.push(
            setTimeout(() => {
              controller.enqueue(eventChunk('reply'));
              controller.close();
            }, 90)
          );
        },
        cancel() {
          window.__chatAbortObserved = true;
          timers.forEach((timer) => clearTimeout(timer));
        }
      });

      return Promise.resolve(
        new Response(stream, {
          status: 200,
          headers: { 'Content-Type': 'text/event-stream' }
        })
      );
    };
  });
}

test('streams Nova messages with status, typing, copy, and stop controls', async ({ page }) => {
  await installChatStreamMock(page);
  await mockShellData(page);
  await page.goto('/');

  await page.locator('#chat-input').fill('summarize spend');
  await page.locator('#chat-form button[type="submit"]').click();

  await expect(page.locator('.bubble.user')).toContainText('summarize spend');
  await expect(page.locator('.bubble.nova')).toContainText('Nova reply');
  await expect(page.locator('#chat-status-text')).toContainText('Idle');
  await expect(page.locator('#chat-typing')).toBeHidden();

  await page.locator('.bubble.nova .bubble-copy').last().click();
  await expect.poll(() => page.evaluate(() => window.__copied)).toBe('Nova reply');

  await page.locator('#chat-input').fill('long answer');
  await page.locator('#chat-form button[type="submit"]').click();
  await expect(page.locator('#chat-stop-button')).toBeVisible();
  await expect(page.locator('#chat-status-text')).toContainText('Connected');
  await expect(page.locator('#chat-typing')).toBeVisible();
  await page.locator('#chat-stop-button').click();
  await expect(page.locator('#chat-status-text')).toContainText('Idle');
  await expect(page.locator('#chat-stop-button')).toBeHidden();
  await expect.poll(() => page.evaluate(() => window.__chatAbortObserved)).toBe(true);
});
