export async function api(path, options = {}) {
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({ success: false, error: { message: 'Invalid server response' } }));
  if (!response.ok || payload.success === false) {
    const message = payload.error?.message || `Request failed with ${response.status}`;
    throw new Error(message);
  }
  return payload.data;
}

export function fetchTransactions() {
  return api('/api/v1/transactions');
}

export function fetchAnalysis() {
  return api('/api/v1/analysis');
}

export function confirmDuplicate(transactionId, confirmed) {
  return api('/api/v1/duplicate/confirm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ transaction_id: transactionId, confirmed })
  });
}

export function dismissAnomaly(transactionId) {
  return api(`/api/v1/transactions/${transactionId}/dismiss-anomaly`, { method: 'POST' });
}

export function uploadBills(formData) {
  return api('/api/v1/upload', { method: 'POST', body: formData });
}

export function confirmTransaction(uploadId, extractionResult, userEdits) {
  return api('/api/v1/transactions/confirm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      upload_id: uploadId,
      extraction_result: extractionResult,
      user_edits: userEdits
    })
  });
}

export function discardTransaction(uploadId) {
  return api('/api/v1/transactions/discard', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ upload_id: uploadId || null })
  });
}

export async function streamNovaMessage(message, conversationHistory, onToken) {
  const connection = openNovaConnection(message, conversationHistory, { onToken });
  return connection.done;
}

export function openNovaConnection(message, conversationHistory, callbacks = {}) {
  const controller = new AbortController();
  const done = readNovaStream(message, conversationHistory, callbacks.onToken || (() => {}), controller.signal);
  return {
    done,
    close() {
      controller.abort();
    }
  };
}

async function readNovaStream(message, conversationHistory, onToken, signal) {
  const response = await fetch('/api/v1/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, conversation_history: conversationHistory }),
    signal
  });
  if (!response.ok || !response.body) {
    throw new Error('Nova is temporarily unavailable. Please try again.');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let novaText = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split('\n\n');
    buffer = events.pop() || '';
    for (const event of events) {
      const line = event.split('\n').find((entry) => entry.startsWith('data:'));
      if (!line) continue;
      novaText += line.slice(5).trimStart();
      onToken(novaText);
    }
  }
  return novaText;
}

window.FinSightApi = {
  api,
  fetchTransactions,
  fetchAnalysis,
  confirmDuplicate,
  dismissAnomaly,
  uploadBills,
  confirmTransaction,
  discardTransaction,
  streamNovaMessage,
  openNovaConnection
};
