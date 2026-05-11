import { confirmDuplicate, dismissAnomaly, fetchAnalysis, fetchTransactions } from './api.js';
import { createTransactionDetailsRow, createTransactionRow } from './ui_components.js';

const els = {
  uploadStatus: document.getElementById('upload-status'),
  transactionBody: document.getElementById('transaction-body'),
  refreshData: document.getElementById('refresh-data')
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

loadDashboard().catch((error) => {
  els.uploadStatus.textContent = error.message;
});

window.FinSightMain = { loadDashboard, renderTransactions, setupTransactions };
