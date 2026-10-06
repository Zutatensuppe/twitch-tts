"""Updater against a real HTTP server: check -> download -> apply over the wire."""

import io
import os
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from twitch_tts import updater

import fake_release_server


def _make_release_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


class UpdaterIntegrationTests(unittest.TestCase):
    def _serve(self, version: str, zip_data: bytes = b"") -> None:
        """Start a Fake Release Server and point the Updater at it."""
        server = fake_release_server.start_in_background(zip_data, version)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        patcher = patch.object(updater, "GITHUB_API_LATEST", server.latest_release_url)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_newer_release_is_downloaded_and_applied(self):
        self._serve("2.0.0", _make_release_zip({
            "tts.exe": b"new-tts",
            "tts-gui.exe": b"new-gui",
            "config.jsonc": b"{}",
        }))

        with tempfile.TemporaryDirectory() as app_dir:
            for name in ("tts.exe", "tts-gui.exe"):
                with open(os.path.join(app_dir, name), "wb") as f:
                    f.write(b"old-" + name.encode())

            info = updater.check_for_update("1.0.0")
            self.assertIsNotNone(info)
            self.assertEqual(info["version"], "2.0.0")

            zip_path = updater.download_update(info["asset_url"])
            updated = updater.apply_update(zip_path, app_dir=app_dir)
            updater.cleanup_download(zip_path)

            self.assertEqual(sorted(updated), ["tts-gui.exe", "tts.exe"])
            with open(os.path.join(app_dir, "tts.exe"), "rb") as f:
                self.assertEqual(f.read(), b"new-tts")
            with open(os.path.join(app_dir, "tts-gui.exe"), "rb") as f:
                self.assertEqual(f.read(), b"new-gui")
            with open(os.path.join(app_dir, "tts.exe.old"), "rb") as f:
                self.assertEqual(f.read(), b"old-tts.exe")
            # config is never overwritten by an update
            self.assertFalse(os.path.exists(os.path.join(app_dir, "config.jsonc")))
            self.assertFalse(os.path.exists(zip_path))
            self.assertFalse(os.path.isdir(os.path.dirname(zip_path)))

    def test_same_version_means_no_update(self):
        self._serve("1.0.0")

        self.assertIsNone(updater.check_for_update("1.0.0"))


if __name__ == "__main__":
    unittest.main()
