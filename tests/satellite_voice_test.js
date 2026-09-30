// No browser packages: run the real progressive speech adapter with missing/failing APIs.
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname,'../web/satellite/voice.js'),'utf8');
function setup(extras={}) {
  const window = {navigator:{language:'en-US'},...extras};
  const notices=[], states=[], transcripts=[];
  vm.runInNewContext(source,{window});
  const voice = window.SatelliteVoice({notice:t=>notices.push(t),state:t=>states.push(t),transcript:t=>transcripts.push(t)});
  return {voice,notices,states,transcripts};
}
const unavailable = setup();
assert.equal(unavailable.voice.canListen,false); assert.equal(unavailable.voice.canSpeak,false);
unavailable.voice.listen(); unavailable.voice.speak('Reply stays visible'); unavailable.voice.stop();
assert.match(unavailable.notices[0],/still type/); assert.match(unavailable.notices[1],/still visible/);
const insecure = setup({isSecureContext:false,SpeechRecognition:function(){throw Error('must not construct');}});
assert.equal(insecure.voice.canListen,false); insecure.voice.listen();
const denied = setup({isSecureContext:true,SpeechRecognition:function(){this.start=()=>{throw Error('permission denied');};}});
denied.voice.listen(); assert.match(denied.notices[0],/still type/);
let recognition;
const supported = setup({isSecureContext:true,SpeechRecognition:function(){recognition=this; this.start=()=>this.onstart(); this.abort=()=>{};}});
supported.voice.listen(); assert.equal(supported.states[0],'Listening');
recognition.onresult({results:[[{transcript:'Hello TV'}]]});
assert.deepEqual(supported.transcripts,['Hello TV']); assert.match(supported.notices[0],/choose Send/);
recognition.onerror(); recognition.onend(); assert.match(supported.notices[1],/type your message/);
const failedSpeech = setup({SpeechSynthesisUtterance:function(text){this.text=text;},speechSynthesis:{cancel(){},speak(){throw Error('no audio');}}});
failedSpeech.voice.speak('A text response'); assert.match(failedSpeech.notices[0],/reply is still visible/);
let spoken;
const asyncFail = setup({SpeechSynthesisUtterance:function(text){this.text=text;},speechSynthesis:{cancel(){},speak(u){spoken=u;u.onstart();}}});
asyncFail.voice.speak('Visible response'); assert.equal(spoken.text,'Visible response'); spoken.onerror();
assert.match(asyncFail.notices[0],/still visible/);
console.log('Browser speech fallback checks passed');
