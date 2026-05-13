import { confirmTransaction, discardTransaction, uploadBills } from './api.js';
import { clearExtractionPreview, renderExtractionPreview, renderPreviews } from './ui_components.js';

const els = {
  fileInput: document.getElementById('file-input'),
  fileButton: document.getElementById('file-picker-button'),
  dropZone: document.getElementById('drop-zone'),
  previewStrip: document.getElementById('preview-strip'),
  uploadStatus: document.getElementById('upload-status'),
  extractionPreview: document.getElementById('extraction-preview'),
  processButton: document.getElementById('process-btn'),
  toastContainer: document.getElementById('toast-container')
};

const UPLOAD_STATUS_CLASSES = [
  'upload-state-uploading',
  'upload-state-processing',
  'upload-state-review',
  'upload-state-confirmed',
  'upload-state-discarded',
  'upload-state-error'
];

let stagedFiles = [];

function state() {
  return window.FinSightState;
}

function requestDashboardRefresh() {
  document.dispatchEvent(new CustomEvent('finsight:refresh-dashboard'));
}

function machineEvent(name, detail = {}) {
  document.dispatchEvent(new CustomEvent(`finsight:machine-${name}`, { detail }));
}

function setProcessReady(isReady) {
  if (!els.processButton) return;
  els.processButton.disabled = !isReady;
  els.processButton.setAttribute('aria-disabled', String(!isReady));
  els.processButton.classList.toggle('ready', isReady);
}

