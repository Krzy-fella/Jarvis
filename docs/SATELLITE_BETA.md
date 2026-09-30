# JARVIS Satellite / TV Mode — experimental beta

Satellite lets a browser on your private home network use JARVIS as a conversational
assistant. It does not run JARVIS on the TV, install a TV app, or control your PC.
Keep the beta on `feature/satellite-beta` until reviewed and tested on real devices.

## Architecture and isolation

```text
TV browser: text / optional browser recognition / browser speech
        │ HTTPS: pair, send message, poll state
        ▼
Dedicated Satellite process — explicit IP, port 8766
        │ Host/Origin/body/rate checks → device authentication
        ▼
Device conversation → existing Session + separate MemoryStore
        │ existing brain.get_response(conversation_only=True)
        ▼
Selected AI provider → server permission check → text reply

Separate normal process: terminal / voice / 127.0.0.1:8765 PC web
                        existing approvals/actions/execution
```

There are no Satellite imports during normal CLI startup. Satellite imports web
packages only when explicitly launched; the flag alone starts nothing. Its entry
point catches startup errors, including Uvicorn startup exits, and identifies them
as beta failures. A port/certificate/bind/dependency failure exits the standalone
Satellite command with status 1; it does not stop another normal JARVIS process.
Existing voice, actions, execution, memory and chat-store behavior is unchanged.
The local web server only gains an explicit shared keyboard-history asset route
for the separately requested Up/Down message recall feature.
The same provider routing is reused; no second AI implementation or model download.

The additive brain flag uses ContextVars, so a Satellite conversation-only prompt
cannot leak into simultaneous normal requests. Security does not depend on the
prompt: `conversation_reply` allows only `action.tool == "none"`, and Satellite
has no reference to the PC dispatcher. Memory slash commands are narrowly handled
by the existing Session against a device-specific database/profile.

## Install and enable

Requires Python 3.11+ and the existing project dependencies. No new Satellite-only
package, frontend build, or PC voice installation is needed. For a fresh checkout:

```bash
git clone --branch feature/satellite-beta https://github.com/Krzy-fella/Jarvis.git
cd Jarvis
python3 scripts/install.py
```

For an existing virtual environment, the exact dependency command is:

```bash
.venv/bin/python -m pip install -r requirements.txt
```

On Windows use `.venv\Scripts\python.exe` in place of `.venv/bin/python` and run
`main.py` directly if no launcher is installed. Existing requirements include
FastAPI, Uvicorn and Pydantic (via FastAPI); HTTPX comes through the provider SDK.
No additional runtime requirements file was introduced.

The following Linux/macOS command previews the interface **on the PC only**:

```bash
JARVIS_SATELLITE_ENABLED=true jarvis --mode satellite --satellite-insecure-http
```

Open `http://127.0.0.1:8766`. This does not expose the service to your TV. The explicit
HTTP flag is for testing; secure transport is the default. In PowerShell set
`$env:JARVIS_SATELLITE_ENABLED="true"`, then invoke the Python command with the same
arguments. You may set the flag in your private `.env`, but still must select the
Satellite mode each time. Set it to `false` to disable server launches.

## Connect a TV using HTTPS

1. Put the PC and TV on the same private LAN. Keep normal JARVIS in another terminal
   if desired. Cloud providers still require internet.
2. Identify the PC's correct private LAN IP in network settings or `ip -brief address`
   on Linux. There is deliberately no automatic choice among Wi-Fi, Ethernet and VPN
   interfaces. Example below: `192.168.1.25`; replace it with **your PC's** address.
3. Obtain a TLS certificate and its matching private key. The certificate must have
   an IP subject alternative name matching the chosen address and be trusted by the
   TV/browser. A local CA is suitable only where you can install its trust certificate.
   Keep the key outside the repository with owner-only permissions. Many TV browsers
   cannot install a local CA; use another browser/device in that case. Do not solve
   certificate failures by disabling browser certificate verification.
