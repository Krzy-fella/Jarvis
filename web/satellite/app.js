(function () {
  'use strict';
  var el = function (id) { return document.getElementById(id); };
  var key = 'jarvis.satellite.credential';
  var credential = '', timer = null, generation = 0, delay = 1500, pending = null;
  var busy = false, online = false, polling = false, sending = false, lastRender = '', latestReply = '';
  var historyEntries = [];
  var inputHistory = window.JarvisInputHistory(el('message'),function () { return historyEntries; });
  function notice(text) { el('notice').textContent = text || ''; }
  function state(text) { el('status').textContent = text; }
  function storage(which, operation, value) {
    try { return window[which][operation](key,value); } catch (_) { return null; }
  }
  function controls() { el('send').disabled = sending || busy || !online; el('microphone').disabled = !voice.canListen || busy || sending; }
  var voice = window.SatelliteVoice({notice:notice,state:state,transcript:function (text) { inputHistory.reset(); el('message').value = text; el('message').focus(); }});
  el('voice-help').textContent = (voice.canListen ? 'Microphone is optional. Browser speech recognition may send audio to the browser vendor; review its privacy settings. Recognized text is never sent until you choose Send. ' : 'Voice input is unavailable here. Use a supported browser with trusted HTTPS, or type your message. ') + (voice.canSpeak ? 'Choose Read latest reply to use this device’s voice.' : 'Speech output is unavailable; replies remain visible.');
  el('read-reply').disabled = !voice.canSpeak;
  el('microphone').onclick = voice.listen;
  el('read-reply').onclick = function () { if (latestReply) voice.speak(latestReply); else notice('Send a message first.'); };
  async function request(path, body, token) {
    var controller = new AbortController();
    var timeout = setTimeout(function () { controller.abort(); },12000);
    try {
      var headers = {};
      if (token) headers.Authorization = 'Bearer ' + token;
      if (body) headers['Content-Type'] = 'application/json';
      var response = await fetch(path,{method:body ? 'POST' : 'GET',headers:headers,body:body ? JSON.stringify(body) : undefined,signal:controller.signal,cache:'no-store',credentials:'omit',redirect:'error'});
      var data = await response.json();
      if (!response.ok) { var error = new Error(typeof data.detail === 'string' ? data.detail : 'Satellite request failed.'); error.status = response.status; throw error; }
      return data;
    } finally { clearTimeout(timeout); }
  }
  function disconnect(message) {
    generation++; clearTimeout(timer); credential = ''; online = false; busy = false; sending = false; pending = null;
    storage('localStorage','removeItem'); storage('sessionStorage','removeItem'); voice.stop();
    el('chat-panel').hidden = true; el('pair-panel').hidden = false;
    inputHistory.reset(); historyEntries = [];
    el('messages').replaceChildren(); lastRender = ''; latestReply = ''; el('message').value = '';
    el('identity').textContent = 'Connect this screen to your JARVIS PC.'; state('Disconnected'); notice(message); controls();
  }
  function render(data) {
    el('identity').textContent = data.device.device_name + ' · ' + data.device.device_type + ' · ' + data.device.device_id.slice(0,8);
    var conversation = data.conversation;
    busy = conversation.busy;
    historyEntries = conversation.messages.filter(function (message) { return message.role === 'user'; }).map(function (message) { return message.content; });
    if (!['Listening','Speaking'].includes(el('status').textContent)) state(conversation.status);
    var serialized = JSON.stringify(conversation.messages);
    if (serialized !== lastRender) {
      var list = el('messages');
      var nearBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 100;
      list.replaceChildren();
      if (!conversation.messages.length) { var empty = document.createElement('p'); empty.className = 'empty'; empty.textContent = 'Your conversation begins here.'; list.appendChild(empty); }
      conversation.messages.forEach(function (message) {
        var item = document.createElement('article'); item.className = 'message ' + (message.role === 'user' ? 'user' : 'assistant');
        var label = document.createElement('h3'); label.textContent = message.role === 'user' ? 'You' : 'JARVIS';
        var text = document.createElement('p'); text.textContent = message.content;
        item.append(label,text); list.appendChild(item);
        if (message.role === 'assistant') latestReply = message.content;
      });
      if (nearBottom || !lastRender) list.scrollTop = list.scrollHeight;
      lastRender = serialized;
    }
    if (conversation.error) notice(conversation.error);
    controls();
  }
  async function poll() {
    clearTimeout(timer);
    if (!credential || polling) return;
    var version = generation, token = credential;
    polling = true;
    try {
      var data = await request('/api/state',null,token);
      if (version !== generation) return;
      if (!online) notice(pending ? 'Connection restored. If your message is missing, choose Send message to retry it safely.' : '');
      online = true; delay = 1500; el('connection').textContent = 'Connected'; render(data);
    } catch (error) {
      if (version !== generation) return;
      online = false;
      if (error.status === 401) { disconnect('This credential expired or was revoked. Get a new pairing code from the PC.'); return; }
      state('Disconnected'); el('connection').textContent = 'Reconnecting…';
      notice(error.status ? error.message : 'Connection lost. Your chat is saved on the PC. Reconnecting automatically…');
      delay = Math.min(delay * 2,15000); controls();
    } finally {
      polling = false;
      if (credential) timer = setTimeout(poll,delay);
    }
  }
  function connected(token) {
    credential = token; generation++; delay = 1500; online = false; busy = false; pending = null; lastRender = ''; latestReply = '';
    el('pair-panel').hidden = true; el('chat-panel').hidden = false; state('Connecting'); controls(); poll();
  }
  el('pair-form').onsubmit = async function (event) {
    event.preventDefault(); el('connect').disabled = true; notice('Connecting…');
    try {
      var data = await request('/api/pair',{code:el('pair-code').value.trim(),device_name:el('device-name').value.trim(),device_type:el('device-type').value});
      storage('sessionStorage','removeItem'); storage('localStorage','removeItem');
      var target = el('remember-device').checked ? 'localStorage' : 'sessionStorage';
      storage(target,'setItem',data.credential);
      el('pair-code').value = ''; notice(''); connected(data.credential);
      if (storage(target,'getItem') !== data.credential) notice('Browser storage is blocked. Stay on this page; reloading will require a new pairing code.');
    } catch (error) { state('Error'); notice(error.status ? error.message : 'Could not confirm pairing. Check the PC. If the code was consumed, restart Satellite for a new code.'); }
    finally { el('connect').disabled = false; }
  };
  el('chat-form').onsubmit = async function (event) {
    event.preventDefault(); var text = el('message').value.trim();
    if (!text || sending || busy || !online) return;
    if (!pending || pending.text !== text) {
      var bytes = new Uint8Array(16); window.crypto.getRandomValues(bytes);
      pending = {text:text,request_id:Array.from(bytes,function (b) { return b.toString(16).padStart(2,'0'); }).join('')};
    }
    var version = generation; sending = true; controls(); state('Thinking'); notice('');
    try {
      await request('/api/message',pending,credential);
      if (version !== generation) return;
      pending = null; inputHistory.reset(); el('message').value = ''; busy = true; poll();
    } catch (error) {
      if (version !== generation) return;
      if (error.status === 401) { disconnect('Pair this device again on the PC.'); return; }
      state('Error'); notice(error.status ? error.message : 'Delivery could not be confirmed. Reconnect, then choose Send message to retry the same message safely.');
    } finally { if (version === generation) { sending = false; controls(); } }
  };
  el('reconnect').onclick = function () { delay = 1500; poll(); };
  el('forget-device').onclick = function () { disconnect('Disconnected from this browser. Saved history remains on the PC. Use jarvis --satellite-revoke on the PC to revoke a lost device.'); };
  el('fullscreen').onclick = function () {
    try { var result = document.documentElement.requestFullscreen(); if (result && result.catch) result.catch(function () { notice('Full screen is unavailable. Browser view still works.'); }); }
    catch (_) { notice('Full screen is unavailable. Browser view still works.'); }
  };
  document.addEventListener('keydown',function (event) {
    if (!['ArrowUp','ArrowDown'].includes(event.key) || /^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName) || event.target.id === 'messages') return;
    var focusable = Array.from(document.querySelectorAll('button,input,textarea,select,[tabindex="0"]')).filter(function (node) { return !node.disabled && node.offsetParent !== null; });
    var current = focusable.indexOf(document.activeElement), direction = event.key === 'ArrowDown' ? 1 : -1;
    if (focusable.length) { event.preventDefault(); focusable[(current + direction + focusable.length) % focusable.length].focus(); }
  });
  if (!window.fetch || !window.AbortController || !window.crypto || !window.crypto.getRandomValues) {
    el('connect').disabled = true; notice('This browser is too old for Satellite Beta. Try an updated browser on another device.'); return;
  }
  var saved = storage('sessionStorage','getItem') || storage('localStorage','getItem');
  if (saved) connected(saved); else controls();
}());
