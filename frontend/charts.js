const charts = { donut: null, line: null, bar: null };

export function updateCharts(analysis) {
  try {
    clearChartErrors();
    if (!window.Chart || !analysis) return;
    const categoryEntries = Object.entries(analysis.category_totals || {});
    const trendEntries = analysis.daily_trend || [];
    const merchantEntries = analysis.top_merchants || analysis.merchant_totals || [];
    const palette = chartPalette();
    const configs = [
      ['donut', 'category-chart', 'doughnut', categoryEntries.map(([key]) => key), categoryEntries.map(([, value]) => value)],
      ['line', 'trend-chart', 'line', trendEntries.map(([key]) => key), trendEntries.map(([, value]) => value)],
      ['bar', 'merchant-chart', 'bar', merchantEntries.map(([key]) => key), merchantEntries.map(([, value]) => value)]
    ];
    for (const [slot, id, type, labels, data] of configs) {
      const ctx = document.getElementById(id);
      if (charts[slot]) charts[slot].destroy();
      charts[slot] = new Chart(ctx, {
        type,
        data: { labels, datasets: [{ data, label: 'Spend', backgroundColor: palette, borderColor: palette[0] }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: type === 'doughnut' } } }
      });
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

document.addEventListener('finsight:analysis-updated', (event) => updateCharts(event.detail?.analysis));
window.addEventListener('resize', resizeCharts);

window.FinSightCharts = { updateCharts, resizeCharts, clearCharts };