4. Start the separate service:

   ```bash
   JARVIS_SATELLITE_ENABLED=true jarvis --mode satellite \
     --satellite-host 192.168.1.25 \
     --satellite-cert /absolute/path/to/satellite.crt \
     --satellite-key /absolute/path/to/satellite.key
   ```

   Equivalent without the launcher:

   ```bash
   JARVIS_SATELLITE_ENABLED=true .venv/bin/python main.py --mode satellite \
     --satellite-host 192.168.1.25 \
     --satellite-cert /absolute/path/to/satellite.crt \
     --satellite-key /absolute/path/to/satellite.key
   ```

5. Open the **exact printed URL**, including port, on the TV. Name the device and
   enter the six-digit code shown on the PC. The code works once, expires after five
   minutes, and allows at most ten guesses. Restart Satellite for a fresh code.
6. Choose Remember only on a trusted browser profile. Without it, tab/session storage
   holds the credential; browser session restoration can sometimes retain it.
7. Send text. Replies appear in the TV chat; reload/reconnect restores this device's
   recent conversation. Ctrl+C in the Satellite terminal stops only this service.

For a short **trusted-LAN text-only trial** when TLS setup is not yet possible:

```bash
JARVIS_SATELLITE_ENABLED=true jarvis --mode satellite \
  --satellite-host 192.168.1.25 --satellite-insecure-http
```

This explicitly weakens transport security: network observers can steal reusable
credentials and read chats. Do not use it on public/shared/untrusted networks.
Browser microphone support normally requires trusted HTTPS. The server does not
change your firewall, start automatically, open a router port or create a tunnel.
If your firewall blocks it, allow only the chosen TCP port from your trusted LAN
through your OS firewall UI. Never expose the normal private PC web service.

Settings: `JARVIS_SATELLITE_ENABLED`, `JARVIS_SATELLITE_HOST`,
`JARVIS_SATELLITE_PORT`, `JARVIS_SATELLITE_DIR`, `JARVIS_SATELLITE_CERT`,
`JARVIS_SATELLITE_KEY`. Explicit CLI address/port/certificate options override env.
`--provider ollama|gemini|openai|anthropic` chooses the existing configured provider;
Ollama remains the default. `--satellite-insecure-http` is intentionally CLI-only.
Do not combine HTTP with configured certificate/key settings.

## Pairing and credentials

The code is salted/hashed in RAM and consumed atomically. It is displayed once for
the operator; no request/access log contains it. Do not record the pairing terminal.
Pairing returns a random device ID and an independent 256-bit secret as a bearer
credential. Only SHA-256 of that credential is saved in the owner-only database.
It expires after 90 days, persists over server restarts, and never grants PC access.
A maximum of eight non-revoked, unexpired devices can pair.

```bash
jarvis --satellite-devices
jarvis --satellite-revoke DEVICE_ID
```

These are local PC commands, also available when the server feature flag is off.
Use the printed full device ID. Revocation prevents new API calls and delivery of
an in-flight reply. It does not delete history or cancel an already-sent provider
request. A lost response during pairing can consume a code without delivering a
credential: list/revoke that orphan device and restart Satellite to pair again.
Disconnect this browser clears its local credential; PC revocation is still needed
for a lost/copied credential. Do not send tokens in URLs or share browser profiles.

## Permissions and memory

Allowed: text conversation, this device's memory, optional browser speech.
Blocked: terminal, application launching, file create/read/edit, Kali/security
commands, Android/iOS/Bluetooth control, 3D rendering, skill inventory, web research,
and every future/unknown action. PC control is deliberately disabled. Neither
`--nxnx`, auto-approval nor a request claiming to be the owner overrides this.
The beta cannot fetch live news; model knowledge alone may be stale.

Data lives in `~/.local/share/jarvis/satellite/`:

