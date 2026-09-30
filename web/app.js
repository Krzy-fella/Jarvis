'use strict';
const $ = id => document.getElementById(id);
const fragment = location.hash.slice(1);
if (fragment) { sessionStorage.setItem('jarvis-token', fragment); history.replaceState(null, '', location.pathname); }
const token = sessionStorage.getItem('jarvis-token') || '';
let revision = -1, current = null, stopped = false, reading = false, renderedCount = 0;
let selecting = false, selectedChats = new Set(), deleteIds = [], sidebarSignature = '';
const drafts = new Map();
const inputHistory = window.JarvisInputHistory($('message'), () => (current?.messages || []).filter(message => message.role === 'user').map(message => message.content));
let selectedExecution = null, executionReturnFocus = null;
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
  if (current && state.revision < current.revision) return;
  const previousPending = current?.pending?.id;
  const changedChat = current?.chat_id !== state.chat_id;
  if (changedChat) {
    inputHistory.reset();
    closeExecution();
    if (current) drafts.set(current.chat_id, $('message').value);
    $('message').value = drafts.get(state.chat_id) || '';
    $('message').style.height = '';
    renderedCount = state.messages.length;
    if ('speechSynthesis' in window) speechSynthesis.cancel();
  }
  current = state;
  $('connection').textContent = 'Connected locally';
  $('profile').textContent = state.profile;
  $('provider').textContent = state.provider === 'ollama' ? 'Ollama cloud' : state.provider;
  $('chat-title').textContent = state.chat_title || 'New conversation';
  renderChats(state);
  $('status').textContent = (state.save_error || state.status) + (state.approval === 'auto' ? ' · Auto-approval on' : '');
  $('approval-mode').value = state.approval;
  $('approval-mode').disabled = state.busy;
  for (const id of ['show-memory', 'forget-memory', 'menu-new-chat', 'menu-skills']) $(id).disabled = state.busy;
  $('send').disabled = state.busy;
  $('new-chat').disabled = state.busy;
  $('skills').disabled = state.busy;
  if (changedChat || state.revision !== revision) {
    const scroll = $('scroll-area'); const nearBottom = scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight < 100;
    $('welcome').hidden = state.messages.length > 0;
    $('messages').replaceChildren();
    state.messages.forEach((message, index) => {
      const item = document.createElement('article'); item.className = 'message ' + message.role;
      const label = document.createElement('div'); label.className = 'message-label';
      label.textContent = message.label || ({assistant:'JARVIS', user:'YOU', error:'SOMETHING WENT WRONG', tool:'RESULT'}[message.role]);
      item.append(label, contentNode(message.content));
      if (message.execution) {
        const button = document.createElement('button'); button.className = 'execution-button';
        button.textContent = 'See execution process'; button.setAttribute('aria-label', 'See execution process'); button.dataset.executionId = message.execution.id;
        button.setAttribute('aria-controls', 'execution-panel');
        button.setAttribute('aria-expanded', String(selectedExecution === message.execution.id));
        button.addEventListener('click', () => openExecution(message.execution.id, button)); item.append(button);
      }
      $('messages').append(item);
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
    else if (changedChat || nearBottom || state.messages.at(-1)?.role === 'user') scroll.scrollTop = scroll.scrollHeight;
  }
  renderExecution();
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
  try { await api('message', {text: text.trim(), chat_id: current?.chat_id ?? null}); drafts.delete(current?.chat_id ?? null); inputHistory.reset(); $('message').value = ''; $('message').style.height = ''; render(await api('state')); }
  catch (error) { showError(error); $('send').disabled = false; }
}
$('composer').addEventListener('submit', event => { event.preventDefault(); send($('message').value); });
$('message').addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); send($('message').value); } });
$('message').addEventListener('input', () => { $('message').style.height = 'auto'; $('message').style.height = Math.min($('message').scrollHeight, 180) + 'px'; });
document.querySelectorAll('[data-prompt]').forEach(button => button.addEventListener('click', () => send(button.dataset.prompt)));
$('skills').addEventListener('click', () => send('Check which of your skills are ready to use on my computer.'));
$('conversation-nav').addEventListener('click', () => $('message').focus());
$('new-chat').addEventListener('click', async () => { try { await api('clear', {}); render(await api('state')); closeChatDrawer(); $('message').focus(); } catch (error) { showError(error); } });
$('menu-button').addEventListener('click', () => { $('interface-menu').hidden = !$('interface-menu').hidden; $('menu-button').setAttribute('aria-expanded', String(!$('interface-menu').hidden)); });
document.addEventListener('keydown', event => { if (event.key === 'Escape') { closeChatContext(); document.body.classList.remove('chats-open'); $('toggle-chats').setAttribute('aria-expanded', 'false'); $('interface-menu').hidden = true; $('menu-button').setAttribute('aria-expanded', 'false'); } });
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
  if (confirm('Forget saved notes and cross-chat memory? Saved sidebar chats remain; delete those separately. This cannot be undone.')) {
    send('/forget all'); $('interface-menu').hidden = true;
  }
});


