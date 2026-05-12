import { confirmDuplicate, deleteTransaction, dismissAnomaly, fetchAnalysis, fetchBenchmarkResults, fetchTransactions } from './api.js';
import { createTransactionDetailsRow, createTransactionRow, formatCurrency } from './ui_components.js';

const els = {
  uploadStatus: document.getElementById('upload-status'),
  transactionBody: document.getElementById('transaction-body'),
  transactionEmpty: document.querySelector('.transaction-empty-state'),
  refreshData: document.getElementById('refresh-data'),
  resetDemoData: document.getElementById('reset-demo-data'),
  toastContainer: document.getElementById('toast-container'),
  sidebar: document.querySelector('.sidebar'),
  sidebarToggle: document.getElementById('sidebar-toggle'),
  novaPanel: document.getElementById('nova'),
  novaToggle: document.querySelector('.nova-toggle'),
  themeToggle: document.querySelector('.theme-toggle'),
  kpiValues: document.querySelectorAll('.kpi-card strong'),
  metricsToggle: document.getElementById('benchmark-metrics-toggle'),
  metricsBody: document.getElementById('benchmark-metrics-body'),
  metricsSummary: document.getElementById('benchmark-metrics-summary'),
  metricsDetails: document.getElementById('benchmark-metrics-details'),
  metricsEmpty: document.getElementById('benchmark-metrics-empty')
};

const THEME_STORAGE_KEY = 'finsight-theme';
const RESET_LABEL = 'Reset demo';
const RESET_ARMED_LABEL = 'Click again to reset';
const RESET_DISARM_MS = 4500;
const SUMMARY_METRICS = [
  ['OCR Accuracy', ['summary', 'ocr_accuracy'], 'percent'],
  ['Field Extraction', ['summary', 'field_extraction_accuracy'], 'percent'],
  ['Categorization F1', ['summary', 'categorization_f1'], 'percent'],
  ['Duplicate Detection', ['summary', 'duplicate_detection_rate'], 'percent'],
  ['Anomaly Recall', ['summary', 'anomaly_recall'], 'percent'],
  ['Avg Pipeline Time', ['summary', 'avg_pipeline_time_seconds'], 'seconds']
];
const DETAIL_METRICS = [
  ['CER', ['ocr', 'cer'], 'percent'],
  ['WER', ['ocr', 'wer'], 'percent'],
  ['Field Detection Rate', ['ocr', 'field_detection_rate'], 'percent'],
  ['Date Parse Rate', ['extraction', 'date_parse_rate'], 'percent'],
  ['Amount Accuracy', ['extraction', 'amount_accuracy_within_1_inr'], 'percent'],
  ['Bills Processed', ['summary', 'bills_processed'], 'number']
];
let resetArmed = false;
let resetTimer = null;
let metricsLoaded = false;

function state() {
  return window.FinSightState;
}

export async function loadDashboard() {
  const [transactions, analysis] = await Promise.all([fetchTransactions(), fetchAnalysis()]);
  state().setTransactions(transactions);
  state().setAnalysis(analysis);
  renderTransactions();
  renderKpis(transactions, analysis);
  document.dispatchEvent(new CustomEvent('finsight:analysis-updated', { detail: { analysis } }));
}

export function renderKpis(transactions = [], analysis = {}) {
  const totalSpend = Number(analysis?.total_spend || 0);
  const thisMonthSpend = calculateCurrentMonthSpend(transactions, analysis);
  const anomalyCount = Array.isArray(analysis?.anomalies)
    ? analysis.anomalies.length
    : transactions.filter((transaction) => transaction.is_anomaly).length;
  const billsProcessed = Number.isFinite(Number(analysis?.transaction_count))
    ? Number(analysis.transaction_count)
    : transactions.length;
  const values = [formatCurrency(totalSpend), formatCurrency(thisMonthSpend), String(anomalyCount), String(billsProcessed)];
  els.kpiValues.forEach((element, index) => {
    element.textContent = values[index] || '--';
  });
}

export async function loadBenchmarkMetrics() {
  try {
    const results = await fetchBenchmarkResults();
    renderBenchmarkMetrics(results);
  } catch (error) {
    renderBenchmarkMetrics(null);
  }
}

