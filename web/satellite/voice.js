/* Optional browser speech, isolated from chat. No audio reaches the JARVIS server. */
(function (root) {
  'use strict';
  root.SatelliteVoice = function (callbacks) {
    var recognition = null;
    var Recognition = root.SpeechRecognition || root.webkitSpeechRecognition;
    var canListen = !!(root.isSecureContext && Recognition);
    var canSpeak = !!(root.speechSynthesis && root.SpeechSynthesisUtterance);
    function failed(message) { callbacks.notice(message); callbacks.state('Error'); }
    function stop() {
      try { if (recognition) recognition.abort(); } catch (_) { /* already stopped */ }
      try { if (canSpeak) root.speechSynthesis.cancel(); } catch (_) { /* text stays available */ }
    }
    return {
      canListen: canListen, canSpeak: canSpeak, stop: stop,
      listen: function () {
        if (!canListen) return failed('Voice input is unavailable on this device. You can still type messages.');
        try {
          stop(); recognition = new Recognition();
          recognition.lang = root.navigator.language || 'en-US';
          recognition.continuous = false; recognition.interimResults = false;
          recognition.onstart = function () { callbacks.state('Listening'); };
          recognition.onresult = function (event) {
            callbacks.transcript(String(event.results[0][0].transcript).slice(0,4000));
            callbacks.notice('Check the recognized text, then choose Send message.');
          };
          recognition.onerror = function () { failed('Microphone or speech recognition failed. Check browser permissions, or type your message.'); };
          recognition.onend = function () { callbacks.state('Idle'); recognition = null; };
          recognition.start();
        } catch (_) { failed('Voice input could not start. You can still type messages.'); }
      },
      speak: function (text) {
        if (!canSpeak) return failed('Speech output is unavailable. The reply is still visible.');
        try {
          stop(); var utterance = new root.SpeechSynthesisUtterance(text);
          utterance.lang = root.navigator.language || 'en-US';
          utterance.onstart = function () { callbacks.state('Speaking'); };
          utterance.onend = function () { callbacks.state('Idle'); };
          utterance.onerror = function () { failed('Speech output failed. The reply is still visible.'); };
          root.speechSynthesis.speak(utterance);
        } catch (_) { failed('Speech output failed. The reply is still visible.'); }
      }
    };
  };
}(window));
