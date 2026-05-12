import { confirmDuplicate, deleteTransaction, dismissAnomaly, fetchAnalysis, fetchTransactions } from './api.js';
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
  kpiValues: document.querySelectorAll('.kpi-card strong')
};

const THEME_STORAGE_KEY = 'finsight-theme';
const RESET_LABEL = 'Reset demo';
const RESET_ARMED_LABEL = 'Click again to reset';
const RESET_DISARM_MS = 4500;
let resetArmed = false;
let resetTimer = null;

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

loadDashboard().catch((error) => {
  els.uploadStatus.textContent = error.message;
});

window.FinSightMain = { loadDashboard, renderTransactions, renderKpis, setupTransactions };

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
