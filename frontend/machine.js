const STATUS_COLORS = {
  green: 'var(--success)',
  red: 'var(--error)',
  amber: 'var(--warning)',
  gold: 'var(--accent)'
};

const els = {
  machineLive: document.getElementById('machine-live'),
  dropZone: document.getElementById('drop-zone'),
  processButton: document.getElementById('process-btn')
};

function announce(message) {
  if (els.machineLive) els.machineLive.textContent = message;
}

function setVisualState(stateName) {
  els.dropZone?.classList.toggle('armed', stateName === 'armed');
  els.dropZone?.classList.toggle('is-processing', stateName === 'processing');
  els.dropZone?.classList.toggle('is-reviewing', stateName === 'review');
  els.processButton?.classList.toggle('ready', stateName === 'armed');
}

function setArmed(event) {
  const count = Number(event.detail?.fileCount || 0);
  setVisualState('armed');
  announce(count > 1 ? `${count} documents selected. Press Process to extract.` : 'Document selected. Press Process to extract.');
}

function setProcessing() {
  setVisualState('processing');
  announce('OCR extraction in progress.');
}

function setReview() {
  setVisualState('review');
  announce('Extraction complete. Review and confirm or discard.');
}

function resetMachine(message = 'System ready. Awaiting document.') {
  setVisualState('idle');
  els.dropZone?.classList.remove('dragover');
  announce(message);
}

function setError(event) {
  setVisualState('idle');
  announce(event.detail?.message || 'Upload error. Check the selected file.');
}

resetMachine();

document.addEventListener('finsight:machine-armed', setArmed);
document.addEventListener('finsight:machine-processing', setProcessing);
document.addEventListener('finsight:machine-review', setReview);
document.addEventListener('finsight:machine-confirmed', () => resetMachine('Transaction saved. Dashboard updated.'));
document.addEventListener('finsight:machine-discarded', () => resetMachine('Extraction discarded. Awaiting document.'));
document.addEventListener('finsight:machine-error', setError);

window.FinSightMachine = { announce, resetMachine, statusColors: STATUS_COLORS };
