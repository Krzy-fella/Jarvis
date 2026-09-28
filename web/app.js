'use strict';
const $ = id => document.getElementById(id);
const fragment = location.hash.slice(1);
if (fragment) { sessionStorage.setItem('jarvis-token', fragment); history.replaceState(null, '', location.pathname); }
const token = sessionStorage.getItem('jarvis-token') || '';
let revision = -1, current = null, stopped = false, reading = false, renderedCount = 0;
async function api(path, body) {
  const response = await fetch('/api/' + path, {method: body === undefined ? 'GET' : 'POST', headers: {'X-Jarvis-Token': token, 'Content-Type': 'application/json'}, ...(body === undefined ? {} : {body: JSON.stringify(body)})});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Please check your input.');
  return data;
}
function showError(error) { $('status').textContent = error.message || String(error); }
// Treat all model/tool output as text. Never insert model HTML or execute code.
function contentNode(text) {
  const container = document.createElement('div'); container.className = 'message-content';
  const chunks = text.split(/```[^\n]*\n([\s\S]*?)```/g);
  chunks.forEach((chunk, i) => {
    if (i % 2) { const pre = document.createElement('pre'); pre.textContent = chunk; container.append(pre); }
    else {
      const parts = chunk.split(/\*\*([^*\n]+)\*\*/g);
      parts.forEach((part, j) => { const node = j % 2 ? document.createElement('strong') : document.createTextNode(part); if (j % 2) node.textContent = part; container.append(node); });
    }
  });
  return container;
}
function render(state) {
  const previousPending = current?.pending?.id;
  current = state;
  $('connection').textContent = 'Connected locally';
  $('profile').textContent = state.profile;
  $('provider').textContent = state.provider === 'ollama' ? 'Ollama cloud' : state.provider;
  $('status').textContent = state.status + (state.approval === 'auto' ? ' · Auto-approval on' : '');
  $('approval-mode').value = state.approval;
  $('approval-mode').disabled = state.busy;
  for (const id of ['show-memory', 'forget-memory', 'menu-new-chat', 'menu-skills']) $(id).disabled = state.busy;
  $('send').disabled = state.busy;
  $('new-chat').disabled = state.busy;
  $('skills').disabled = state.busy;
  if (state.revision !== revision) {
    const scroll = $('scroll-area'); const nearBottom = scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight < 100;
    $('welcome').hidden = state.messages.length > 0;
    $('messages').replaceChildren();
    state.messages.forEach((message, index) => {
      const item = document.createElement('article'); item.className = 'message ' + message.role;
      const label = document.createElement('div'); label.className = 'message-label';
      label.textContent = message.label || ({assistant:'JARVIS', user:'YOU', error:'SOMETHING WENT WRONG', tool:'RESULT'}[message.role]);
      item.append(label, contentNode(message.content)); $('messages').append(item);
      if (reading && index >= renderedCount && message.role === 'assistant' && 'speechSynthesis' in window) {
        const utterance = new SpeechSynthesisUtterance(message.content);
        utterance.lang = 'en-GB'; utterance.rate = .95;
        const voice = speechSynthesis.getVoices().find(v => v.lang === 'en-GB');
        if (voice) utterance.voice = voice;
        speechSynthesis.speak(utterance);
      }
    });
    renderedCount = state.messages.length;
    revision = state.revision;
    if (!state.messages.length) scroll.scrollTop = 0;
    else if (nearBottom || state.messages.at(-1)?.role === 'user') scroll.scrollTop = scroll.scrollHeight;
  }
  $('approval').hidden = !state.pending;
  if (state.pending) {
    $('approval-title').textContent = state.pending.tool.replaceAll('_', ' ');
    $('approval-details').textContent = state.pending.description || 'No arguments needed.';
    $('approve').disabled = $('cancel').disabled = false;
    if (state.pending.id !== previousPending) $('approval').scrollIntoView({block: 'nearest'});
  }
}
async function poll() {
  if (stopped) return;
  try { render(await api('state')); }
  catch (error) { $('connection').textContent = 'Disconnected'; showError(error); }
  if (!stopped) setTimeout(poll, 900);
}
async function send(text) {
  if (!text.trim() || current?.busy) return;
  $('send').disabled = true;
  try { await api('message', {text: text.trim()}); $('message').value = ''; $('message').style.height = ''; render(await api('state')); }
  catch (error) { showError(error); $('send').disabled = false; }
}
$('composer').addEventListener('submit', event => { event.preventDefault(); send($('message').value); });
$('message').addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); send($('message').value); } });
$('message').addEventListener('input', () => { $('message').style.height = 'auto'; $('message').style.height = Math.min($('message').scrollHeight, 180) + 'px'; });
document.querySelectorAll('[data-prompt]').forEach(button => button.addEventListener('click', () => send(button.dataset.prompt)));
$('skills').addEventListener('click', () => send('Check which of your skills are ready to use on my computer.'));
$('conversation-nav').addEventListener('click', () => $('message').focus());
$('new-chat').addEventListener('click', async () => { try { await api('clear', {}); render(await api('state')); $('message').focus(); } catch (error) { showError(error); } });
$('menu-button').addEventListener('click', () => { $('interface-menu').hidden = !$('interface-menu').hidden; $('menu-button').setAttribute('aria-expanded', String(!$('interface-menu').hidden)); });
document.addEventListener('keydown', event => { if (event.key === 'Escape') { $('interface-menu').hidden = true; $('menu-button').setAttribute('aria-expanded', 'false'); } });
document.querySelectorAll('[data-mode]').forEach(button => button.addEventListener('click', async () => {
  try { await api('interface', {mode: button.dataset.mode}); stopped = true; $('interface-menu').hidden = true; $('send').disabled = true; $('connection').textContent = 'Session ended'; $('status').textContent = button.dataset.mode === 'exit' ? 'JARVIS has closed. You can close this tab.' : 'Continue in the terminal where you launched JARVIS.'; }
  catch (error) { showError(error); }
}));
for (const [id, approve] of [['approve', true], ['cancel', false]]) {
  $(id).addEventListener('click', async () => {
    if (!current?.pending) return;
    $('approve').disabled = $('cancel').disabled = true;
    try { await api('decision', {action_id: current.pending.id, approve}); render(await api('state')); }
    catch (error) { showError(error); }
  });
}
$('toggle-speech').addEventListener('click', () => {
  if (!('speechSynthesis' in window)) { showError(new Error('This browser has no speech playback. Use voice mode from the terminal menu.')); return; }
  reading = !reading; if (!reading) speechSynthesis.cancel();
  $('toggle-speech').textContent = 'Read replies aloud: ' + (reading ? 'on' : 'off');
  $('toggle-speech').setAttribute('aria-pressed', String(reading));
});
poll();

$('menu-new-chat').addEventListener('click', () => { $('new-chat').click(); $('interface-menu').hidden = true; });
$('menu-skills').addEventListener('click', () => { $('skills').click(); $('interface-menu').hidden = true; });

$('approval-mode').addEventListener('change', async () => {
  try { await api('settings', {approval: $('approval-mode').value}); render(await api('state')); }
  catch (error) { $('approval-mode').value = current?.approval || 'ask'; showError(error); }
});
$('show-memory').addEventListener('click', () => { send('/memory'); $('interface-menu').hidden = true; });
$('forget-memory').addEventListener('click', () => {
  if (confirm('Forget all saved notes and previous conversations for this profile? This cannot be undone.')) {
    send('/forget all'); $('interface-menu').hidden = true;
  }
});
