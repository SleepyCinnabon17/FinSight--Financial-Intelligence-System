import { confirmTransaction, discardTransaction, uploadBills } from './api.js';
import { clearExtractionPreview, renderExtractionPreview, renderPreviews } from './ui_components.js';

const els = {
  fileInput: document.getElementById('file-input'),
  fileButton: document.getElementById('file-picker-button'),
  dropZone: document.getElementById('drop-zone'),
  previewStrip: document.getElementById('preview-strip'),
  uploadStatus: document.getElementById('upload-status'),
  extractionPreview: document.getElementById('extraction-preview'),
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

function state() {
  return window.FinSightState;
}

function requestDashboardRefresh() {
  document.dispatchEvent(new CustomEvent('finsight:refresh-dashboard'));
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
  if (!files.length) return;
  let processingTimer = null;
  try {
    renderPreviews(els.previewStrip, files);
    setUploadState('uploading', 'Uploading bills...');
    const formData = new FormData();
    for (const file of files) formData.append('files', file);
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
  } catch (error) {
    if (processingTimer) window.clearTimeout(processingTimer);
    const message = error.message || 'Upload failed.';
    setUploadState('error', message);
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
    setUploadState('confirmed', 'Transaction confirmed.');
    showToast('Transaction confirmed.', 'success');
    requestDashboardRefresh();
  } catch (error) {
    const message = error.message || 'Could not confirm this extraction.';
    setUploadState('error', message);
    showToast(message, 'error');
  }
}

export async function discardCurrentExtraction() {
  try {
    await discardTransaction(state().getCurrentExtraction()?.upload_id || null);
    state().setCurrentExtraction(null);
    clearExtractionPreview(els.extractionPreview);
    setUploadState('discarded', 'Upload discarded.');
    showToast('Upload discarded.', 'warning');
  } catch (error) {
    const message = error.message || 'Could not discard this extraction.';
    setUploadState('error', message);
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

export function setupUpload() {
  els.fileButton.addEventListener('click', () => els.fileInput.click());
  els.fileInput.addEventListener('change', () => uploadFiles([...els.fileInput.files]));
  els.dropZone.addEventListener('dragover', (event) => {
    event.preventDefault();
    els.dropZone.classList.add('dragover');
  });
  els.dropZone.addEventListener('dragleave', () => els.dropZone.classList.remove('dragover'));
  els.dropZone.addEventListener('drop', (event) => {
    event.preventDefault();
    els.dropZone.classList.remove('dragover');
    uploadFiles([...event.dataTransfer.files]);
  });
}

setupUpload();

window.FinSightUpload = { uploadFiles, confirmCurrentExtraction, discardCurrentExtraction, setupUpload };