export function renderBenchmarkMetrics(results) {
  if (!els.metricsSummary || !els.metricsDetails || !els.metricsEmpty) return;
  els.metricsSummary.replaceChildren();
  els.metricsDetails.replaceChildren();
  if (!results?.summary) {
    els.metricsEmpty.hidden = false;
    return;
  }
  els.metricsEmpty.hidden = true;
  for (const [label, path, format] of SUMMARY_METRICS) {
    els.metricsSummary.appendChild(createMetricCard(label, getMetricValue(results, path), format));
  }
  for (const [label, path, format] of DETAIL_METRICS) {
    els.metricsDetails.appendChild(createMetricDetail(label, getMetricValue(results, path), format));
  }
  if (results.chatbot?.status) {
    els.metricsDetails.appendChild(createMetricDetail('Nova Metrics', results.chatbot.status, 'text'));
  }
}

function createMetricCard(label, value, format) {
  const card = document.createElement('article');
  card.className = 'metric-card';
  const title = document.createElement('span');
  title.textContent = label;
  const number = document.createElement('strong');
  number.textContent = formatMetricValue(value, format);
  card.append(title, number);
  return card;
}

function createMetricDetail(label, value, format) {
  const item = document.createElement('div');
  item.className = 'metric-detail';
  const term = document.createElement('dt');
  term.textContent = label;
  const description = document.createElement('dd');
  description.textContent = formatMetricValue(value, format);
  item.append(term, description);
  return item;
}

function getMetricValue(source, path) {
  return path.reduce((value, key) => (value && value[key] !== undefined ? value[key] : null), source);
}

function formatMetricValue(value, format) {
  if (value === null || value === undefined || value === '') return '--';
  if (format === 'percent') return `${Math.round(Number(value) * 1000) / 10}%`;
  if (format === 'seconds') return `${Number(value).toFixed(2)}s`;
  if (format === 'number') return String(value);
  return String(value);
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
  els.refreshData.addEventListener('click', loadDashboard);
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
    els.metricsToggle.setAttribute('aria-expanded', String(!isExpanded));
    els.metricsToggle.textContent = isExpanded ? 'Show metrics' : 'Hide metrics';
    if (els.metricsBody) {
      els.metricsBody.hidden = isExpanded;
    }
    if (!isExpanded && !metricsLoaded) {
      metricsLoaded = true;
      await loadBenchmarkMetrics();
    }
  });
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
    const results = await Promise.allSettled(transactions.map((transaction) => deleteTransaction(transaction.id)));
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
  els.uploadStatus.textContent = error.message;
});

window.FinSightMain = { loadDashboard, renderTransactions, renderKpis, loadBenchmarkMetrics, renderBenchmarkMetrics, setupTransactions };

function setupLayoutShell() {
  els.sidebarToggle?.addEventListener('click', () => {
    const isOpen = els.sidebar?.classList.toggle('is-open') || false;
    els.sidebarToggle.setAttribute('aria-expanded', String(isOpen));
  });

  els.novaToggle?.addEventListener('click', () => {
    const isCollapsed = els.novaPanel?.classList.toggle('is-collapsed') || false;
    els.novaToggle.setAttribute('aria-expanded', String(!isCollapsed));
    els.novaToggle.textContent = isCollapsed ? 'Open' : 'Minimize';
  });

  document.querySelectorAll('.sidebar-nav a').forEach((link) => {
    link.addEventListener('click', () => {
      els.sidebar?.classList.remove('is-open');
      els.sidebarToggle?.setAttribute('aria-expanded', 'false');
    });
  });
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
    els.themeToggle.textContent = theme === 'dark' ? 'Light mode' : 'Dark mode';
    els.themeToggle.setAttribute('aria-label', `Switch to ${nextTheme} theme`);
  }
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch (error) {
    return;
  }
  const analysis = state().getAnalysis();
  if (analysis) {
    document.dispatchEvent(new CustomEvent('finsight:analysis-updated', { detail: { analysis } }));
  }
}
