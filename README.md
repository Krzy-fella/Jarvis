# JARVIS

A customizable local AI assistant with a dark glass-style web chat and terminal interface with readable replies, free voice options,
Ollama cloud, optional alternative AI providers, device actions and a local 3D viewer.
**MIT licensed:** fork it, modify it, and redistribute it with the license notice.

## Quick start

Linux is the primary supported platform. Core text mode also works on macOS/Windows;
Bluetooth integration specifically uses Linux BlueZ. Use Python 3.11 or newer.

```bash
git clone https://github.com/Krzy-fella/Jarvis.git
cd Jarvis
python3 scripts/install.py
```

The installer creates `.venv`, installs dependencies, copies `.env.example` only
when `.env` is absent, and installs `~/.local/bin/jarvis` on Linux/macOS. It downloads
Python packages, **not AI model weights**. Ensure `~/.local/bin` is on PATH.

Install [Ollama](https://ollama.com/download), start its service, and sign in:

```bash
ollama signin
jarvis
```

The default model is `gpt-oss:120b-cloud`. Requests run online; Ollama account limits
apply. Keep `JARVIS_OLLAMA_CLOUD_ONLY=true`: local model names are rejected and this
app never calls `ollama pull`. Set `OLLAMA_HOST` in `.env` if your server uses another
port. A normal installation uses 11434. No provider keys are included in this repo.

```bash
jarvis --mode text     # Always use terminal chat
jarvis --mode web      # Always open browser chat
jarvis --mode voice
jarvis --nxnx          # Nxnx owner profile
jarvis --provider gemini
jarvis --menu
jarvis --doctor
jarvis --test-voice
```

Text commands: `exit` quits; `menu` changes provider/mode. Ctrl+C exits text mode
or returns from voice mode. The launcher preserves your current directory, so
relative file paths and terminal actions operate there.

Alternatively run `.venv/bin/python main.py --provider ollama --mode text`.
On Windows use `.venv\Scripts\python.exe`. In VS Code choose the `.venv`
interpreter and use the included **JARVIS** launch configuration.

## Web chat and interface selection

`jarvis` defaults to **auto**: at launch, a short internet check selects web chat
when online and terminal chat otherwise. Use `--mode text` or `--mode web` to
choose explicitly. This checks at startup, not with a background network monitor.
Cloud AI still needs internet regardless of interface.

The local web app has translucent dark panels, a spacious conversation view,
readable tool results, a new-conversation button, and an interface menu. Use that
menu to return to terminal chat or choose a provider/voice mode. Each interface starts a fresh conversation view while loading saved local memory.
Browser “Read replies aloud” uses your browser's available voices; the customized
Ryan preset is used by terminal voice mode.

The server binds **127.0.0.1 only** (port 8765, or a free local port if occupied).
Keep its terminal running. The private launch link contains a random session token
in its URL fragment; the page removes it from the URL and keeps it in tab storage.
Don't share that launch link. No API keys are sent to the browser. Foreign origins
are rejected. Tool actions follow your current session approval setting. Long tools run in a
worker while the interface remains responsive. Tool output is shown on completion.
Closing the tab does not stop a running tool; keep the terminal open until it finishes.
The API provider still receives your chat and relevant tool context.

`--nxnx` selects a named **owner preference profile**, not authentication or a
privilege escalation. It encourages useful help with authorized local tasks and
addresses you as Nxnx. It does not change your approval setting, credential protections, or provider rules. Anyone with access to your OS account can select this profile.

The web UI uses local HTML/CSS/JavaScript, with no frontend build step or CDN.
Its source is in `web/`, and its server is `web_chat.py`. The Figma draft was
created, but Figma's Starter-plan tool limit prevented canvas design; the implemented
interface is currently maintained in code.

## Approval settings and memory

In the web menu, **Approval settings** offers:

1. **Approve all commands in this session** — model tool actions run without another prompt.
2. **Seek my approval for all commands** — every model tool action waits for you (the default).

In terminal chat, type `/settings`, or open `jarvis --menu` and choose Approval
settings. The preference applies to text, voice, and web within the same running
process, including interface switches. It is never stored and resets to **ask**
when JARVIS closes. A pending action must be approved/cancelled before changing
settings. Automatic approval gives the model the ability to run commands and edit
files with your OS account's permissions. Existing command/path checks remain;
these checks are not a sandbox.

JARVIS now saves successful chat turns locally for later sessions, including voice
chats. Memory starts with conversations after this update; old unsaved chats cannot
be recovered. It retains the latest **100 turns** and supplies the latest **8** plus
up to **30 saved notes** as bounded background context. Tool output is not stored.
For facts you want to keep beyond recent history, use:

```text
/remember I prefer short explanations with Python examples.
/memory
/forget all
```

The web menu also has **View saved memory** and **Forget saved memory**. Starting a
new conversation clears the visible chat, not saved memory. `/forget all` clears
saved notes, saved turns, and the model's current chat context; future messages
start accumulating new memory. The forget menu asks you to confirm deletion.

Memory is shared across interfaces and the `--nxnx` preference for your OS user.
It lives in `~/.local/share/jarvis/memory/memory.sqlite3` with owner-only file
permissions, outside the repository. Set `JARVIS_MEMORY_DIR` to use another
private directory. Known credentials are redacted before storage; avoid putting
secrets in chat. Memory excerpts are sent to the selected AI provider as context.
The database is not encrypted at rest. Git ignores it, and the publication scanner
rejects tracked memory databases.

## Free custom voice

```bash
python3 scripts/install.py --voice
jarvis --test-voice
```

Default preset: **en-GB-RyanNeural**, rate **-5%**, pitch **-8Hz**. Change
`JARVIS_VOICE`, `JARVIS_VOICE_RATE`, and `JARVIS_VOICE_PITCH` in your local `.env`.
This is a customized preset, not a cloned voice. Edge TTS needs internet but no
API key or paid subscription. Its third-party service availability can change.

Install FFmpeg for `ffplay` playback. If online speech fails, JARVIS tries offline
pyttsx3. For always-offline speech output set `JARVIS_TTS_ENGINE=pyttsx3`; customize
`JARVIS_OFFLINE_VOICE` and `JARVIS_OFFLINE_RATE`. Linux needs the eSpeak library;
PyAudio needs PortAudio and Python development headers when built from source.
On Debian/Kali these typically come from `ffmpeg`, `libespeak1`, `portaudio19-dev`
and `python3-dev`.

Voice input uses Google's online recognizer, including wake-word recognition.
Say “jarvis,” wait for “Yes?”, then speak. Text and action results remain visible.
When approval mode is set to ask, tool confirmations are typed in the terminal.

Microphone input keeps one session open, calibrates once, and releases the device
when voice mode ends. Native ALSA/JACK device-probing warnings are suppressed only
while opening/enumerating devices; actual Python/audio failures remain visible.
If you need a different microphone, run `jarvis --list-microphones` and set
`JARVIS_MIC_INDEX` in `.env`. Set `JARVIS_AUDIO_DEBUG=1` to restore driver diagnostics.
This does not install a JACK server or repair a missing/disconnected microphone.

## Actions

| Action | Behavior |
| --- | --- |
| open_app | Launches an installed executable; `vscode` maps to `code`. |
| run_terminal | Confirms commands; reports exit status/stdout/stderr. Background mode reports a PID. |
| create_file | Creates a new UTF-8 file; does not overwrite. |
| read_file | Reads text up to 1 MB; common credential paths are blocked. |
| edit_file | Replaces one exact unique text match after confirmation; creates `.jarvis.bak`. |
| research | No-key metasearch with source links; explicitly labelled Wikipedia fallback. |
| render_3d | Starts the local viewer and opens the browser when needed. |
| connect_device | Android, Bluetooth and limited iOS actions described below. |
| list_skills | Reports installed dependencies and optional tool availability. |
| kali_tool | Runs a confirmed, installed command from the optional inventory. |

Terminal and Kali commands have a **3,830-second timeout (1 hour, 3 minutes, 50 seconds)**.
Set `JARVIS_TOOL_TIMEOUT` in `.env` to change it. API/device calls keep shorter
timeouts. Foreground output appears when the command finishes. In terminal mode, Ctrl+C interrupts waiting; a command may leave its own child processes running.
Background mode runs detached and has no automatic timeout.

Read the file before editing it. A second edit requires you to remove or rename the
previous backup; backups are never silently overwritten. Edits and terminal access
are powerful; the blacklist and path checks are not a sandbox.

The AI sees the **installed** optional tool names. The inventory includes package
names/aliases that may not be executable names on your OS. Missing tools are reported
clearly, not automatically installed. Use `jarvis --doctor` and install only tools
you need. Presence on PATH does not prove a tool is configured or tested.

## Devices and how to help test them

**Android:** install Google's [platform-tools](https://developer.android.com/tools/releases/platform-tools)
and put `adb` on PATH or set `JARVIS_ADB_PATH`. On Linux, a user install under
`~/.local/share/jarvis/platform-tools/adb` is detected automatically. Enable USB
debugging, connect USB, unlock the phone, and accept the authorization prompt.

Ask to scan Android devices, open an app by package name, open a dialer, or compose
an SMS. If several phones are connected, provide the device serial. Dial/SMS actions
**do not place calls or send messages automatically**; review and complete them on
the phone. We do not bypass phone permissions or lock screens.

**Bluetooth (Linux):** install BlueZ, start your system Bluetooth service, and enable
your adapter. Supported operations: status/list, timed scan, pair, connect, disconnect,
info and remove. Some pairing flows need confirmation in the desktop Bluetooth UI.
If the service is stopped, a user with administrator access can run
`sudo systemctl start bluetooth`. The app does not request or store your sudo password.

**iPhone (optional):** install libimobiledevice tools, connect USB and tap Trust.
Only device listing and basic product/OS information are exposed. App launching,
calling and SMS on iOS are not implemented. This is not full iPhone remote control.

Hardware tests require your actual connected and authorized devices. Mock tests
verify construction/validation of commands but cannot validate a phone or adapter.

## 3D viewer

Ask JARVIS to render a box, sphere or cone. It starts a local server at
http://127.0.0.1:8000 and opens the viewer. The assistant stops the server it owns
when it exits. For an independently running viewer:

```bash
.venv/bin/python render_server.py
```

Scene example: `{"shape":"sphere","color":"#00ff88","size":1}`.
The frontend downloads Three.js from a CDN on initial load. An occupied port 8000
or unavailable CDN is reported/visible rather than silently treated as success.

## Other providers and privacy

Set your own `GEMINI_API_KEY`, `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` in `.env`.
Gemini uses Google's OpenAI-compatible endpoint. Environment variables override
`.env`; model names can be changed with `JARVIS_GEMINI_MODEL`, `JARVIS_OPENAI_MODEL`,
`JARVIS_ANTHROPIC_MODEL` or `JARVIS_OLLAMA_MODEL`.

`.env`, private keys, generated audio, backups and virtual environments are ignored
by Git. A scanner checks tracked files and CI runs tests and secret checks. Known
credential values are redacted from provider-bound content, but no automated filter
can promise to detect every secret. See [SECURITY.md](SECURITY.md).

## Development

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m pip check
.venv/bin/python scripts/check_secrets.py
```

`requirements-lock.txt` records a tested Linux/Python 3.14 environment. For other
platforms start from `requirements.txt` and optionally `requirements-voice.txt`.
See [CONTRIBUTING.md](CONTRIBUTING.md) and [the implementation plan](docs/IMPLEMENTATION_PLAN.md).

Dependencies are not relicensed by this repository; each retains its own license.
