const charts = { donut: null, line: null, bar: null };
let resizeFrame = null;

const EMPTY_MESSAGES = {
  donut: 'No category spend yet.',
  line: 'No trend data yet.',
  bar: 'No merchant spend yet.'
};

export function updateCharts(analysis) {
  try {
    clearChartErrors();
    if (!window.Chart || !analysis) return;
    const categoryEntries = Object.entries(analysis.category_totals || {});
    const trendEntries = analysis.daily_trend || [];
    const merchantEntries = analysis.top_merchants || analysis.merchant_totals || [];
    const palette = chartPalette();
    const theme = chartTheme();
    const configs = [
      ['donut', 'category-chart', 'doughnut', categoryEntries.map(([key]) => key), categoryEntries.map(([, value]) => value)],
      ['line', 'trend-chart', 'line', trendEntries.map(([key]) => key), trendEntries.map(([, value]) => value)],
      ['bar', 'merchant-chart', 'bar', merchantEntries.map(([key]) => key), merchantEntries.map(([, value]) => value)]
    ];
    for (const [slot, id, type, labels, data] of configs) {
      const ctx = document.getElementById(id);
      const box = ctx?.closest('.chart-box');
      if (charts[slot]) charts[slot].destroy();
      charts[slot] = null;
      if (!hasChartData(labels, data)) {
        showEmptyState(box, EMPTY_MESSAGES[slot]);
        if (ctx) ctx.hidden = true;
        continue;
      }
      clearEmptyState(box);
      if (ctx) ctx.hidden = false;
      charts[slot] = new Chart(ctx, {
        type,
        data: {
          labels,
          datasets: [
            {
              data,
              label: 'Spend',
              backgroundColor: palette,
              borderColor: palette[0],
              pointBackgroundColor: palette[0],
              tension: type === 'line' ? 0.32 : 0
            }
          ]
        },
        options: chartOptions(type, theme)
      });
      box?.classList.add('has-data');
    }
  } catch (error) {
    clearCharts();
    showChartErrors('Charts are temporarily unavailable.');
  }
}

export function resizeCharts() {
  Object.values(charts).forEach((chart) => {
    if (chart && typeof chart.resize === 'function') chart.resize();
  });
}

export function clearCharts() {
  for (const slot of Object.keys(charts)) {
    if (charts[slot]) charts[slot].destroy();
    charts[slot] = null;
  }
}

function chartBoxes() {
  return document.querySelectorAll('.chart-box');
}

function clearChartErrors() {
  chartBoxes().forEach((box) => {
    box.querySelectorAll('[data-chart-error]').forEach((message) => message.remove());
  });
}

function hasChartData(labels, data) {
  return labels.length > 0 && data.some((value) => Number(value) !== 0);
}

function showEmptyState(box, message) {
  if (!box) return;
  box.classList.remove('has-data');
  box.classList.add('is-empty');
  let emptyState = box.querySelector('.chart-empty-state');
  if (!emptyState) {
    emptyState = document.createElement('div');
    emptyState.className = 'chart-empty-state';
    const icon = document.createElement('span');
    icon.className = 'chart-empty-icon';
    icon.setAttribute('aria-hidden', 'true');
    const text = document.createElement('p');
    emptyState.append(icon, text);
    box.appendChild(emptyState);
  }
  emptyState.querySelector('p').textContent = message;
}

function clearEmptyState(box) {
  if (!box) return;
  box.classList.remove('is-empty');
  box.querySelectorAll('.chart-empty-state').forEach((message) => message.remove());
}

function showChartErrors(message) {
  chartBoxes().forEach((box) => {
    if (box.querySelector('[data-chart-error]')) return;
    const error = document.createElement('p');
    error.className = 'chart-error';
    error.dataset.chartError = 'true';
    error.textContent = message;
    box.appendChild(error);
  });
}

function chartPalette() {
  const styles = getComputedStyle(document.documentElement);
  return [1, 2, 3, 4, 5, 6].map((index) => styles.getPropertyValue(`--chart-${index}`).trim());
}

function chartTheme() {
  const styles = getComputedStyle(document.documentElement);
  return {
    border: styles.getPropertyValue('--border').trim(),
    muted: styles.getPropertyValue('--muted').trim(),
    text: styles.getPropertyValue('--text').trim()
  };
}

function chartOptions(type, theme) {
  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: type === 'doughnut',
        labels: { color: theme.muted }
      }
    }
  };

  if (type !== 'doughnut') {
    options.scales = {
      x: {
        ticks: { color: theme.muted },
        grid: { color: theme.border }
      },
      y: {
        ticks: { color: theme.muted },
        grid: { color: theme.border }
      }
    };
  }

  return options;
}

function scheduleResize() {
  if (resizeFrame) window.cancelAnimationFrame(resizeFrame);
  resizeFrame = window.requestAnimationFrame(() => {
    resizeFrame = null;
    resizeCharts();
  });
}

document.addEventListener('finsight:analysis-updated', (event) => updateCharts(event.detail?.analysis));
window.addEventListener('resize', scheduleResize);

if ('ResizeObserver' in window) {
  const resizeObserver = new ResizeObserver(scheduleResize);
  chartBoxes().forEach((box) => resizeObserver.observe(box));
}

window.FinSightCharts = { updateCharts, resizeCharts, clearCharts };
