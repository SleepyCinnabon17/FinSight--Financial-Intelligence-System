import { streamNovaMessage } from './api.js';
import { appendBubble } from './ui_components.js';

const els = {
  chatForm: document.getElementById('chat-form'),
  chatInput: document.getElementById('chat-input'),
  chatBubbles: document.getElementById('chat-bubbles')
};

function state() {
  return window.FinSightState;
}

export async function sendNovaMessage(message) {
  appendBubble(els.chatBubbles, 'user', message);
  const novaBubble = appendBubble(els.chatBubbles, 'nova', '');
  try {
    const novaText = await streamNovaMessage(message, state().getNovaHistory(), (text) => {
      novaBubble.textContent = text;
      els.chatBubbles.scrollTop = els.chatBubbles.scrollHeight;
    });
    state().addNovaExchange(message, novaText);
  } catch (error) {
    novaBubble.textContent = error.message || 'Nova is temporarily unavailable. Please try again.';
  }
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
}

setupChat();

window.FinSightChat = { sendNovaMessage, setupChat };
