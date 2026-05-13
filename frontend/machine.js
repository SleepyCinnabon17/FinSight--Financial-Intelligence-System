const SYMBOLS = ['INR', 'DOC', 'OCR', 'DATA', 'BILL', 'GST', 'UPI', 'KIE', 'PDF', 'TAX', 'SAVE', 'LOSS', 'FLAG'];
const REVIEW_LABELS = ['MERCHANT', 'DATE', 'CATEGORY', 'AMOUNT', 'CONF'];
const STATUS_COLORS = {
  green: 'var(--led-green)',
  red: 'var(--led-red)',
  amber: 'var(--led-amber)',
  gold: 'var(--gold)'
};

const els = {
  cabinet: document.getElementById('cabinet'),
  payline: document.getElementById('payline'),
  tickerText: document.getElementById('ticker-text'),
  tickerPip: document.getElementById('ticker-pip'),
  machineLive: document.getElementById('machine-live'),
  dropZone: document.getElementById('drop-zone'),
  processButton: document.getElementById('process-btn'),
  reels: Array.from({ length: 5 }, (_, index) => document.getElementById(`reel-${index}`)).filter(Boolean)
};

const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
let lockTimers = [];

function buildReels() {
  els.reels.forEach((reel, index) => {
    reel.replaceChildren();
    const fragment = document.createDocumentFragment();
    for (let iteration = 0; iteration < 2; iteration += 1) {
      for (let item = 0; item < 12; item += 1) {
        fragment.appendChild(createAmbientCell(SYMBOLS[(item + index * 3) % SYMBOLS.length]));
      }
    }
    reel.appendChild(fragment);
    reel.classList.add('idle');
    reel.classList.remove('spinning', 'locked');
    reel.style.transform = '';
  });
}

function createAmbientCell(value) {
  const cell = document.createElement('div');
  cell.className = 'tape-cell';
  const symbol = document.createElement('span');
  symbol.className = 'cell-ambient';
  symbol.textContent = value;
  cell.appendChild(symbol);
  return cell;
}

function createDataCell(label, value) {
  const cell = document.createElement('div');
  cell.className = 'tape-cell';
  const wrap = document.createElement('div');
  wrap.className = 'cell-data';
  const labelElement = document.createElement('span');
  labelElement.className = 'data-label';
  labelElement.textContent = label;
  const valueElement = document.createElement('span');
  valueElement.className = 'data-value';
  valueElement.textContent = value || '--';
  wrap.append(labelElement, valueElement);
  cell.appendChild(wrap);
  return cell;
}

function setTicker(message, color = 'green') {
  if (els.tickerText) els.tickerText.textContent = message;
  if (els.machineLive) els.machineLive.textContent = message;
  if (els.tickerPip) els.tickerPip.style.background = STATUS_COLORS[color] || STATUS_COLORS.green;
}

function clearLockTimers() {
  lockTimers.forEach((timer) => window.clearTimeout(timer));
  lockTimers = [];
}

function setArmed(event) {
  const count = Number(event.detail?.fileCount || 0);
  els.dropZone?.classList.add('armed');
  els.processButton?.classList.add('ready');
  setTicker(count > 1 ? `${count} DOCUMENTS LOCKED - PRESS PROCESS` : 'DOCUMENT LOCKED - PRESS PROCESS', 'amber');
}

function setProcessing() {
  clearLockTimers();
  els.dropZone?.classList.remove('armed');
  els.dropZone?.classList.add('is-processing');
  els.processButton?.classList.remove('ready');
  setTicker('OCR EXTRACTION IN PROGRESS...', 'red');
  els.reels.forEach((reel) => {
    reel.classList.remove('idle', 'locked');
    reel.style.transform = '';
    reel.classList.add('spinning');
  });
}

function setReview(event) {
  const fields = extractionFields(event.detail?.extraction);
  if (reducedMotion.matches) {
    els.reels.forEach((_, index) => lockReel(index, fields[index]));
    completeReview();
    return;
  }

  els.reels.forEach((_, index) => {
    lockTimers.push(window.setTimeout(() => lockReel(index, fields[index]), 240 + index * 130));
  });
  lockTimers.push(window.setTimeout(completeReview, 1000));
}

function extractionFields(extraction = {}) {
  return REVIEW_LABELS.map((label) => {
    const key = label.toLowerCase() === 'amount' ? 'total' : label.toLowerCase();
    const info = extraction?.[key];
    const rawValue = info && typeof info === 'object' ? info.value : info;
    if (label === 'CONF') {
      const confidences = Object.values(extraction || {})
        .map((entry) => (entry && typeof entry === 'object' ? Number(entry.confidence) : NaN))
        .filter(Number.isFinite);
      const average = confidences.length
        ? confidences.reduce((sum, confidence) => sum + confidence, 0) / confidences.length
        : 0;
      return { label, value: `${Math.round(average * 100)}%` };
    }
    return { label, value: normalizeReelValue(rawValue) };
  });
}

function normalizeReelValue(value) {
  if (value === null || value === undefined || value === '') return '--';
  const text = String(value);
  return text.length > 16 ? `${text.slice(0, 15)}...` : text;
}

function lockReel(index, data) {
  const reel = els.reels[index];
  if (!reel || !data) return;
  reel.classList.remove('spinning', 'idle');
  reel.classList.add('locked');
  reel.replaceChildren(
    createAmbientCell(SYMBOLS[(index * 2) % SYMBOLS.length]),
    createDataCell(data.label, data.value),
    createAmbientCell(SYMBOLS[(index * 2 + 1) % SYMBOLS.length])
  );
  reel.style.transform = 'translateY(-33.333%)';
}

function completeReview() {
  els.dropZone?.classList.remove('is-processing');
  els.cabinet?.classList.add('win-flash');
  els.payline?.classList.add('surge');
  setTicker('EXTRACTION COMPLETE - REVIEW AND COMMIT', 'green');
  window.setTimeout(() => {
    els.cabinet?.classList.remove('win-flash');
    els.payline?.classList.remove('surge');
  }, reducedMotion.matches ? 10 : 700);
}

function resetMachine(message, color = 'green') {
  clearLockTimers();
  els.dropZone?.classList.remove('armed', 'is-processing', 'dragover');
  els.processButton?.classList.remove('ready');
  buildReels();
  setTicker(message, color);
}

function setError(event) {
  els.dropZone?.classList.remove('armed', 'is-processing');
  els.processButton?.classList.remove('ready');
  setTicker(event.detail?.message || 'MACHINE ERROR - CHECK UPLOAD', 'red');
}

buildReels();
setTicker('SYSTEM READY - AWAITING DOCUMENT', 'green');

document.addEventListener('finsight:machine-armed', setArmed);
document.addEventListener('finsight:machine-processing', setProcessing);
document.addEventListener('finsight:machine-review', setReview);
document.addEventListener('finsight:machine-confirmed', () => resetMachine('TRANSACTION COMMITTED - LEDGER UPDATED', 'green'));
document.addEventListener('finsight:machine-discarded', () => resetMachine('EXTRACTION DISCARDED - AWAITING DOCUMENT', 'amber'));
document.addEventListener('finsight:machine-error', setError);

window.FinSightMachine = { buildReels, setTicker, resetMachine };
