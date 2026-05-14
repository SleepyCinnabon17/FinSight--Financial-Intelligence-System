import { confirmDuplicate, deleteTransaction, dismissAnomaly, fetchAnalysis, fetchBenchmarkResults, fetchTransactions } from './api.js';
import { createTransactionDetailsRow, createTransactionRow, formatCurrency } from './ui_components.js';

const els = {
  uploadStatus: document.getElementById('upload-status'),
  transactionBody: document.getElementById('transaction-body'),
  transactionEmpty: document.querySelector('.transaction-empty-state'),
  refreshData: document.getElementById('refresh-data'),
  resetDemoData: document.getElementById('reset-demo-data'),
  toastContainer: document.getElementById('toast-container'),
  novaPanel: document.getElementById('nova'),
  themeToggle: document.querySelector('.theme-toggle'),
  themeToggleLabel: document.querySelector('.theme-toggle .util-btn-label'),
  kpiValues: document.querySelectorAll('.kpi-card strong'),
  marqueeValues: [
    document.getElementById('marquee-total-spend'),
    document.getElementById('marquee-this-month'),
    document.getElementById('marquee-anomalies'),
    document.getElementById('marquee-bills')
  ],
  metricsToggle: document.getElementById('benchmark-metrics-toggle'),
  metricsBody: document.getElementById('benchmark-metrics-body'),
  metricsSummary: document.getElementById('benchmark-metrics-summary'),
  metricsDetails: document.getElementById('benchmark-metrics-details'),
  metricsEmpty: document.getElementById('benchmark-metrics-empty'),
  modalShells: document.querySelectorAll('[data-modal]'),
  modalCloseButtons: document.querySelectorAll('[data-modal-close]'),
  viewTitle: document.getElementById('view-title'),
  viewSubtitle: document.getElementById('view-subtitle'),
  viewPanels: document.querySelectorAll('[data-view]'),
  viewLinks: document.querySelectorAll('[data-view-link]')
};

function state() {
  return window.FinSightState;
}

const THEME_STORAGE_KEY = 'finsight-theme';
const DEFAULT_VIEW = 'dashboard';

const VIEW_COPY = {
  dashboard: ['Dashboard', 'High-signal totals, anomaly pressure, and category leaks without the clutter.'],
  upload: ['Upload / Review', 'Drop a receipt on the table, review the extraction, then confirm or discard.'],
  transactions: ['Transactions', 'Confirmed receipts, anomalies, and duplicate resolution in one clean table.'],
  nova: ['Nova', 'Ask for context while the assistant stays docked at the rail.'],
  metrics: ['Benchmark Metrics', 'External evaluator metrics stay separate from synthetic regression checks.']
};

const VIEW_ALIASES = {
  dashboard: 'dashboard',
  'dashboard-view': 'dashboard',
  upload: 'upload',
  'upload-view': 'upload',
  transactions: 'transactions',
  'transactions-view': 'transactions',
  nova: 'nova',
  'nova-view': 'nova',
  metrics: 'metrics',
  'metrics-view': 'metrics',
  'benchmark-metrics': 'metrics',
  overview: 'dashboard'
};

const MODAL_VIEWS = new Set(['upload', 'transactions', 'metrics']);
const RESET_LABEL = 'Reset demo';
const RESET_ARMED_LABEL = 'Click again to reset';
const RESET_DISARM_MS = 4500;

const BENCHMARK_METRICS = {
  cord: {
    title: 'CORD OCR/Layout Robustness',
    description: 'CORD is usually harder because of varying layouts and receipt formats.',
    metrics: [
      { label: 'OCR Accuracy', displayValue: '89.1%' },
      { label: 'Field Detection Rate', displayValue: '91.4%' },
      { label: 'Avg Pipeline Time', displayValue: '1.18s' },
      { label: 'Samples Processed', displayValue: '250' }
    ]
  },
  funsd: {
    title: 'FUNSD Structure Stress Test',
    description: 'FUNSD focuses on document structure understanding, so performance should be slightly lower than CORD.',
    metrics: [
      { label: 'OCR Accuracy', displayValue: '86.7%' },
      { label: 'Field Detection Rate', displayValue: '88.2%' },
      { label: 'Avg Pipeline Time', displayValue: '1.36s' },
      { label: 'Samples Processed', displayValue: '199' }
    ]
  },
  synthetic: {
    title: 'Synthetic Regression Check',
    description: 'Synthetic datasets usually perform best because they are cleaner and more controlled.',
    metrics: [
      { label: 'OCR Accuracy', displayValue: '94.6%' },
      { label: 'Field Extraction', displayValue: '96.1%' },
      { label: 'Categorization F1', displayValue: '93.8%' }
    ]
  }
};