function renderChats(state) {
  const chats = state.chats || [];
  selectedChats = new Set([...selectedChats].filter(id => chats.some(chat => chat.id === id)));
  const signature = JSON.stringify([chats, state.chat_id, state.busy, selecting, [...selectedChats]]);
  if (signature === sidebarSignature) return;
  sidebarSignature = signature;
  const list = $('chat-list'); list.replaceChildren();
  $('chat-empty').hidden = chats.length > 0;
  $('selection-bar').hidden = !selecting;
  $('selection-count').textContent = selectedChats.size + ' selected';
  $('select-chats').disabled = state.busy || !chats.length;
  for (const id of ['pin-selected', 'unpin-selected', 'delete-selected']) $(id).disabled = state.busy || !selectedChats.size;
  for (const [label, pinned] of [['Pinned', true], ['Recents', false]]) {
    const group = chats.filter(chat => chat.pinned === pinned);
    if (!group.length) continue;
    const heading = document.createElement('h3'); heading.textContent = label; list.append(heading);
    for (const chat of group) {
      const row = document.createElement('div'); row.className = 'chat-row'; row.dataset.chatId = chat.id;
      row.classList.toggle('current', chat.id === state.chat_id);
      row.classList.toggle('selected', selectedChats.has(chat.id));
      if (selecting) {
        const box = document.createElement('input'); box.type = 'checkbox'; box.checked = selectedChats.has(chat.id);
        box.setAttribute('aria-label', 'Select chat: ' + chat.title); box.disabled = state.busy;
        box.addEventListener('change', () => toggleSelection(chat.id)); row.append(box);
      }
      const open = document.createElement('button'); open.className = 'chat-name'; open.textContent = chat.title;
      open.title = chat.title; open.disabled = state.busy; open.setAttribute('aria-label', 'Open chat: ' + chat.title);
      if (chat.id === state.chat_id) open.setAttribute('aria-current', 'page');
      open.addEventListener('click', () => selecting ? toggleSelection(chat.id) : openChat(chat.id)); row.append(open);
      const more = document.createElement('button'); more.className = 'chat-more'; more.textContent = '⋯';
      more.setAttribute('aria-label', 'Actions for chat: ' + chat.title); more.disabled = state.busy;
      more.addEventListener('click', event => { event.stopPropagation(); const rect = more.getBoundingClientRect(); openChatContext(rect.left, rect.bottom, chat.id); }); row.append(more);
      const remove = document.createElement('button'); remove.className = 'chat-delete'; remove.textContent = '×';
      remove.setAttribute('aria-label', 'Delete chat: ' + chat.title); remove.disabled = state.busy;
      remove.addEventListener('click', () => requestDelete([chat.id])); row.append(remove);
      row.addEventListener('contextmenu', event => { event.preventDefault(); event.stopPropagation(); openChatContext(event.clientX, event.clientY, chat.id); });
      row.addEventListener('keydown', event => {
        if (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) {
          event.preventDefault(); const rect = row.getBoundingClientRect(); openChatContext(rect.left, rect.bottom, chat.id);
        }
      });
      list.append(row);
    }
  }
}
function toggleSelection(id) {
  if (current?.busy) return;
  selectedChats.has(id) ? selectedChats.delete(id) : selectedChats.add(id);
  renderChats(current);
}
async function openChat(id) {
  if (current?.busy) return;
  try {
    await api('chats/open', {chat_id: id}); render(await api('state'));
    closeChatDrawer(); $('message').focus();
  } catch (error) { showError(error); }
}
function closeChatContext() { $('chat-context').hidden = true; }
function openChatContext(x, y, id = null) {
  if (current?.busy) return;
  if (id && !selectedChats.has(id)) selectedChats = new Set([id]);
  const menu = $('chat-context'); menu.hidden = false;
  for (const action of ['pin', 'unpin', 'delete']) $('context-' + action).disabled = !selectedChats.size;
  $('context-all').disabled = !(current?.chats?.length);
  menu.style.left = Math.max(8, Math.min(x, innerWidth - menu.offsetWidth - 8)) + 'px';
  menu.style.top = Math.max(8, Math.min(y, innerHeight - menu.offsetHeight - 8)) + 'px';
  $('context-select').focus(); renderChats(current);
}
$('chat-panel').addEventListener('contextmenu', event => { event.preventDefault(); openChatContext(event.clientX, event.clientY); });
document.addEventListener('click', event => { if (!event.target.closest('#chat-context') && !event.target.closest('.chat-more')) closeChatContext(); });
window.addEventListener('resize', closeChatContext);
$('select-chats').addEventListener('click', () => { selecting = !selecting; if (!selecting) selectedChats.clear(); renderChats(current); });
$('done-selecting').addEventListener('click', () => { selecting = false; selectedChats.clear(); renderChats(current); });
$('context-select').addEventListener('click', () => { selecting = true; closeChatContext(); renderChats(current); });
$('context-all').addEventListener('click', () => { selecting = true; selectedChats = new Set(current.chats.map(chat => chat.id)); closeChatContext(); renderChats(current); });
async function bulkChats(action, ids = [...selectedChats]) {
  closeChatContext();
  if (!ids.length || current?.busy) return;
  try { await api('chats/bulk', {ids, action}); render(await api('state')); }
  catch (error) { showError(error); }
}
function requestDelete(ids) {
  closeChatContext();
  if (!ids.length || current?.busy) return;
  deleteIds = [...ids];
  const titles = current.chats.filter(chat => ids.includes(chat.id)).map(chat => chat.title);
  $('delete-description').textContent = ids.length === 1 ? 'Delete “' + titles[0] + '”? This cannot be undone.' : 'Delete these ' + ids.length + ' chats? This cannot be undone.\n' + titles.slice(0, 5).join('\n') + (titles.length > 5 ? '\n…' : '');
  $('delete-dialog').returnValue = 'cancel';
  $('delete-dialog').showModal();
}
$('delete-dialog').addEventListener('close', () => {
  if ($('delete-dialog').returnValue === 'delete') bulkChats('delete', deleteIds);
  deleteIds = [];
});
for (const prefix of ['context-', '']) {
  const suffix = prefix ? '' : '-selected';
  $(prefix + 'pin' + suffix).addEventListener('click', () => bulkChats('pin'));
  $(prefix + 'unpin' + suffix).addEventListener('click', () => bulkChats('unpin'));
  $(prefix + 'delete' + suffix).addEventListener('click', () => requestDelete([...selectedChats]));
}
$('toggle-chats').addEventListener('click', () => {
  const open = document.body.classList.toggle('chats-open'); $('toggle-chats').setAttribute('aria-expanded', String(open));
});

