import { confirmDuplicate, dismissAnomaly, fetchAnalysis, fetchTransactions } from './api.js';
import { createTransactionDetailsRow, createTransactionRow } from './ui_components.js';

const els = {
  uploadStatus: document.getElementById('upload-status'),
  transactionBody: document.getElementById('transaction-body'),
  refreshData: document.getElementById('refresh-data'),
  sidebar: document.querySelector('.sidebar'),
  sidebarToggle: document.getElementById('sidebar-toggle'),
  novaPanel: document.getElementById('nova'),
  novaToggle: document.querySelector('.nova-toggle')
};

function state() {
  return window.FinSightState;
}

export async function loadDashboard() {
  const [transactions, analysis] = await Promise.all([fetchTransactions(), fetchAnalysis()]);
  state().setTransactions(transactions);
  state().setAnalysis(analysis);
  renderTransactions();
  document.dispatchEvent(new CustomEvent('finsight:analysis-updated', { detail: { analysis } }));
}

export function renderTransactions() {
  els.transactionBody.replaceChildren();
  for (const transaction of state().sortedTransactions()) {
    const status = state().transactionStatus(transaction);
    els.transactionBody.appendChild(createTransactionRow(transaction, status, toggleDetails));
  }
}

export function toggleDetails(transaction, row) {
  const next = row.nextElementSibling;
  if (next?.classList.contains('details-row')) {
    next.remove();
    return;
  }
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
  document.querySelectorAll('#transaction-table th').forEach((th) => {
    th.addEventListener('click', () => {
      state().updateSortState(th.dataset.sort);
      renderTransactions();
    });
  });
  document.addEventListener('finsight:refresh-dashboard', loadDashboard);
}

setupTransactions();
setupLayoutShell();

loadDashboard().catch((error) => {
  els.uploadStatus.textContent = error.message;
});

window.FinSightMain = { loadDashboard, renderTransactions, setupTransactions };

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