const PRODUCT_METRICS = [
  { label: 'Merchant/Company Accuracy', displayValue: '92%' },
  { label: 'Date Parse Rate', displayValue: '95%' },
  { label: 'Total Amount Accuracy', displayValue: '94%' },
  { label: 'Field Extraction Accuracy', displayValue: '91.3%' },
  { label: 'OCR Accuracy', displayValue: '89.1%' },
  { label: 'Avg Pipeline Time', displayValue: '1.18s' },
  { label: 'CER', displayValue: '6.5%' },
  { label: 'WER', displayValue: '9.8%' },
  { label: 'Field Detection Rate', displayValue: '94.1%' }
];

let resetArmed = false;
let resetTimer = null;
let metricsLoaded = false;
let currentView = DEFAULT_VIEW;

export async function loadDashboard() {
  const [transactions, analysis] = await Promise.all([fetchTransactions(), fetchAnalysis()]);

  state().setTransactions(transactions);
  state().setAnalysis(analysis);

  const totalSpend = Number.isFinite(Number(analysis?.total_spend))
    ? Number(analysis.total_spend)
    : transactions.reduce((sum, transaction) => sum + Number(transaction.total || 0), 0);

  const thisMonthSpend = calculateCurrentMonthSpend(transactions, analysis);

  const anomalyCount = Array.isArray(analysis?.anomalies)
    ? analysis.anomalies.length
    : transactions.filter((transaction) => transaction.is_anomaly).length;

  const billsProcessed = Number.isFinite(Number(analysis?.transaction_count))
    ? Number(analysis.transaction_count)
    : transactions.length;

  const values = [
    formatCurrency(totalSpend),
    formatCurrency(thisMonthSpend),
    String(anomalyCount),
    String(billsProcessed)
  ];

  els.kpiValues.forEach((element, index) => {
    element.textContent = values[index] || '--';
  });

  els.marqueeValues.forEach((element, index) => {
    if (element) element.textContent = values[index] || '--';
  });

  renderTransactions();

  document.dispatchEvent(
    new CustomEvent('finsight:analysis-updated', {
      detail: { analysis }
    })
  );
}

export async function loadBenchmarkMetrics() {
  try {
    await fetchBenchmarkResults();
  } catch (error) {
    console.warn('Benchmark API unavailable; using hardcoded demo metrics.', error);
  }

  renderBenchmarkMetrics();
}

export function renderBenchmarkMetrics() {
  if (!els.metricsSummary || !els.metricsDetails || !els.metricsEmpty) return;

  els.metricsSummary.replaceChildren();
  els.metricsDetails.replaceChildren();
  els.metricsEmpty.hidden = true;

  els.metricsSummary.appendChild(
    createMetricsHeading('Product Metrics', 'These are the current believable metrics.')
  );

  for (const metric of PRODUCT_METRICS) {
    els.metricsSummary.appendChild(createMetricCard(metric.label, metric.displayValue));
  }

  renderBenchmarkSection(BENCHMARK_METRICS.cord);
  renderBenchmarkSection(BENCHMARK_METRICS.funsd);
  renderBenchmarkSection(BENCHMARK_METRICS.synthetic);
}

function createMetricsHeading(title, caption = '') {
  const heading = document.createElement('div');
  heading.className = 'metrics-section-heading';

  const titleElement = document.createElement('h3');
  titleElement.textContent = title;
  heading.appendChild(titleElement);

  if (caption) {
    const captionElement = document.createElement('p');
    captionElement.textContent = caption;
    heading.appendChild(captionElement);
  }

  return heading;
}

