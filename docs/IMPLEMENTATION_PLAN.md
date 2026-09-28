# Implementation plan and acceptance checks

1. Complete file reading/editing, Android and Bluetooth actions; expose limited
   optional iPhone listing/info. Test invalid inputs, ambiguous devices, and remote
   shell quoting. Calls/SMS must open phone UI for the user to complete.
2. Replace fake/fragile research with no-key metasearch and a labelled Wikipedia
   fallback. Verify actual source URLs and honest failure responses.
3. Start the viewer on demand, retain scenes for newly connected browsers, and
   show a working browser view. Validate scene inputs and server identity.
4. Supply the model with installed optional tool names and add `jarvis --doctor`.
   Missing OS executables remain optional: do not bulk-install hundreds of unrelated
   security tools or mistake a package name for a valid executable.
5. Add a configurable British voice using Edge TTS, with offline pyttsx3 fallback
   and `jarvis --test-voice`. Generate a real sample without paid APIs/model weights.
6. Create an independent public repository with MIT licensing, portable setup,
   contributor guidance and CI. Exclude secrets, scan tracked files/history and
   compare against local credential values before uploading.

Hardware acceptance requires a USB-authorized phone and an active Bluetooth
service/adapter. Tests using mocks verify command construction, not real hardware.
Optional iOS functionality requires a trusted USB connection and libimobiledevice;
Android-style app/call/SMS control is outside that limited implementation.

## Web and voice follow-up

- Implemented: default online web launch, terminal/web menu, glass-style local UI.
- Implemented: readable response envelope handling and tool output.
- Implemented: per-launch API token, origin/host checks, single-use tool approvals, background execution.
- Implemented: Nxnx owner preference profile without removing confirmations.
- Implemented: persistent microphone session, scoped driver log suppression, microphone selection.
- Figma draft exists; canvas design is blocked by the Starter-plan MCP tool limit.
- Spoken wake-word accuracy, Bluetooth pairing, and authorized Android hardware actions still need user participation.

## Session approvals and persistent memory

- Implemented both requested approval choices in terminal/web menus. Ask is the default; auto approval is process-local and never persisted.
- Implemented owner-only SQLite memory outside the checkout, recent-turn retention, pinned notes, and view/forget controls.
- Memory is shared across terminal, web, voice, and the Nxnx preference. Known credentials are redacted and memory databases are ignored/rejected by publication checks.
- Tests cover persistence after reopening, retention, forgetting, credential redaction, provider context, automatic action execution, and approval reset.
