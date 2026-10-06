# twitch-tts

Reads Twitch (and YouTube) chat aloud, optionally translated, as a Windows desktop app with a GUI and a CLI.

## Updating

**Updater**:
The feature that brings an installed copy up to the latest Release: check, download, apply, restart. Covers both the Startup Check and the Manual Check.
_Avoid_: auto updater, self-update

**Startup Check**:
The update check the GUI performs on its own shortly after launch, when enabled in the settings.
_Avoid_: auto check, auto update

**Manual Check**:
The update check the user triggers via "Help → Check for Updates…".

**Release Zip**:
The zip attached to a GitHub release, containing `tts.exe`, `tts-gui.exe` and an example config.
_Avoid_: update package, asset

**Fake Release Server**:
A stand-in for GitHub's "latest release" endpoint that advertises a chosen version and serves a chosen Release Zip; used only for testing the Updater.
_Avoid_: mock server, update server