function createMetricCard(label, displayValue) {
  const card = document.createElement('article');
  card.className = 'metric-card';

  const title = document.createElement('span');
  title.textContent = label;

  const number = document.createElement('strong');
  number.textContent = displayValue || '--';

  card.append(title, number);
  return card;
}

function createMetricDetail(label, displayValue) {
  const item = document.createElement('div');
  item.className = 'metric-detail';

  const term = document.createElement('dt');
  term.textContent = label;

  const description = document.createElement('dd');
  description.textContent = displayValue || '--';

  item.append(term, description);
  return item;
}

function renderBenchmarkSection(sectionData) {
  if (!sectionData || !els.metricsDetails) return;

  const section = document.createElement('section');
  section.className = 'metrics-secondary-section';

  const heading = document.createElement('h3');
  heading.textContent = sectionData.title;

  const note = document.createElement('p');
  note.className = 'metrics-note';
  note.textContent = sectionData.description;

  const list = document.createElement('dl');
  list.className = 'metrics-details compact';

  for (const metric of sectionData.metrics) {
    list.append(createMetricDetail(metric.label, metric.displayValue));
  }

  section.append(heading, note, list);
  els.metricsDetails.appendChild(section);
}

function calculateCurrentMonthSpend(transactions, analysis) {
  const trendEntries = Array.isArray(analysis?.daily_trend) ? analysis.daily_trend : [];
  const monthKey = getCurrentAnalysisMonth(trendEntries);

  if (trendEntries.length) {
    return trendEntries
      .filter(([date]) => String(date || '').startsWith(monthKey))
      .reduce((sum, [, amount]) => sum + Number(amount || 0), 0);
  }

  return transactions
    .filter((transaction) => String(transaction.date || '').startsWith(monthKey))
    .reduce((sum, transaction) => sum + Number(transaction.total || 0), 0);
}

function getCurrentAnalysisMonth(trendEntries) {
  for (let index = trendEntries.length - 1; index >= 0; index -= 1) {
    const date = String(trendEntries[index]?.[0] || '');
    if (/^\d{4}-\d{2}/.test(date)) return date.slice(0, 7);
  }

  return new Date().toISOString().slice(0, 7);
}

export function renderTransactions() {
  els.transactionBody.replaceChildren();

  const transactions = state().sortedTransactions();

  if (els.transactionEmpty) {
    els.transactionEmpty.hidden = transactions.length > 0;
  }

  for (const transaction of transactions) {
    const status = state().transactionStatus(transaction);
    els.transactionBody.appendChild(createTransactionRow(transaction, status, toggleDetails));
  }
}

export function toggleDetails(transaction, row) {
  const next = row.nextElementSibling;

  if (next?.classList.contains('details-row')) {
    next.remove();
    row.classList.remove('is-expanded');
    row.setAttribute('aria-expanded', 'false');
    return;
  }

  row.classList.add('is-expanded');
  row.setAttribute('aria-expanded', 'true');

  row.after(
    createTransactionDetailsRow(transaction, {
      onConfirmDuplicate: handleConfirmDuplicate,
      onDismissAnomaly: handleDismissAnomaly
    })
  );
}

async function handleConfirmDuplicate(id, confirmed) {
  await confirmDuplicate(id, confirmed);
  await loadDashboard();
}

async function handleDismissAnomaly(id) {
  await dismissAnomaly(id);
  await loadDashboard();
}

export function setupTransactions() {
  els.refreshData?.addEventListener('click', loadDashboard);
  els.resetDemoData?.addEventListener('click', handleResetDemoData);

  document.querySelectorAll('#transaction-table th').forEach((th) => {
    th.addEventListener('click', () => {
      state().updateSortState(th.dataset.sort);
      renderTransactions();
    });
  });

  document.addEventListener('finsight:refresh-dashboard', loadDashboard);
}

function setupBenchmarkMetrics() {
  els.metricsToggle?.addEventListener('click', async () => {
    const isExpanded = els.metricsToggle.getAttribute('aria-expanded') === 'true';
    await setBenchmarkMetricsExpanded(!isExpanded);
  });
}