- `devices.sqlite3`: device metadata, hashed credentials, bounded transcripts,
  internal model histories and retry identifiers.
- `memory/memory.sqlite3`: existing MemoryStore with a separate profile per device.
- `server.lock`: prevents two servers using the same directory simultaneously.

This is separate from `~/.local/share/jarvis/memory/` and existing saved PC chats.
Overlapping paths are rejected. The beta never imports private PC memory into a TV
conversation. Each device has one ongoing thread with up to 80 visible messages,
40 model-context messages, and the normal bounded memory (100 turns / 30 notes).
Only this device's context is sent to the configured AI provider.

`/remember something` saves a note; `/memory` displays this device's memory;
`/forget all` clears its notes, stored general-memory turns and active model context.
It **does not delete the visible transcript**. Beta has no chat sidebar/delete UI.
Revoked histories remain on disk. To erase all Satellite data, stop the server,
inspect/back up its dedicated directory, then remove that directory through your
file manager; this invalidates all devices. Never remove the PC memory directory.
Databases are owner-only on POSIX but not encrypted. Redaction is best effort.

## Concurrency, reconnection and failure handling

One provider request can run at a time across all paired Satellite devices; a second
receives a friendly busy response. PC interfaces have their own processes and locks.
The browser polls state every 1.5 seconds, backing off to 15 seconds after failures.
No WebSockets, streaming audio, audio uploads or extra ports are used.

Each message has a client request ID. The last 100 IDs per device are stored with a
text hash to prevent duplicate submissions after a lost HTTP response. Retries with
a changed message and the same ID are refused. The UI retains an uncertain request
ID while the page stays open and lets you retry; it never automatically resends
messages. Reload restores accepted messages, but an unsent draft may be lost.
Retries older than the retained 100 IDs are not deduplicated.

On server restart an unfinished request is marked interrupted and is never replayed.
Provider errors are sanitized; no exception contents/prompts/secrets go to clients
or Satellite logs. Existing model request timeouts/retries still apply (a response
can take several minutes). Stopping the process may abandon an in-flight cloud
request; it cannot cancel work already accepted by that provider. Resources/provider
quotas still share the same host, so this is not protection from machine-wide failure.

## Optional voice and TV compatibility

The browser performs speech recognition when available in a secure context. It does
not stream microphone audio to the PC. Recognition populates the draft; the user
reviews it and presses Send. Microphone denial, missing hardware, unsupported APIs,
and recognition errors leave text chat available. No continuous listening/wake word.
Some TV remotes route microphones only to their OS assistant, not the browser.

