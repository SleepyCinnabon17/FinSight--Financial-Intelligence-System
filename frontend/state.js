const state = {
  transactions: [],
  currentExtraction: null,
  novaHistory: [],
  analysis: null
};

let sortState = { key: 'date', direction: 'desc' };

export function getTransactions() {
  return state.transactions;
}

export function setTransactions(transactions) {
  state.transactions = Array.isArray(transactions) ? transactions : [];
}

export function getAnalysis() {
  return state.analysis;
}

export function setAnalysis(analysis) {
  state.analysis = analysis;
}

export function getCurrentExtraction() {
  return state.currentExtraction;
}

export function setCurrentExtraction(extraction) {
  state.currentExtraction = extraction;
}

export function getNovaHistory() {
  return state.novaHistory;
}

export function addNovaExchange(userMessage, novaMessage) {
  state.novaHistory.push({ role: 'user', content: userMessage }, { role: 'assistant', content: novaMessage });
}

export function getSortState() {
  return { ...sortState };
}

export function updateSortState(key) {
  sortState = {
    key,
    direction: sortState.key === key && sortState.direction === 'asc' ? 'desc' : 'asc'
  };
  return getSortState();
}

export function transactionStatus(transaction) {
  if (transaction.is_anomaly) return 'anomaly';
  if (transaction.is_duplicate) return 'duplicate';
  return 'normal';
}

export function sortedTransactions() {
  const rows = [...state.transactions];
  rows.sort((a, b) => {
    const key = sortState.key;
    const av = key === 'status' ? transactionStatus(a) : a[key];
    const bv = key === 'status' ? transactionStatus(b) : b[key];
    const result = key === 'total' ? Number(av || 0) - Number(bv || 0) : String(av || '').localeCompare(String(bv || ''));
    return sortState.direction === 'asc' ? result : -result;
  });
  return rows;
}

window.FinSightState = {
  getTransactions,
  setTransactions,
  getAnalysis,
  setAnalysis,
  getCurrentExtraction,
  setCurrentExtraction,
  getNovaHistory,
  addNovaExchange,
  getSortState,
  updateSortState,
  transactionStatus,
  sortedTransactions
};