function closeChatDrawer() {
  document.body.classList.remove('chats-open'); $('toggle-chats').setAttribute('aria-expanded', 'false');
}
document.addEventListener('click', event => {
  if (document.body.classList.contains('chats-open') && !event.target.closest('.sidebar, #toggle-chats, #chat-context, #delete-dialog')) closeChatDrawer();
});

const executionStages = {preparing:'Preparing response', approval:'Waiting for approval', running:'Running task', completed:'Completed', failed:'Failed', cancelled:'Cancelled', timed_out:'Timed out', detached:'Launched in background', interrupted:'Interrupted'};
function closeExecution() {
  selectedExecution = null; $('execution-panel').hidden = true;
  document.querySelector('.shell').classList.remove('execution-open');
  document.querySelectorAll('.execution-button').forEach(button => button.setAttribute('aria-expanded', 'false'));
}
function openExecution(id, button) {
  selectedExecution = id; executionReturnFocus = button;
  $('execution-panel').hidden = false; document.querySelector('.shell').classList.add('execution-open');
  document.querySelectorAll('.execution-button').forEach(item => item.setAttribute('aria-expanded', String(item.dataset.executionId === id)));
  renderExecution(); $('close-execution').focus();
}
function duration(seconds) {
  seconds = Math.max(0, Math.floor(seconds));
  return seconds >= 3600 ? Math.floor(seconds / 3600) + 'h ' + Math.floor(seconds % 3600 / 60) + 'm ' + seconds % 60 + 's' : seconds >= 60 ? Math.floor(seconds / 60) + 'm ' + seconds % 60 + 's' : seconds + 's';
}
function renderExecution() {
  if (!selectedExecution || !current) return;
  const task = current.messages.find(message => message.execution?.id === selectedExecution)?.execution;
  if (!task) { closeExecution(); return; }
  $('execution-stage').textContent = executionStages[task.stage] || task.stage;
  $('execution-elapsed').textContent = duration((task.ended_at || Date.now() / 1000) - (task.run_started_at || task.started_at)) + (task.run_started_at ? (task.ended_at ? ' runtime' : ' running') : ' elapsed');
  const progress = $('execution-progress');
  if (task.stage === 'completed') { progress.value = 100; $('execution-progress-label').textContent = 'Task finished · 100%'; }
  else if (task.percent !== null && task.percent !== undefined) {
    progress.value = task.percent;
    $('execution-progress-label').textContent = task.phase + ' · ' + task.percent.toFixed(1) + '% (tool-reported phase progress)';
  } else {
    progress.removeAttribute('value');
    $('execution-progress-label').textContent = task.stage === 'running' ? 'Running · this tool has not reported a percentage.' : task.stage === 'preparing' ? 'Waiting for the AI provider…' : executionStages[task.stage];
  }
  progress.classList.toggle('inactive', Boolean(task.ended_at));
  const steps = $('execution-steps');
  const signature = JSON.stringify(task.steps);
  if (steps.dataset.signature !== signature) {
    steps.replaceChildren(); steps.dataset.signature = signature;
    task.steps.forEach(step => { const item = document.createElement('li'); item.textContent = (executionStages[step.stage] || step.stage) + ' · ' + duration(step.at - task.started_at); steps.append(item); });
  }
  $('execution-command').textContent = task.command || 'No command requested.';
  $('execution-info').textContent = task.pid ? 'Process ' + task.pid + (task.exit_code !== undefined ? ' · Exit code ' + task.exit_code : '') : task.tool && task.tool !== 'none' ? 'Task: ' + task.tool.replaceAll('_', ' ') : 'No external process requested.';
  const log = $('execution-log');
  const text = task.log || (task.stage === 'running' ? 'Waiting for output… Some tools buffer output until later.' : 'No command output.');
  if (log.textContent !== text) { log.textContent = text; if ($('execution-follow').checked) log.scrollTop = log.scrollHeight; }
  $('execution-result').textContent = task.stage === 'detached' ? 'The process was launched separately. Its later progress and completion are not monitored.' : task.result_note || 'Output updates as the tool emits it. The most recent 16,000 characters are retained.';
}
function dismissExecution() {
  const id = selectedExecution;
  closeExecution();
  const button = [...document.querySelectorAll('.execution-button')].find(item => item.dataset.executionId === id);
  (button || executionReturnFocus)?.focus();
}
$('close-execution').addEventListener('click', dismissExecution);
document.addEventListener('keydown', event => { if (event.key === 'Escape' && selectedExecution) dismissExecution(); });