Read latest reply uses browser SpeechSynthesis after a user gesture, through that
device's speakers. Voices depend on the TV/browser/OS; the PC Ryan voice preset is
not used here. Missing/failed synthesis leaves the reply visible. Browser recognition
may send audio to its vendor, and some synthesis voices may use network services.
See [MDN SpeechRecognition](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition)
and [SpeechSynthesis](https://developer.mozilla.org/en-US/docs/Web/API/Window/speechSynthesis).

Expected text baseline: recent Chromium/Chrome/Edge, Firefox and Safari with current
JavaScript, Fetch, AbortController and Web Crypto. This is not a tested guarantee
for every browser or TV. Speech recognition support is much narrower. Old TV engines
may fail to parse modern JavaScript; use an updated browser or another device.
Full screen and glass effects are progressive; their absence does not affect text.
Tab/Shift+Tab and Up/Down outside editable fields navigate controls; Enter activates.
A keyboard may be needed on TV browsers with poor remote text input.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Disabled by default | Set the flag to true **and** choose `--mode satellite`. |
| Cannot bind | Choose an IP assigned to this PC and a free port; 8000/8765 are reserved. Try `--satellite-port 8767`. |
| Another server uses this data | Stop the other Satellite process. Do not remove a live lock file to bypass it. |
| TV cannot connect | Exact private IP/port, same LAN, PC awake, firewall and Wi-Fi client isolation. Loopback is PC-only. |
| Several network adapters | Select the private interface shared with the TV. No automatic discovery or wildcard binding. |
| HTTPS error | Matching certificate/key, trusted issuing CA, IP SAN, correct device clock. Do not bypass verification. |
| Invalid host/origin | Use exactly the printed URL. DNS aliases, proxies, forwarded hosts and alternate schemes are rejected. |
| IPv6 trouble | Use canonical loopback/ULA IPv6 with bracketed URL, or private IPv4. Link-local scopes and public IPv6 are not supported. |
| Pairing unavailable | Expired, exhausted or used code: restart Satellite. Existing devices stay paired. |
| Pairing succeeded but page lost it | List/revoke the orphan device, restart and pair again. Allow browser storage. |
| Too many devices | Revoke an unused device on the PC. |
| Too many requests | Wait one minute; only six new messages per device per minute. |
| Another message is running | Wait for it to complete. Only one Satellite request runs at once. |
| Provider error | Check normal provider configuration/sign-in and connectivity. No API key belongs in the TV UI. |
| Storage error | Check disk space and dedicated-directory permissions; normal PC data is separate. |
| No microphone/speech | Expected on some TVs. Use text; trusted HTTPS and browser permissions may enable recognition. |
| Missing dependency | Run the existing requirements install with the same interpreter. Normal text does not import Satellite packages. |

## Files and why they changed

Added:

| File | Purpose |
| --- | --- |
| `satellite/__init__.py` | Lightweight beta exception/package boundary. |
| `satellite/settings.py` | Explicit enablement, safe bind/transport/storage validation. |
| `satellite/cli.py` | Isolated startup, certificate/bind handling, process lock and local device management. |
| `satellite/pairing.py` | One-use expiring code with attempt limits. |
| `satellite/storage.py` | Private credential hashes, device metadata and durable state/retry IDs. |
| `satellite/models.py` | Strict input schemas and text/identifier limits. |
| `satellite/permissions.py` | Immutable capabilities and server-side deny-by-default action gate. |
| `satellite/sessions.py` | Bounded serialized requests, device memory, reconnect and failure recovery. |
| `satellite/server.py` | Dedicated restricted API, request guard and five explicit static assets. |
| `web/satellite/index.html` | Accessible pairing/chat/fullscreen controls. |
| `web/satellite/style.css` | Large TV-friendly dark glass presentation and focus states. |
| `web/satellite/app.js` | Pairing, browser credentials, safe text rendering, polling and retry UX. |
| `web/satellite/voice.js` | Optional isolated speech adapter with text fallbacks. |
| `web/input-history.js` | Shared draft-preserving Up/Down message recall, scoped to the active conversation. |
| `tests/test_input_history.py` | Terminal PTY, redaction/bounds/fallback and web keyboard regression tests. |
| `tests/input_history_test.js` | Actual shared history helper tested for drafts, chat scope and multiline editing. |
| `tests/test_satellite.py` | Startup, permission, authentication, memory, concurrency and regression tests. |
| `tests/satellite_voice_test.js` | Execute real speech adapter against absent/failed browser APIs. |
| `docs/SATELLITE_PLAN.md` | Baseline inspection, architecture and staged implementation plan. |
| `docs/SATELLITE_BETA.md` | Setup, security, limitations and implementation report. |

Modified:

| File | Why |
| --- | --- |
| `main.py` | Add explicit Satellite/admin CLI routing before PC session creation; preserve normal modes and return error status. |
| `brain.py` | Add request-scoped conversation-only prompt without PC tools/owner privileges; keep existing providers and defaults. |
| `.env.example` | Document disabled beta defaults and optional private settings. |
| `terminal_ui.py` | Add bounded process-local readline message recall, excluding menu/approval input. |
| `web/app.js` | Hook recall into the current saved chat and reset it after send/switch. |
| `web/index.html` | Load the shared keyboard helper before normal chat code. |
| `web_chat.py` | Serve only the new named keyboard asset; keep loopback/auth/action behavior unchanged. |
| `README.md` | Add discoverable beta setup/limitations and link this guide. |
| `SECURITY.md` | Document distinct LAN threat model and actual enforcement/transport/storage limits. |

No changes to normal `voice.py`, `actions.py`, `execution.py`,
`session.py`, `memory.py`, `chat_store.py`, `config.py`, requirements or existing tests.

## Validation

Baseline before changes: **65 existing tests passed**. The expanded suite currently
has **102 passing tests**, including 32 Satellite tests and five keyboard-history tests. It covers normal import/text
startup without Satellite/web packages, original action dispatch and local web app,
explicit enablement, bind/lock/dependency/certificate failures, authentication,
pairing limits, strict input/oversize/chunked/audio rejection, Host/Origin checks,
all current and future tool denial, prompt context isolation, per-device memory,
revocation, persistence, deduplication, concurrency, storage failures and interrupted
requests. Browser speech absence, microphone failure and TTS failure run against the
real speech adapter with synthetic APIs. Node is development-only; that adapter test
is skipped with an explicit reason when Node is absent.

Run:

```bash
.venv/bin/python -m unittest discover -s tests -v
node tests/satellite_voice_test.js
.venv/bin/python -m pip check
.venv/bin/python scripts/check_secrets.py
```

A real Ollama cloud reply passed through the paired Satellite API using disposable
state. Chromium pairing and chat were exercised with a deterministic provider fixture;
terminal Up/Down and draft restoration passed through a real pseudo-terminal.
A real HTTPS CLI launch also passed certificate verification, pairing and authenticated
state retrieval using a disposable test certificate/data directory. Normal web
Up/Down recall, draft restoration, reload persistence and new-chat separation passed
in Chromium. No JavaScript errors were reported during those flows. TV-specific
microphone/speaker behavior has not been hardware-verified.

The final local suite passed 102 tests on Python 3.14; `pip check` found no broken
requirements. The built-in scanner found zero issues in 65 tracked source files;
Gitleaks found no leaks in the public-source export or the seven implementation
commits inspected. No private environment, credential, certificate, history database
or generated audio was included in the export. Actual TV microphones, remote controls, speakers, LAN
firewalls and client certificate trust still require testing on your hardware.

## Before any future remote PC control

Do not just flip a capability boolean. Keep conversation as the default and design
a separate reviewed, typed action gateway. Candidate tiers `satellite_chat`,
`satellite_safe_control`, `satellite_full_control` are a roadmap, not implemented
roles. Before enabling even a small safe-control tier:

1. Require trusted TLS and stronger operator-authenticated device enrollment.
2. Define a tiny action allowlist with strict argument/target validation and explicit
   per-device grants stored only by a local authenticated administration flow.
3. Require fresh PC-side approval for effects; never inherit global auto-approval or
   trust an LLM, device name, owner flag or chat claim as authorization.
4. Add bounded jobs, cancellation, audit records with secret redaction, replay
   protection, revocation during jobs and clear UI showing the exact proposed action.
5. Put execution behind a least-privilege process/OS boundary, not the current PC
   assistant's unrestricted OS account.
6. Add adversarial permission tests, review by another maintainer and real multi-device
   testing. Treat arbitrary terminal/full-control access as a separate security design.


## Up / Down input recall

The follow-up keyboard feature applies to terminal chat, normal PC web chat and
Satellite. Web history is derived only from the current conversation's user messages;
restoring a chat restores recall. Up on the first input line starts browsing; repeated
Up/Down navigates, and Down beyond newest restores the draft. Editing resets recall.
Multiline cursor movement, selected text, composition and modified arrow keys remain
available. Nothing sends or executes until you explicitly submit the message.
Terminal history is process-local, capped at 100 and redacted, with no new disk file.
