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
      // Avoid stealing focus when interacting with form controls or copy buttons
      if (event.target.closest('#chat-form') || event.target.closest('.bubble-copy') || event.target.closest('button')) return;
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