function setUploadState(status, message) {
  els.uploadStatus.classList.remove(...UPLOAD_STATUS_CLASSES);
  els.dropZone.classList.remove('is-processing');
  if (status) {
    els.uploadStatus.classList.add(`upload-state-${status}`);
  }
  if (status === 'processing') {
    els.dropZone.classList.add('is-processing');
  }
  els.uploadStatus.textContent = message;
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

export async function uploadFiles(files) {
  const selectedFiles = [...files];
  if (!selectedFiles.length) return;
  let processingTimer = null;
  try {
    renderPreviews(els.previewStrip, selectedFiles);
    machineEvent('processing', { fileCount: selectedFiles.length });
    setProcessReady(false);
    setUploadState('uploading', 'Uploading bills...');
    const formData = new FormData();
    for (const file of selectedFiles) formData.append('files', file);
    processingTimer = window.setTimeout(() => {
      setUploadState('processing', 'Processing OCR...');
    }, 120);
    const results = await uploadBills(formData);
    if (processingTimer) window.clearTimeout(processingTimer);
    setUploadState('processing', 'Processing OCR...');
    if (!results[0]) {
      throw new Error('No extraction result was returned.');
    }
    state().setCurrentExtraction(results[0]);
    renderExtractionPreview(els.extractionPreview, results[0], {
      onConfirm: confirmCurrentExtraction,
      onDiscard: discardCurrentExtraction
    });
    setUploadState('review', 'Extraction ready for review.');
    machineEvent('review', { extraction: results[0].extraction });
  } catch (error) {
    if (processingTimer) window.clearTimeout(processingTimer);
    const message = error.message || 'Upload failed.';
    setUploadState('error', message);
    if (stagedFiles.length) setProcessReady(true);
    machineEvent('error', { message });
    showToast(message, 'error');
  }
}

export async function confirmCurrentExtraction() {
  try {
    const currentExtraction = state().getCurrentExtraction();
    if (!currentExtraction) return;
    const edits = collectEdits();
    const errors = validateEdits(edits);
    showFieldErrors(errors);
    if (Object.keys(errors).length) {
      setUploadState('review', 'Fix highlighted fields before confirming.');
      return;
    }
    await confirmTransaction(currentExtraction.upload_id, currentExtraction.extraction, edits);
    state().setCurrentExtraction(null);
    clearExtractionPreview(els.extractionPreview);
    clearStagedFiles();
    setUploadState('confirmed', 'Transaction confirmed.');
    machineEvent('confirmed');
    showToast('Transaction confirmed.', 'success');
    requestDashboardRefresh();
  } catch (error) {
    const message = error.message || 'Could not confirm this extraction.';
    setUploadState('error', message);
    machineEvent('error', { message });
    showToast(message, 'error');
  }
}

export async function discardCurrentExtraction() {
  try {
    await discardTransaction(state().getCurrentExtraction()?.upload_id || null);
    state().setCurrentExtraction(null);
    clearExtractionPreview(els.extractionPreview);
    clearStagedFiles();
    setUploadState('discarded', 'Upload discarded.');
    machineEvent('discarded');
    showToast('Upload discarded.', 'warning');
  } catch (error) {
    const message = error.message || 'Could not discard this extraction.';
    setUploadState('error', message);
    machineEvent('error', { message });
    showToast(message, 'error');
  }
}

export function collectEdits() {
  const edits = {};
  els.extractionPreview.querySelectorAll('input').forEach((input) => {
    edits[input.name] = input.value;
  });
  return edits;
}

export function validateEdits(edits) {
  const errors = {};
  const merchant = String(edits.merchant || '').trim();
  if (!merchant) errors.merchant = 'Merchant is required.';

  for (const field of ['subtotal', 'tax', 'total']) {
    const value = String(edits[field] ?? '').trim();
    if (field === 'total' && !value) {
      errors[field] = 'Amount must be a valid number.';
      continue;
    }
    if (value && !Number.isFinite(Number(value))) {
      errors[field] = 'Amount must be a valid number.';
    }
  }

  const date = String(edits.date || '').trim();
  if (date && !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    errors.date = 'Date must use YYYY-MM-DD.';
  }

  if ('category' in edits && !String(edits.category || '').trim()) {
    errors.category = 'Category is required.';
  }

  return errors;
}

function showFieldErrors(errors) {
  els.extractionPreview.querySelectorAll('[data-field-error]').forEach((errorElement) => {
    const field = errorElement.dataset.fieldError;
    const input = els.extractionPreview.querySelector(`input[name="${field}"]`);
    const message = errors[field] || '';
    errorElement.textContent = message;
    errorElement.hidden = !message;
    if (input) input.setAttribute('aria-invalid', message ? 'true' : 'false');
  });
}

export function stageFiles(files) {
  stagedFiles = [...files].filter(Boolean);
  if (!stagedFiles.length) return;
  renderPreviews(els.previewStrip, stagedFiles);
  clearExtractionPreview(els.extractionPreview);
  state().setCurrentExtraction(null);
  els.dropZone.classList.add('armed');
  setProcessReady(true);
  setUploadState('uploading', stagedFiles.length > 1 ? `${stagedFiles.length} files staged. Press Process to extract.` : 'File staged. Press Process to extract.');
  machineEvent('armed', { fileCount: stagedFiles.length, fileNames: stagedFiles.map((file) => file.name) });
}

function clearStagedFiles() {
  stagedFiles = [];
  setProcessReady(false);
  els.dropZone.classList.remove('armed', 'is-processing');
  els.fileInput.value = '';
}

async function processStagedFiles() {
  if (!stagedFiles.length) {
    showToast('Choose a file before processing.', 'warning');
    return;
  }
  await uploadFiles(stagedFiles);
}

export function setupUpload() {
  els.fileButton.addEventListener('click', () => els.fileInput.click());
  els.processButton?.addEventListener('click', processStagedFiles);
  els.fileInput.addEventListener('change', () => stageFiles([...els.fileInput.files]));
  els.dropZone.addEventListener('click', () => {
    if (!els.processButton?.classList.contains('ready')) els.fileInput.click();
  });
  els.dropZone.addEventListener('dragover', (event) => {
    event.preventDefault();
    els.dropZone.classList.add('dragover');
  });
  els.dropZone.addEventListener('dragleave', () => els.dropZone.classList.remove('dragover'));
  els.dropZone.addEventListener('drop', (event) => {
    event.preventDefault();
    els.dropZone.classList.remove('dragover');
    stageFiles([...event.dataTransfer.files]);
  });
  els.dropZone.addEventListener('keydown', (event) => {
    if (event.target !== els.dropZone) return;
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    els.fileInput.click();
  });
}

setupUpload();

window.FinSightUpload = { uploadFiles, stageFiles, confirmCurrentExtraction, discardCurrentExtraction, setupUpload };
