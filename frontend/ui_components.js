export function formatCurrency(value) {
  const amount = Number(value || 0);
  return amount.toLocaleString('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 });
}

export function formatFileSize(bytes) {
  const size = Number(bytes || 0);
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function confidenceClass(confidence) {
  if (confidence >= 0.8) return 'confidence-high';
  if (confidence >= 0.4) return 'confidence-mid';
  return 'confidence-low';
}

export function actionButton(label, handler) {
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = label;
  button.addEventListener('click', (event) => {
    event.stopPropagation();
    handler();
  });
  return button;
}

export function appendBubble(container, role, text = '') {
  const bubble = document.createElement('article');
  bubble.className = `bubble ${role}`;
  const meta = document.createElement('div');
  meta.className = 'bubble-meta';
  const roleLabel = document.createElement('span');
  roleLabel.className = 'bubble-role';
  roleLabel.textContent = role === 'user' ? 'You' : 'Nova';
  const timestamp = document.createElement('time');
  const now = new Date();
  timestamp.dateTime = now.toISOString();
  timestamp.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const copyButton = document.createElement('button');
  copyButton.type = 'button';
  copyButton.className = 'bubble-copy';
  copyButton.textContent = 'Copy';
  copyButton.setAttribute('aria-label', `Copy ${roleLabel.textContent} message`);
  const content = document.createElement('p');
  content.className = 'bubble-text';
  meta.append(roleLabel, timestamp, copyButton);
  bubble.append(meta, content);
  setBubbleText(bubble, text);
  copyButton.addEventListener('click', async () => {
    const message = content.textContent || '';
    try {
      await navigator.clipboard?.writeText(message);
      copyButton.textContent = 'Copied';
      window.setTimeout(() => {
        copyButton.textContent = 'Copy';
      }, 1200);
    } catch (error) {
      copyButton.textContent = 'Copy';
    }
  });
  container.appendChild(bubble);
  container.scrollTop = container.scrollHeight;
  return bubble;
}

export function setBubbleText(bubble, text) {
  const content = bubble.querySelector('.bubble-text');
  if (content) {
    content.textContent = text;
  } else {
    bubble.textContent = text;
  }
}

export function renderPreviews(container, files) {
  container.replaceChildren();
  for (const file of files) {
    if (file.type.startsWith('image/')) {
      const img = document.createElement('img');
      img.alt = file.name;
      img.src = URL.createObjectURL(file);
      img.onload = () => URL.revokeObjectURL(img.src);
      container.appendChild(img);
      continue;
    }

    const chip = document.createElement('div');
    chip.className = 'file-chip';
    const name = document.createElement('span');
    name.className = 'file-chip-name';
    name.textContent = file.name;
    const meta = document.createElement('small');
    meta.className = 'file-chip-meta';
    meta.textContent = `${file.type === 'application/pdf' ? 'PDF' : 'File'} - ${formatFileSize(file.size)}`;
    chip.append(name, meta);
    container.appendChild(chip);
  }
}

export function createTransactionRow(transaction, status, onSelect) {
  const row = document.createElement('tr');
  row.className = [
    'transaction-row',
    status === 'anomaly' ? 'anomaly-row' : '',
    status === 'duplicate' ? 'duplicate-row' : ''
  ]
    .filter(Boolean)
    .join(' ');
  row.tabIndex = 0;
  row.setAttribute('aria-expanded', 'false');
  row.setAttribute('aria-label', `View details for ${transaction.merchant || 'Unknown'} transaction`);
  appendCell(row, transaction.date || '', 'date-cell');
  appendCell(row, transaction.merchant || 'Unknown', 'merchant-cell');
  appendCell(row, transaction.category || 'Uncategorized', 'category-cell');
  appendCell(row, formatCurrency(transaction.total), 'amount-cell');
  const statusCell = document.createElement('td');
  statusCell.className = 'status-cell';
  const badge = document.createElement('span');
  badge.className = `status-badge ${status}`;
  badge.setAttribute('aria-label', `Transaction status ${status}`);
  const icon = document.createElement('span');
  icon.className = 'status-icon';
  icon.setAttribute('aria-hidden', 'true');
  const label = document.createElement('span');
  label.className = 'status-label';
  label.textContent = status;
  badge.append(icon, label);
  statusCell.appendChild(badge);
  row.appendChild(statusCell);
  row.addEventListener('click', () => onSelect(transaction, row));
  row.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    onSelect(transaction, row);
  });
  return row;
}

