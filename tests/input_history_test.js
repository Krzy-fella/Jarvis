const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const window = {};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/input-history.js'),'utf8'),{window});
let entries = ['first','second'];
const handlers = {};
const input = {value:'unfinished draft',selectionStart:16,selectionEnd:16,style:{},scrollHeight:42,
  addEventListener(name,fn){handlers[name]=fn;},setSelectionRange(a,b){this.selectionStart=a;this.selectionEnd=b;}};
const history = window.JarvisInputHistory(input,()=>entries);
function key(name,extras={}) { let prevented=false; handlers.keydown({key:name,preventDefault(){prevented=true;},...extras}); return prevented; }
assert.equal(key('ArrowUp'),true); assert.equal(input.value,'second');
key('ArrowUp'); assert.equal(input.value,'first'); key('ArrowUp'); assert.equal(input.value,'first');
key('ArrowDown'); assert.equal(input.value,'second'); key('ArrowDown'); assert.equal(input.value,'unfinished draft');
history.reset(); input.value='line one\nline two'; input.setSelectionRange(input.value.length,input.value.length);
assert.equal(key('ArrowUp'),false); assert.equal(input.value,'line one\nline two');
input.setSelectionRange(0,0); key('ArrowUp'); assert.equal(input.value,'second');
input.value='edited message'; handlers.input(); input.setSelectionRange(14,14);
key('ArrowUp'); assert.equal(input.value,'second'); key('ArrowDown'); assert.equal(input.value,'edited message');
history.reset(); entries=['other chat']; key('ArrowUp'); assert.equal(input.value,'other chat');
history.reset(); input.setSelectionRange(0,4); assert.equal(key('ArrowUp'),false);
input.setSelectionRange(0,0); assert.equal(key('ArrowUp',{isComposing:true}),false); assert.equal(key('ArrowUp',{shiftKey:true}),false);
entries=[]; history.reset(); assert.equal(key('ArrowUp'),false);
console.log('Input history checks passed: navigation, drafts, editing, chat scope, multiline and composition');
