# Satellite Beta implementation plan

Baseline: stable main at 1e0059c; all 65 existing tests pass before edits.
Work branch: feature/satellite-beta. Do not merge this experiment into main.

1. Keep local web, voice, action dispatch, execution and saved PC chats unchanged.
   Add a lazy CLI entry and a context-local conversation-only brain option.
2. Add a separate FastAPI service on an explicitly chosen private IP and port 8766.
   HTTPS is required by default. A clearly named HTTP opt-in is available for
   trusted-LAN text trials. No wildcard/public bind, discovery or port forwarding.
3. Issue one-use, five-minute pairing codes with a ten-attempt global limit.
   Persist only hashes of strong device tokens, plus minimal metadata. Keep codes
   in process memory only. Add PC-only device listing/revocation commands.
4. Reuse brain.get_response, Session and MemoryStore, with separate Satellite data
   and per-device profiles. Never call PC dispatch. Every action (including
   research) is denied in this version, even if the model returns it.
5. Support up to eight paired devices, one model request at a time. Persist each
   device's bounded transcript and request IDs for safe reconnect/retry. Refuse
   concurrent requests and mark interrupted work without replaying it.
6. Use a small plain HTML/CSS/JS TV page with polling. Browser dictation and speech
   playback are optional, manually enabled, and failure falls back to text. No
   uploaded audio or PC microphone/TTS coupling.
7. Validate security, startup failures, concurrent requests, restart/revocation,
   missing dependencies, browser fallbacks and all existing regression tests.
   Run both repository secret checks and Gitleaks before publishing the branch.

Planned commit boundaries: plan; isolated backend/CLI and security tests; TV UI;
final documentation and complete validation. No new runtime dependencies expected:
FastAPI/Uvicorn already exist; additional mechanisms use the Python standard library.
