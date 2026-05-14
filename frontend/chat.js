import { openNovaConnection } from './api.js';
import { appendBubble, setBubbleText } from './ui_components.js';

const els = {
  chatForm: document.getElementById('chat-form'),
  chatInput: document.getElementById('chat-input'),
  chatBubbles: document.getElementById('chat-bubbles'),
  typingIndicator: document.getElementById('chat-typing'),
  stopButton: document.getElementById('chat-stop-button'),
  retryButton: document.getElementById('chat-retry-button'),
  statusDot: document.getElementById('chat-status-dot'),
  statusText: document.getElementById('chat-status-text')
};

const terminalEl = document.querySelector('.hero-terminal');

const STATUS_CLASSES = ['idle', 'connected', 'error'];
let activeStream = null;
let lastMessage = '';

// Prompt overlay elements (created once)
let promptOverlay = null;
let promptMirror = null;
let promptPlaceholder = null;
let promptCursor = null;

function state() {
  return window.FinSightState;
}

export async function sendNovaMessage(message) {
  if (activeStream) stopActiveConnection();
  lastMessage = message;
  els.retryButton.hidden = true;
  appendBubble(els.chatBubbles, 'user', message);
  const novaBubble = appendBubble(els.chatBubbles, 'nova', '');
  novaBubble.classList.add('is-streaming');
  const stream = { connection: null, bubble: novaBubble, stopped: false };
  activeStream = stream;
  setConnectionStatus('connected');
  setTyping(true);
  els.stopButton.hidden = false;
  try {
    stream.connection = openNovaConnection(message, state().getNovaHistory(), {
      onToken: (text) => {
        const follow = shouldFollowStream();
        setBubbleText(novaBubble, text);
        if (follow) scrollToLatest();
      }
    });
    const novaText = await stream.connection.done;
    setBubbleText(novaBubble, novaText);
    state().addNovaExchange(message, novaText);
    setConnectionStatus('idle');
  } catch (error) {
    if (stream.stopped || error.name === 'AbortError') {
      const existingText = currentBubbleText(novaBubble);
      setBubbleText(novaBubble, existingText || 'Response stopped.');
      setConnectionStatus('idle');
    } else {
      setBubbleText(novaBubble, error.message || 'Nova is temporarily unavailable. Please try again.');
      setConnectionStatus('error');
      els.retryButton.hidden = false;
    }
  } finally {
    novaBubble.classList.remove('is-streaming');
    setTyping(false);
    if (activeStream === stream) activeStream = null;
    els.stopButton.hidden = true;
    scrollToLatest();
  }
}

export function stopActiveConnection() {
  if (!activeStream?.connection) return;
  activeStream.stopped = true;
  activeStream.connection.close();
  setTyping(false);
  setConnectionStatus('idle');
  els.stopButton.hidden = true;
}

export function setupChat() {
  // Move the static terminal intro lines into the chat output so the terminal
  // itself becomes the unified chat surface (preserves IDs and accessibility).
  try {
    const intro = document.querySelector('.terminal-body.terminal-intro');
    if (intro && els.chatBubbles && !els.chatBubbles.dataset.introInited) {
      const paragraphs = Array.from(intro.querySelectorAll('p'));
      for (const p of paragraphs) {
        const text = p.textContent.trim();
        if (text) {
          // use 'nova' role so messages appear as terminal lines; tests look for text, not role
          appendBubble(els.chatBubbles, 'nova', text);
        }
      }
      // mark and hide original intro to avoid duplication
      els.chatBubbles.dataset.introInited = '1';
      intro.style.display = 'none';
    }
  } catch (err) {
    // non-fatal; preserve normal chat behavior
    console.error(err);
  }

  // Create a visible prompt overlay that mirrors the invisible input's value
  // and shows a block cursor. This keeps the native input (for form
  // submissions and tests) but replaces the visual caret with a terminal
  // style cursor and inline prompt text.
  function ensurePromptOverlay() {
    if (promptOverlay || !els.chatForm || !els.chatInput) return;
    promptOverlay = document.createElement('div');
    promptOverlay.className = 'prompt-overlay';

    const symbol = document.createElement('span');
    symbol.className = 'prompt-symbol';
    symbol.textContent = '$';

    const display = document.createElement('span');
    display.className = 'prompt-display';

    promptMirror = document.createElement('span');
    promptMirror.className = 'prompt-mirror';

    promptPlaceholder = document.createElement('span');
    promptPlaceholder.className = 'prompt-placeholder';
    promptPlaceholder.textContent = els.chatInput.placeholder || '';

    promptCursor = document.createElement('span');
    promptCursor.className = 'prompt-cursor';
    // use a non-breaking space so block has width even on empty lines
    promptCursor.textContent = '\u00A0';

    display.appendChild(promptMirror);
    display.appendChild(promptPlaceholder);
    display.appendChild(promptCursor);

    promptOverlay.appendChild(symbol);
    promptOverlay.appendChild(display);

    // Place overlay into the form (after input so it renders above)
    els.chatForm.appendChild(promptOverlay);

    // Keep the overlay interactive so clicks focus the real input
    promptOverlay.addEventListener('click', (e) => {
      e.stopPropagation();
      els.chatInput.focus();
    });

    // Mirror input changes into the overlay
    const updateMirror = () => {
      const v = els.chatInput.value || '';
      if (v.length === 0) {
        promptMirror.textContent = '';
        promptPlaceholder.style.display = '';
      } else {
        promptMirror.textContent = v;
        promptPlaceholder.style.display = 'none';
      }
      // keep terminal scrolled to bottom when typing
      try { scrollToLatest(); } catch (e) {}
    };

    // Update on input and on programmatic value changes
    els.chatInput.addEventListener('input', updateMirror);
    // initialize
    updateMirror();
  }

  ensurePromptOverlay();

  els.chatForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const message = els.chatInput.value.trim();
    if (!message) return;
    els.chatInput.value = '';
    try {
      await sendNovaMessage(message);
    } catch (error) {
      appendBubble(els.chatBubbles, 'nova', error.message || 'Nova is temporarily unavailable. Please try again.');
    }
  });
  els.stopButton.addEventListener('click', stopActiveConnection);
  els.retryButton.addEventListener('click', () => {
    if (lastMessage) sendNovaMessage(lastMessage);
  });
  // Make the terminal container act like a CLI: clicking anywhere focuses the input prompt.
  if (terminalEl) {
    terminalEl.addEventListener('click', (event) => {
      // Avoid stealing focus when interacting with copy buttons or other
      // actionable buttons, but allow clicks anywhere else (including the
      // prompt area) to focus the invisible input.
      if (event.target.closest('.bubble-copy') || event.target.closest('button')) return;
      els.chatInput.focus();
    });
  }
}

setupChat();

window.FinSightChat = { sendNovaMessage, setupChat, stopActiveConnection };

function setTyping(isTyping) {
  els.typingIndicator.hidden = !isTyping;
}

function setConnectionStatus(status) {
  els.statusDot.classList.remove(...STATUS_CLASSES);
  els.statusDot.classList.add(status);
  els.statusText.textContent = status === 'connected' ? 'Connected' : status === 'error' ? 'Error' : 'Idle';
}

function shouldFollowStream() {
  const distanceFromBottom = els.chatBubbles.scrollHeight - els.chatBubbles.scrollTop - els.chatBubbles.clientHeight;
  return distanceFromBottom < 48;
}

function scrollToLatest() {
  els.chatBubbles.scrollTop = els.chatBubbles.scrollHeight;
}

function currentBubbleText(bubble) {
  return bubble.querySelector('.bubble-text')?.textContent || '';
}
