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
random token for all API requests. It serves only three explicitly named static
files. Model text is inserted as text, never HTML. In ask mode, actions are stored server-side and can only be approved once by their
generated ID. Auto-approval is an explicit session setting, resets on restart, and
allows tools to act with your OS user permissions. Do not expose this service
through a tunnel, reverse proxy, or LAN bind. `--nxnx` is a preference, not an
authentication mechanism. Recent chat memory is stored locally in an owner-only SQLite database outside the
checkout; it is not encrypted. Known secrets are redacted. Memory excerpts go to
the selected provider with chat requests. Tab token storage is local.