export function createTransactionDetailsRow(transaction, handlers) {
  const details = document.createElement('tr');
  details.className = 'details-row';
  const cell = document.createElement('td');
  cell.colSpan = 5;
  const panel = document.createElement('div');
  panel.className = 'details-panel';
  const meta = document.createElement('div');
  meta.className = 'details-meta';
  const billLine = document.createElement('article');
  billLine.className = 'detail-block';
  appendStrongText(billLine, 'Bill');
  billLine.appendChild(document.createTextNode(transaction.bill_number || 'N/A'));
  const paymentLine = document.createElement('article');
  paymentLine.className = 'detail-block';
  appendStrongText(paymentLine, 'Payment');
  paymentLine.appendChild(document.createTextNode(transaction.payment_method || 'N/A'));
  meta.append(billLine, paymentLine);
  const itemsBlock = document.createElement('article');
  itemsBlock.className = 'detail-block detail-block-wide';
  appendStrongText(itemsBlock, 'Items');
  const itemsList = document.createElement('ul');
  itemsList.className = 'details-items';
  const items = transaction.items || [];
  if (items.length) {
    for (const item of items) {
      const listItem = document.createElement('li');
      listItem.textContent = `${item.name}: ${formatCurrency(item.total_price)}`;
      itemsList.appendChild(listItem);
    }
  } else {
    const listItem = document.createElement('li');
    listItem.textContent = 'No line items';
    itemsList.appendChild(listItem);
  }
  itemsBlock.appendChild(itemsList);
  const actions = document.createElement('div');
  actions.className = 'row-actions inline-actions';
  panel.append(meta, itemsBlock, actions);
  cell.appendChild(panel);
  details.appendChild(cell);
  if (transaction.is_duplicate) {
    actions.appendChild(actionButton('Confirm duplicate', () => handlers.onConfirmDuplicate(transaction.id, false)));
    actions.appendChild(actionButton('Keep both', () => handlers.onConfirmDuplicate(transaction.id, true)));
  }
  if (transaction.is_anomaly) {
    actions.appendChild(actionButton('Dismiss', () => handlers.onDismissAnomaly(transaction.id)));
  }
  return details;
}

export function renderExtractionPreview(container, result, handlers) {
  const extraction = result.extraction;
  const fields = ['merchant', 'date', 'subtotal', 'tax', 'total', 'payment_method', 'bill_number'];
  container.hidden = false;
  container.replaceChildren();
  const heading = document.createElement('h3');
  heading.textContent = 'Extraction Preview';
  container.appendChild(heading);
  for (const field of fields) {
    const info = extraction[field] || { value: '', confidence: 0 };
    const row = document.createElement('label');
    row.className = 'field-row';
    const label = document.createElement('span');
    label.textContent = field.replace('_', ' ');
    const input = document.createElement('input');
    const inputId = `extraction-${field}`;
    input.id = inputId;
    input.name = field;
    input.value = info.value ?? '';
    const confidence = document.createElement('span');
    confidence.className = confidenceClass(info.confidence || 0);
    confidence.textContent = `${Math.round((info.confidence || 0) * 100)}%`;
    const error = document.createElement('small');
    error.className = 'field-error';
    error.dataset.fieldError = field;
    error.id = `${inputId}-error`;
    error.hidden = true;
    input.setAttribute('aria-describedby', error.id);
    input.setAttribute('aria-invalid', 'false');
    row.append(label, input, confidence, error);
    container.appendChild(row);
  }
  const actions = document.createElement('div');
  actions.className = 'row-actions';
  actions.appendChild(actionButton('Confirm', handlers.onConfirm));
  actions.appendChild(actionButton('Discard', handlers.onDiscard));
  container.appendChild(actions);
}

export function clearExtractionPreview(container) {
  container.hidden = true;
  container.replaceChildren();
}

function appendCell(row, value, className = '') {
  const cell = document.createElement('td');
  if (className) cell.className = className;
  cell.textContent = value;
  row.appendChild(cell);
}

function appendStrongText(container, value) {
  const strong = document.createElement('strong');
  strong.textContent = value;
  container.appendChild(strong);
  container.appendChild(document.createTextNode(' '));
}

window.FinSightUI = {
  formatCurrency,
  formatFileSize,
  confidenceClass,
  actionButton,
  appendBubble,
  setBubbleText,
  renderPreviews,
  createTransactionRow,
  createTransactionDetailsRow,
  renderExtractionPreview,
  clearExtractionPreview
};
