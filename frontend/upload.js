import { confirmTransaction, discardTransaction, uploadBills } from './api.js';
import { clearExtractionPreview, renderExtractionPreview, renderPreviews } from './ui_components.js';

const els = {
  fileInput: document.getElementById('file-input'),
  fileButton: document.getElementById('file-picker-button'),
  dropZone: document.getElementById('drop-zone'),
  previewStrip: document.getElementById('preview-strip'),
  uploadStatus: document.getElementById('upload-status'),
  extractionPreview: document.getElementById('extraction-preview')
};

function state() {
  return window.FinSightState;
}

function requestDashboardRefresh() {
  document.dispatchEvent(new CustomEvent('finsight:refresh-dashboard'));
}

export async function uploadFiles(files) {
  if (!files.length) return;
  try {
    renderPreviews(els.previewStrip, files);
    els.uploadStatus.textContent = 'Uploading...';
    const formData = new FormData();
    for (const file of files) formData.append('files', file);
    const results = await uploadBills(formData);
    state().setCurrentExtraction(results[0]);
    renderExtractionPreview(els.extractionPreview, results[0], {
      onConfirm: confirmCurrentExtraction,
      onDiscard: discardCurrentExtraction
    });
    els.uploadStatus.textContent = 'Extraction ready.';
  } catch (error) {
    els.uploadStatus.textContent = error.message;
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
      els.uploadStatus.textContent = 'Fix highlighted fields before confirming.';
      return;
    }
    await confirmTransaction(currentExtraction.upload_id, currentExtraction.extraction, edits);
    state().setCurrentExtraction(null);
    clearExtractionPreview(els.extractionPreview);
    requestDashboardRefresh();
  } catch (error) {
    els.uploadStatus.textContent = error.message || 'Could not confirm this extraction.';
  }
}

export async function discardCurrentExtraction() {
  try {
    await discardTransaction(state().getCurrentExtraction()?.upload_id || null);
    state().setCurrentExtraction(null);
    clearExtractionPreview(els.extractionPreview);
  } catch (error) {
    els.uploadStatus.textContent = error.message || 'Could not discard this extraction.';
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