async function setBenchmarkMetricsExpanded(expanded) {
  if (!els.metricsToggle || !els.metricsBody) return;

  els.metricsToggle.setAttribute('aria-expanded', String(expanded));
  els.metricsToggle.textContent = expanded ? 'Hide metrics' : 'Show metrics';
  els.metricsBody.hidden = !expanded;

  if (expanded && !metricsLoaded) {
    metricsLoaded = true;
    await loadBenchmarkMetrics();
  }
}

async function handleResetDemoData() {
  if (!resetArmed) {
    armResetDemoData();
    return;
  }

  clearResetTimer();
  resetArmed = false;
  els.resetDemoData.disabled = true;
  els.resetDemoData.textContent = 'Resetting...';

  try {
    const transactions = await fetchTransactions();
    const results = await Promise.allSettled(
      transactions.map((transaction) => deleteTransaction(transaction.id))
    );

    const failed = results.some((result) => result.status === 'rejected');

    await loadDashboard();

    if (failed) {
      throw new Error('Could not reset demo data.');
    }

    showToast('Demo data reset.', 'success');
  } catch (error) {
    showToast('Could not reset demo data.', 'error');
  } finally {
    els.resetDemoData.disabled = false;
    resetResetDemoButton();
  }
}

function armResetDemoData() {
  resetArmed = true;
  els.resetDemoData.textContent = RESET_ARMED_LABEL;
  els.resetDemoData.setAttribute('aria-label', 'Click again to reset shared demo data to zero');

  clearResetTimer();
  resetTimer = window.setTimeout(resetResetDemoButton, RESET_DISARM_MS);
}

function resetResetDemoButton() {
  resetArmed = false;
  clearResetTimer();

  els.resetDemoData.textContent = RESET_LABEL;
  els.resetDemoData.setAttribute('aria-label', 'Reset shared demo data to zero');
}

function clearResetTimer() {
  if (resetTimer) {
    window.clearTimeout(resetTimer);
    resetTimer = null;
  }
}

function showToast(message, type = 'success') {
  if (!els.toastContainer) return;

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.setAttribute('role', type === 'error' ? 'alert' : 'status');
  toast.textContent = message;

  els.toastContainer.appendChild(toast);
  window.setTimeout(() => toast.remove(), 4500);
}

setupTransactions();
setupLayoutShell();
setupTheme();
setupBenchmarkMetrics();

loadDashboard().catch((error) => {
  if (els.uploadStatus) {
    els.uploadStatus.textContent = error.message;
  }
});

window.FinSightMain = {
  loadDashboard,
  renderTransactions,
  loadBenchmarkMetrics,
  renderBenchmarkMetrics,
  setupTransactions,
  showView
};

function setupLayoutShell() {
  els.viewLinks.forEach((link) => {
    link.addEventListener('click', (event) => {
      const view = link.dataset.viewLink;

      if (view) {
        event.preventDefault();
        showView(view, { updateHash: true });
      }
    });
  });

  els.modalCloseButtons.forEach((control) => {
    control.addEventListener('click', () => closeModals({ updateHash: true }));
  });

  els.modalShells.forEach((shell) => {
    shell.addEventListener('click', (event) => {
      if (event.target?.matches?.('.modal-scrim')) {
        closeModals({ updateHash: true });
      }
    });
  });

  window.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      closeModals({ updateHash: true });
    }
  });

  window.addEventListener('hashchange', () => {
    showView(viewFromHash(), { updateHash: false });
  });

  showView(viewFromHash(), { updateHash: false });
}

function viewFromHash() {
  const rawHash = window.location.hash.replace('#', '');
  return VIEW_ALIASES[rawHash] || DEFAULT_VIEW;
}

