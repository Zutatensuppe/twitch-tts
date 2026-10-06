# Testing the Updater

The automated tests (`uv run python -m unittest discover -s tests`) cover
checking, downloading and applying an update, including over real HTTP against
the Fake Release Server. They can't cover what only happens with a real
PyInstaller build on Windows: replacing a running exe and restarting into the
new one. Past Updater bugs (#7, #8) were exactly there, so do this manual check
before releasing changes that touch the Updater or app startup.

The setup: the Fake Release Server runs on the Linux dev machine, and the app runs
in a Windows VM (QEMU/libvirt) that talks to it.

## 1. Get a Release Zip of your changes

1. Push your branch.
2. On GitHub: **Actions → Release Build → Run workflow**, pick your branch.
3. When it's done, download the `twitch-tts-build` artifact from the run page.
   It's a zip with `tts.exe`, `tts-gui.exe` and `config.jsonc` at the top level,
   which is the same layout as a Release Zip.

## 2. Serve it

```shell
uv run python tests/fake_release_server.py --zip ~/Downloads/twitch-tts-build.zip
```

The server advertises version `99.0.0`, so any real release looks outdated
next to it.

## 3. Start an older release in the VM

1. Download an older release from GitHub (1.3.3 or later, since older ones have
   no Updater) and unzip it into a fresh folder.
2. Fill in `config.jsonc` so the bot can actually start.
3. In `cmd`, from that folder:

   ```bat
   set TTS_UPDATE_URL=http://192.168.122.1:8099/releases/latest
   tts-gui.exe
   ```

   `192.168.122.1` is the host as seen from a VM on libvirt's default network.
   When running on Windows directly, use `localhost` instead. If the VM can't
   reach the server, check the host firewall for port 8099.

4. Wait for the Startup Check prompt, or use **Help → Check for Updates…**, and
   accept the update.

## 4. Check

- [ ] The app restarts by itself and the window title shows the new version.
- [ ] **Start the bot and let it read a chat message aloud.** This makes HTTPS
      calls from the restarted process, which is what broke in #7/#8.
- [ ] `tts.exe.old` and `tts-gui.exe.old` are gone, at the latest after
      launching `tts-gui.exe` once more.
- [ ] `tts.exe` started directly still runs.

Because the build you served isn't really version 99.0.0, the Startup Check will
offer the "update" again after the restart. Click **No**.
