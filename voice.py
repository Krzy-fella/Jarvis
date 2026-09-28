"""
voice.py — Speech-to-text (wake word + command capture) and text-to-speech.

Uses SpeechRecognition + PyAudio for input, pyttsx3 for output by default.
If you have `edge-tts` installed and want higher quality speech, set
JARVIS_TTS_ENGINE=edge in your environment; edge-tts is async and writes to
an mp3 that's played back, so it has a bit more latency than pyttsx3.
"""

import os
import tempfile
import shutil
import subprocess
import re
from contextlib import contextmanager

import speech_recognition as sr

import config

_TTS_ENGINE = os.environ.get("JARVIS_TTS_ENGINE", "edge")
_VOICE = os.environ.get("JARVIS_VOICE", "en-GB-RyanNeural")
_RATE = os.environ.get("JARVIS_VOICE_RATE", "-5%")
_PITCH = os.environ.get("JARVIS_VOICE_PITCH", "-8Hz")

_recognizer = sr.Recognizer()
_recognizer.operation_timeout = 15
_microphone = None


@contextmanager
def _quiet_device_probe():
    """Silence native ALSA/JACK probing only; Python exceptions still propagate.

    This changes process stderr briefly and is used only by terminal voice mode.
    Set JARVIS_AUDIO_DEBUG=1 to see the underlying driver diagnostics.
    """
    if os.name != 'posix' or os.environ.get('JARVIS_AUDIO_DEBUG') == '1':
        yield
        return
    saved = os.dup(2)
    try:
        with open(os.devnull, 'w') as sink:
            os.dup2(sink.fileno(), 2)
            yield
    finally:
        os.dup2(saved, 2)
        os.close(saved)


def _get_microphone():
    global _microphone
    if _microphone is None:
        index = os.environ.get('JARVIS_MIC_INDEX', '').strip()
        with _quiet_device_probe():
            try:
                mic = sr.Microphone(device_index=int(index) if index else None)
            except AssertionError as exc:
                raise OSError('Invalid microphone selection. Run jarvis --list-microphones and check JARVIS_MIC_INDEX.') from exc
            mic.__enter__()
        if mic.stream is None:
            raise OSError('Could not open the microphone. Check your system input device or set JARVIS_MIC_INDEX.')
        try:
            _recognizer.adjust_for_ambient_noise(mic, duration=1)
        except BaseException:
            mic.__exit__(None, None, None)
            raise
        _microphone = mic
    return _microphone


def close_microphone():
    global _microphone
    if _microphone is not None:
        try:
            _microphone.__exit__(None, None, None)
        finally:
            _microphone = None


def list_microphones():
    with _quiet_device_probe():
        import pyaudio
        audio = pyaudio.PyAudio()
        try:
            return [(i, audio.get_device_info_by_index(i)['name'])
                    for i in range(audio.get_device_count())
                    if audio.get_device_info_by_index(i)['maxInputChannels'] > 0]
        finally:
            audio.terminate()


def _listen(timeout, phrase_time_limit):
    mic = _get_microphone()
    # Drop audio accumulated while JARVIS was speaking or calling the model.
    stream = mic.stream.pyaudio_stream
    available = stream.get_read_available()
    if available:
        stream.read(available, exception_on_overflow=False)
    return _recognizer.listen(mic, timeout=timeout, phrase_time_limit=phrase_time_limit)


def speak(text: str) -> None:
    """Speak `text` aloud. Falls back to printing if TTS is unavailable."""
    if not text:
        return
    try:
        if _TTS_ENGINE == "edge":
            _speak_edge(text)
        else:
            _speak_pyttsx3(text)
    except Exception as exc:  # noqa: BLE001
        print(f"[voice] {_TTS_ENGINE} speech unavailable ({type(exc).__name__}).")
        if _TTS_ENGINE == "edge":
            try:
                _speak_pyttsx3(text)
                return
            except Exception as fallback:
                print(f"[voice] Offline speech also unavailable ({type(fallback).__name__}).")
        print(f"JARVIS: {text}")


def _speak_pyttsx3(text: str) -> None:
    import pyttsx3

    engine = pyttsx3.init()
    try:
        preferred = os.environ.get("JARVIS_OFFLINE_VOICE", "english")
        voices = engine.getProperty("voices")
        selected = next((v for v in voices if preferred.lower() in v.id.lower()), None)
        if selected:
            engine.setProperty("voice", selected.id)
        engine.setProperty("rate", int(os.environ.get("JARVIS_OFFLINE_RATE", "170")))
        engine.setProperty("volume", 1.0)
        engine.say(text)
        engine.runAndWait()
    finally:
        engine.stop()


def _speak_edge(text: str) -> None:
    import asyncio

    import edge_tts
    player = shutil.which("ffplay")
    if not player:
        raise RuntimeError("Install ffmpeg for Edge TTS playback (ffplay).")

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        asyncio.run(save_voice_sample(text, tmp_path))
        subprocess.run([player, "-nodisp", "-autoexit", "-loglevel", "error", tmp_path], check=True, timeout=180)
    finally:
        os.remove(tmp_path)


async def save_voice_sample(text: str, path: str) -> None:
    """Create a sample with the same preset as live speech (no API key needed)."""
    import asyncio
    import edge_tts
    communicator = edge_tts.Communicate(text, voice=_VOICE, rate=_RATE, pitch=_PITCH)
    await asyncio.wait_for(communicator.save(path), timeout=30)


def listen_for_wake_word(timeout: int = None) -> bool:
    """
    Block until the wake word is heard (or `timeout` seconds elapse).
    Returns True if the wake word was detected, False on timeout.
    """
    print(f"[voice] Listening for wake word '{config.WAKE_WORD}'...")
    try:
        audio = _listen(timeout=timeout, phrase_time_limit=4)
        heard = _recognizer.recognize_google(audio).lower()
        return bool(re.search(r"\b" + re.escape(config.WAKE_WORD) + r"\b", heard))
    except sr.WaitTimeoutError:
        return False
    except sr.UnknownValueError:
        return False
    except sr.RequestError as exc:
        print(f"[voice] Speech recognition service error: {exc}")
        return False


def listen_command(timeout: int = 6) -> str:
    """Capture one spoken command and return it as text (empty string on failure)."""
    print("[voice] Listening for command...")
    try:
        audio = _listen(timeout=timeout, phrase_time_limit=10)
        return _recognizer.recognize_google(audio)
    except sr.WaitTimeoutError:
        print("[voice] Timed out waiting for a command.")
        return ""
    except sr.UnknownValueError:
        print("[voice] Didn't catch that.")
        return ""
    except sr.RequestError as exc:
        print(f"[voice] Speech recognition service error: {exc}")
        return ""