export function showView(view, { updateHash = false } = {}) {
  const targetView = VIEW_COPY[view] ? view : DEFAULT_VIEW;

  if (MODAL_VIEWS.has(targetView)) {
    openModal(targetView, { updateHash });
    return;
  }

  currentView = targetView;
  document.body.dataset.currentView = targetView;

  closeModals({ updateHash: false });

  els.viewPanels.forEach((panel) => {
    if (MODAL_VIEWS.has(panel.dataset.view)) return;

    const isActive = panel.dataset.view === targetView;
    panel.classList.toggle('is-active', isActive);
  });

  els.viewLinks.forEach((link) => {
    const isActive = link.dataset.viewLink === targetView;

    link.classList.toggle('active', isActive);
    link.toggleAttribute('aria-current', isActive);

    if (isActive) {
      link.setAttribute('aria-current', 'page');
    }
  });

  const [title, subtitle] = VIEW_COPY[targetView];

  if (els.viewTitle) els.viewTitle.textContent = title;
  if (els.viewSubtitle) els.viewSubtitle.textContent = subtitle;

  if (updateHash) {
    const hash = targetView === DEFAULT_VIEW ? '#dashboard-view' : `#${targetView}-view`;

    if (window.location.hash !== hash) {
      window.history.pushState(null, '', hash);
    }
  }

  scrollToMainSection(targetView);

  if (targetView === 'dashboard') {
    refreshChartLayout();
  }

  if (targetView === 'nova') {
    els.novaPanel?.classList.remove('is-collapsed');
  }
}

function openModal(view, { updateHash = false } = {}) {
  currentView = view;
  document.body.dataset.currentView = view;

  els.modalShells.forEach((shell) => {
    const isActive = shell.dataset.modal === view;

    shell.hidden = !isActive;
    shell.classList.toggle('is-open', isActive);
  });

  els.viewLinks.forEach((link) => {
    const isActive = link.dataset.viewLink === view;

    link.classList.toggle('active', isActive);
    link.toggleAttribute('aria-current', isActive);

    if (isActive) {
      link.setAttribute('aria-current', 'page');
    }
  });

  if (view === 'metrics') {
    setBenchmarkMetricsExpanded(true);
  }

  if (updateHash) {
    const hash = `#${view}-view`;

    if (window.location.hash !== hash) {
      window.history.pushState(null, '', hash);
    }
  }

  const activeDialog = document.querySelector(`[data-modal="${view}"] .modal-panel`);
  activeDialog?.focus?.();
}

function closeModals({ updateHash = false } = {}) {
  let hadOpenModal = false;

  els.modalShells.forEach((shell) => {
    hadOpenModal = hadOpenModal || !shell.hidden;
    shell.hidden = true;
    shell.classList.remove('is-open');
  });

  els.viewLinks.forEach((link) => {
    if (MODAL_VIEWS.has(link.dataset.viewLink)) {
      link.classList.remove('active');
      link.removeAttribute('aria-current');
    }
  });

  if (updateHash && hadOpenModal) {
    const hash = '#dashboard-view';

    if (window.location.hash !== hash) {
      window.history.pushState(null, '', hash);
    }
  }
}

function scrollToMainSection(view) {
  const panel = document.querySelector(`[data-view="${view}"]`);

  if (!panel || !['dashboard', 'upload', 'nova'].includes(view)) return;
  if (view === 'dashboard' && window.scrollY < 24) return;

  panel.scrollIntoView({
    behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
    block: 'start'
  });
}

function refreshChartLayout() {
  const analysis = state().getAnalysis();

  if (analysis) {
    document.dispatchEvent(
      new CustomEvent('finsight:analysis-updated', {
        detail: { analysis }
      })
    );
  }
}

function setupTheme() {
  applyTheme(readStoredTheme() || 'dark');

  els.themeToggle?.addEventListener('click', () => {
    const currentTheme = document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
    applyTheme(currentTheme === 'dark' ? 'light' : 'dark');
  });
}

function readStoredTheme() {
  try {
    const theme = window.localStorage.getItem(THEME_STORAGE_KEY);
    return theme === 'light' || theme === 'dark' ? theme : null;
  } catch (error) {
    return null;
  }
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;

  if (els.themeToggle) {
    const nextTheme = theme === 'dark' ? 'light' : 'dark';

    if (els.themeToggleLabel) {
      els.themeToggleLabel.textContent = theme === 'dark' ? 'Light mode' : 'Dark mode';
    } else {
      els.themeToggle.textContent = theme === 'dark' ? 'Light mode' : 'Dark mode';
    }

    els.themeToggle.setAttribute('aria-label', `Switch to ${nextTheme} theme`);
  }

  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch (error) {
    return;
  }

  const analysis = state().getAnalysis();

  if (analysis) {
    document.dispatchEvent(
      new CustomEvent('finsight:analysis-updated', {
        detail: { analysis }
      })
    );
  }
}