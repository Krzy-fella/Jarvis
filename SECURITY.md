# Security and privacy

Never publish `.env`, tokens, private keys or your Ollama authentication files.
Use `.env.example` only for empty values and non-secret defaults. Rotate any key
that has appeared in a public post, chat, commit or log; deleting a file does not
revoke its credentials.

This assistant can run commands with your account's permissions after confirmation.
Its blacklist is not a sandbox. Review command arguments and targets carefully.
Use security tools only on systems where you have authorization.

API conversations go to the provider you choose. Edge speech sends response text
to Microsoft's online service; Google recognition sends microphone audio to its
speech service, including wake-word detection. Use pyttsx3 for offline speech
output. Ollama cloud is online; this project does not download model weights.

Known-secret redaction is best effort, not a guarantee against every secret format.
The file actions block common credential paths, but terminal commands and arbitrary
files can still expose sensitive information. Do not ask the assistant to process
secrets. Inspect staged files and run the secret scanner before publishing.

Do not post live credentials in an issue. For a vulnerability, use GitHub private
vulnerability reporting if available; otherwise contact the repository owner
without including a working secret or sensitive exploit payload.

## Local web interface

The web server is loopback-only, validates Host/Origin, and requires a per-launch
random token for all API requests. It serves only four explicitly named static
files. Model text is inserted as text, never HTML. In ask mode, actions are stored server-side and can only be approved once by their
generated ID. Auto-approval is an explicit session setting, resets on restart, and
allows tools to act with your OS user permissions. Do not expose this service
through a tunnel, reverse proxy, or LAN bind. `--nxnx` is a preference, not an
authentication mechanism. Recent chat memory is stored locally in an owner-only SQLite database outside the
checkout; it is not encrypted. Known secrets are redacted. Memory excerpts go to
the selected provider with chat requests. Tab token storage is local.

Saved web chats use the same private database and retain their transcripts,
including tool results, until deleted. Known credentials are redacted before
storage. Deleting a chat also removes its linked recent-memory turns, but not
explicit saved notes. The general-memory forget command does not remove saved
sidebar chats. Restoring a chat never replays interrupted tool actions.

## Satellite Beta boundary

Satellite is a separate, explicitly enabled process and FastAPI application, not a
LAN bind of `web_chat.py`. The normal web API, approval endpoints, action dispatcher,
files and execution monitor are not mounted in it. `satellite/permissions.py`
accepts only a `none` action. All named, malformed and future actions are rejected;
there is no dispatcher call. A conversation-only brain prompt adds guidance but is
not the security boundary. `--nxnx` and session auto-approval confer no TV powers.

Both `JARVIS_SATELLITE_ENABLED=true` and `--mode satellite` are required. The default
bind is loopback. LAN use requires a specific private IP; wildcard/public/link-local
binds, the existing default PC ports, and overlapping PC-memory storage are refused.
HTTPS certificates are required unless the operator explicitly selects insecure
HTTP. HTTP exposes both conversation content and reusable credentials. Do not use
port forwarding, public tunnels or untrusted networks. No firewall is changed by
this feature. TLS termination proxies and host aliases are not supported in beta.

Pairing uses a six-digit code, a salted in-memory hash, a five-minute lifetime,
ten guesses per issued code, and atomic single use. Its one-time display in the
PC terminal is intentional; do not record/share that terminal. The server never
returns the code in HTTP responses or access logs. Successful pairing returns a
256-bit random bearer secret once; only its SHA-256 digest is stored. Comparisons
use `secrets.compare_digest`. Credentials expire after 90 days and can be revoked
from the PC CLI. The six-digit code is never a long-term credential.

The browser defaults to session storage, or local storage when the user explicitly
chooses Remember. This is bearer authentication, not hardware identity: anyone
with the browser profile or token can impersonate that device and read its chat.
Disconnect clears that browser's credential; **revoke on the PC** to invalidate a
lost device. No provider keys, environment/configuration endpoint or credentials
of other devices are sent to the client. Text is rendered with `textContent`, with
self-only scripts/styles, no CDN, a CSP, no caching, no framing and no referrers.

Host and Origin must match the configured IP/scheme/port exactly; POST requires
Origin, foreign origins and ambiguous headers are refused, and proxy headers are
not trusted. Bodies are limited to 8 KiB before parsing, including chunked input,
with a five-second body deadline. Schemas reject extra fields, messages exceeding
4,000 characters are rejected, audio/compression/uploads/WebSockets are unavailable.
Per-IP/global traffic, bad credentials and per-device messages are rate limited.
Only one model request runs at a time; the existing provider timeouts still apply.

Credentials, transcripts and device-specific memory are stored under
`~/.local/share/jarvis/satellite/` outside the checkout. The directory and databases
have owner-only permissions on POSIX; verify equivalent ACLs on other platforms.
Device histories never load PC memory. Stored content is redacted on a best-effort
basis, **not encrypted at rest**. Chat text and device memory go to the selected AI
provider. Browser recognition may send audio to the browser's speech service; its
privacy/availability is independent of JARVIS. No audio is uploaded to this server.

This is application/process isolation, not an OS security sandbox or a guarantee
against machine-wide failures. Satellite and normal JARVIS share an OS account,
hardware and provider quotas. A compromised host, disk exhaustion, OS failure or
provider outage can affect both. Review/test the feature before wider deployment;
see the beta guide for constraints and prerequisites for future PC control.

## October 2026 review changes

Normal web chat now bounds HTTP request bodies to 128 KiB before parsing, rejects
ambiguous authority/authentication headers, compressed bodies and non-JSON POST
bodies. The 3D viewer also validates local Host and Origin, including WebSocket
handshakes, to block cross-origin access and DNS rebinding. Same-account local
processes can still access the viewer; it does not execute commands or serve private
files. Loopback services are not multi-user security boundaries.

TV start/stop administration exists only in the authenticated loopback PC API and
terminal menu. Starting explicitly opts in for this session. It launches the
restricted server in a child process; it never publishes the PC tool API to LAN.
Pairing codes stay in process memory and are returned only to the authenticated PC
panel. UI HTTPS setup does not offer insecure LAN binding; PC preview is loopback.

Only a complete provider JSON envelope (optionally fenced) can request an action.
JSON examples embedded in prose are display-only. Special-file reads are rejected;
regular reads are bounded even when files grow. Foreground commands use bounded
output collection in all interfaces, and POSIX timeout/interruption kills the
foreground process group. Explicit detached/background work remains separate.
These protections do not turn shell execution or auto-approval into a sandbox.
