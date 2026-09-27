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
