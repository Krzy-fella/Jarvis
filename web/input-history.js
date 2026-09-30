/* Shared by both web interfaces. History belongs to the displayed conversation. */
(function (root) {
  'use strict';
  root.JarvisInputHistory = function (input, readEntries) {
    var entries = null, index = 0, draft = '';
    function reset() { entries = null; index = 0; draft = ''; }
    input.addEventListener('input', reset);
    input.addEventListener('keydown', function (event) {
      if (!['ArrowUp','ArrowDown'].includes(event.key) || event.isComposing || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      if (input.selectionStart !== input.selectionEnd) return;
      var up = event.key === 'ArrowUp';
      // Enter history on the first/last line; keep moving through it until edited.
      if (entries === null && up && input.value.slice(0,input.selectionStart).includes('\n')) return;
      if (entries === null && !up && input.value.slice(input.selectionEnd).includes('\n')) return;
      if (entries === null) {
        if (!up) return;
        entries = readEntries().filter(function (text) { return typeof text === 'string' && text.trim(); }).slice(-100);
        if (!entries.length) { reset(); return; }
        draft = input.value; index = entries.length;
      }
      event.preventDefault();
      index = Math.max(0,Math.min(entries.length,index + (up ? -1 : 1)));
      input.value = index === entries.length ? draft : entries[index];
      // Keep the cursor on the boundary used to browse, enabling repeated presses.
      var caret = up ? 0 : input.value.length;
      input.setSelectionRange(caret,caret);
      input.style.height = 'auto';
      input.style.height = Math.min(input.scrollHeight,180) + 'px';
      // Do not emit input here: it would discard the saved draft/navigation position.
    });
    return {reset:reset};
  };
}(window));
