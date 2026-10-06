import io
import json
import os
import tempfile
import unittest
import zipfile
from unittest.mock import MagicMock, patch, call

from twitch_tts import updater


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_github_release_response(
    tag_name: str = "v2.0.0",
    zip_asset_name: str = "twitch-tts-2.0.0.zip",
    zip_asset_url: str = "https://example.com/twitch-tts-2.0.0.zip",
    html_url: str = "https://github.com/Zutatensuppe/twitch-tts/releases/tag/v2.0.0",
    extra_assets: list | None = None,
) -> dict:
    assets = [{"name": zip_asset_name, "browser_download_url": zip_asset_url}]
    if extra_assets:
        assets.extend(extra_assets)
    return {
        "tag_name": tag_name,
        "html_url": html_url,
        "assets": assets,
    }


def _make_release_zip(files: dict[str, bytes]) -> bytes:
    """Create an in-memory zip with the given {name: content} entries."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _mock_urlopen_for_json(data: dict):
    """Return a context-manager mock whose .read() returns JSON bytes."""
    body = json.dumps(data).encode("utf-8")
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ---------------------------------------------------------------------------
# _parse_version
# ---------------------------------------------------------------------------

class TestParseVersion(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(updater._parse_version("1.2.3"), (1, 2, 3))

    def test_with_v_prefix(self):
        self.assertEqual(updater._parse_version("v1.2.3"), (1, 2, 3))

    def test_two_part(self):
        self.assertEqual(updater._parse_version("2.0"), (2, 0))

    def test_single_number(self):
        self.assertEqual(updater._parse_version("7"), (7,))

    def test_leading_whitespace(self):
        self.assertEqual(updater._parse_version("  v3.1.0"), (3, 1, 0))

    def test_trailing_text(self):
        self.assertEqual(updater._parse_version("v1.0.0-beta"), (1, 0, 0))

    def test_invalid_returns_none(self):
        self.assertIsNone(updater._parse_version("not-a-version"))

    def test_empty_string(self):
        self.assertIsNone(updater._parse_version(""))


# ---------------------------------------------------------------------------
# _find_in_zip
# ---------------------------------------------------------------------------

class TestFindInZip(unittest.TestCase):
    def test_root_level(self):
        names = ["tts.exe", "tts-gui.exe", "README.md"]
        self.assertEqual(updater._find_in_zip(names, "tts.exe"), "tts.exe")

    def test_nested_one_level(self):
        names = ["twitch-tts/tts.exe", "twitch-tts/tts-gui.exe"]
        self.assertEqual(updater._find_in_zip(names, "tts.exe"), "twitch-tts/tts.exe")

    def test_not_found(self):
        names = ["other.exe"]
        self.assertIsNone(updater._find_in_zip(names, "tts.exe"))

    def test_empty_list(self):
        self.assertIsNone(updater._find_in_zip([], "tts.exe"))


# ---------------------------------------------------------------------------
# check_for_update
# ---------------------------------------------------------------------------

class TestCheckForUpdate(unittest.TestCase):
    def _patch_urlopen(self, data: dict):
        resp = _mock_urlopen_for_json(data)
        return patch("twitch_tts.updater.request.urlopen", return_value=resp)

    def test_newer_version_returns_info(self):
        release = _make_github_release_response(tag_name="v2.0.0")
        with self._patch_urlopen(release):
            result = updater.check_for_update("1.0.0")
        self.assertIsNotNone(result)
        self.assertEqual(result["tag_name"], "v2.0.0")
        self.assertEqual(result["version"], "2.0.0")
        self.assertEqual(result["asset_url"], "https://example.com/twitch-tts-2.0.0.zip")

    def test_same_version_returns_none(self):
        release = _make_github_release_response(tag_name="v1.0.0")
        with self._patch_urlopen(release):
            self.assertIsNone(updater.check_for_update("1.0.0"))

    def test_older_remote_returns_none(self):
        release = _make_github_release_response(tag_name="v0.9.0")
        with self._patch_urlopen(release):
            self.assertIsNone(updater.check_for_update("1.0.0"))

    def test_unparseable_current_version_returns_none(self):
        self.assertIsNone(updater.check_for_update("garbage"))

    def test_unparseable_remote_tag_returns_none(self):
        release = _make_github_release_response(tag_name="nope")
        with self._patch_urlopen(release):
            self.assertIsNone(updater.check_for_update("1.0.0"))

    def test_no_zip_asset_returns_none(self):
        release = _make_github_release_response(tag_name="v2.0.0")
        release["assets"] = [{"name": "notes.txt", "browser_download_url": "https://x"}]
        with self._patch_urlopen(release):
            self.assertIsNone(updater.check_for_update("1.0.0"))

    def test_network_error_returns_none(self):
        with patch("twitch_tts.updater.request.urlopen", side_effect=OSError("no network")):
            self.assertIsNone(updater.check_for_update("1.0.0"))


# ---------------------------------------------------------------------------
# download_update
# ---------------------------------------------------------------------------

class TestDownloadUpdate(unittest.TestCase):
    def test_downloads_to_dest_dir(self):
        zip_bytes = _make_release_zip({"tts.exe": b"exe-content"})

        resp = MagicMock()
        resp.headers = {"Content-Length": str(len(zip_bytes))}
        # Simulate chunked reads
        resp.read = MagicMock(side_effect=[zip_bytes, b""])
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)

        with tempfile.TemporaryDirectory() as dest:
            with patch("twitch_tts.updater.request.urlopen", return_value=resp):
                path = updater.download_update("https://example.com/release.zip", dest_dir=dest)

            self.assertTrue(os.path.isfile(path))
            self.assertTrue(path.endswith("release.zip"))
            with open(path, "rb") as f:
                self.assertEqual(f.read(), zip_bytes)

    def test_progress_callback_is_called(self):
        zip_bytes = _make_release_zip({"tts.exe": b"x" * 100})

        resp = MagicMock()
        resp.headers = {"Content-Length": str(len(zip_bytes))}
        resp.read = MagicMock(side_effect=[zip_bytes, b""])
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)

        cb = MagicMock()
        with tempfile.TemporaryDirectory() as dest:
            with patch("twitch_tts.updater.request.urlopen", return_value=resp):
                updater.download_update("https://example.com/r.zip", dest_dir=dest, progress_callback=cb)

        cb.assert_called()
        # First call should have (bytes_downloaded, total)
        args = cb.call_args_list[0][0]
        self.assertEqual(len(args), 2)


# ---------------------------------------------------------------------------
# apply_update
# ---------------------------------------------------------------------------

class TestApplyUpdate(unittest.TestCase):
    def test_extracts_update_files(self):
        zip_data = _make_release_zip({
            "tts.exe": b"new-tts",
            "tts-gui.exe": b"new-gui",
            "README.md": b"ignore-me",
        })

        with tempfile.TemporaryDirectory() as app_dir:
            # Create existing exes
            for name in ("tts.exe", "tts-gui.exe"):
                with open(os.path.join(app_dir, name), "wb") as f:
                    f.write(b"old")

            zip_path = os.path.join(app_dir, "update.zip")
            with open(zip_path, "wb") as f:
                f.write(zip_data)

            updated = updater.apply_update(zip_path, app_dir=app_dir)

            self.assertEqual(sorted(updated), ["tts-gui.exe", "tts.exe"])
            # New content written
            with open(os.path.join(app_dir, "tts.exe"), "rb") as f:
                self.assertEqual(f.read(), b"new-tts")
            # Old files backed up
            self.assertTrue(os.path.exists(os.path.join(app_dir, "tts.exe.old")))

    def test_extracts_nested_files(self):
        zip_data = _make_release_zip({
            "twitch-tts/tts.exe": b"nested-exe",
        })

        with tempfile.TemporaryDirectory() as app_dir:
            zip_path = os.path.join(app_dir, "update.zip")
            with open(zip_path, "wb") as f:
                f.write(zip_data)

            updated = updater.apply_update(zip_path, app_dir=app_dir)

            self.assertIn("tts.exe", updated)
            with open(os.path.join(app_dir, "tts.exe"), "rb") as f:
                self.assertEqual(f.read(), b"nested-exe")

    def test_removes_leftover_old_files(self):
        zip_data = _make_release_zip({"tts.exe": b"new"})

        with tempfile.TemporaryDirectory() as app_dir:
            # Simulate leftover .old from a previous update
            old_path = os.path.join(app_dir, "tts.exe.old")
            with open(old_path, "wb") as f:
                f.write(b"stale")
            with open(os.path.join(app_dir, "tts.exe"), "wb") as f:
                f.write(b"current")

            zip_path = os.path.join(app_dir, "update.zip")
            with open(zip_path, "wb") as f:
                f.write(zip_data)

            updater.apply_update(zip_path, app_dir=app_dir)

            # .old should contain the "current" content, not "stale"
            with open(old_path, "rb") as f:
                self.assertEqual(f.read(), b"current")

    def test_missing_file_in_zip_is_skipped(self):
        zip_data = _make_release_zip({"unrelated.txt": b"data"})

        with tempfile.TemporaryDirectory() as app_dir:
            zip_path = os.path.join(app_dir, "update.zip")
            with open(zip_path, "wb") as f:
                f.write(zip_data)

            updated = updater.apply_update(zip_path, app_dir=app_dir)
            self.assertEqual(updated, [])

    def test_no_existing_exe_still_extracts(self):
        zip_data = _make_release_zip({"tts.exe": b"fresh"})

        with tempfile.TemporaryDirectory() as app_dir:
            zip_path = os.path.join(app_dir, "update.zip")
            with open(zip_path, "wb") as f:
                f.write(zip_data)

            updated = updater.apply_update(zip_path, app_dir=app_dir)

            self.assertIn("tts.exe", updated)
            with open(os.path.join(app_dir, "tts.exe"), "rb") as f:
                self.assertEqual(f.read(), b"fresh")
            # No .old should exist
            self.assertFalse(os.path.exists(os.path.join(app_dir, "tts.exe.old")))


# ---------------------------------------------------------------------------
# cleanup_old_files
# ---------------------------------------------------------------------------

class TestCleanupOldFiles(unittest.TestCase):
    def test_removes_old_files(self):
        with tempfile.TemporaryDirectory() as app_dir:
            for name in updater.UPDATE_FILES:
                path = os.path.join(app_dir, name + ".old")
                with open(path, "wb") as f:
                    f.write(b"old")

            updater.cleanup_old_files(app_dir=app_dir)

            for name in updater.UPDATE_FILES:
                self.assertFalse(os.path.exists(os.path.join(app_dir, name + ".old")))

    def test_no_old_files_is_fine(self):
        with tempfile.TemporaryDirectory() as app_dir:
            # Should not raise
            updater.cleanup_old_files(app_dir=app_dir)


# ---------------------------------------------------------------------------
# cleanup_download
# ---------------------------------------------------------------------------

class TestCleanupDownload(unittest.TestCase):
    def test_removes_zip_and_empty_parent(self):
        with tempfile.TemporaryDirectory() as base:
            dl_dir = os.path.join(base, "dl")
            os.makedirs(dl_dir)
            zip_path = os.path.join(dl_dir, "update.zip")
            with open(zip_path, "wb") as f:
                f.write(b"data")

            updater.cleanup_download(zip_path)

            self.assertFalse(os.path.exists(zip_path))
            self.assertFalse(os.path.isdir(dl_dir))

    def test_keeps_parent_if_not_empty(self):
        with tempfile.TemporaryDirectory() as dl_dir:
            zip_path = os.path.join(dl_dir, "update.zip")
            other = os.path.join(dl_dir, "other.txt")
            with open(zip_path, "wb") as f:
                f.write(b"data")
            with open(other, "wb") as f:
                f.write(b"keep")

            updater.cleanup_download(zip_path)

            self.assertFalse(os.path.exists(zip_path))
            self.assertTrue(os.path.isdir(dl_dir))


# ---------------------------------------------------------------------------
# restart_app
# ---------------------------------------------------------------------------

class TestRestartApp(unittest.TestCase):
    @patch("twitch_tts.updater.sys")
    @patch("twitch_tts.updater.subprocess.Popen")
    def test_frozen_mode_relaunches_exe(self, mock_popen, mock_sys):
        mock_sys.frozen = True
        mock_sys.executable = "/app/tts.exe"
        mock_sys.argv = ["tts.exe", "--flag"]
        mock_sys.exit = MagicMock(side_effect=SystemExit)

        with self.assertRaises(SystemExit):
            updater.restart_app()

        mock_popen.assert_called_once_with(["/app/tts.exe", "--flag"])
        mock_sys.exit.assert_called_once_with(0)

    @patch("twitch_tts.updater.sys")
    @patch("twitch_tts.updater.subprocess.Popen")
    def test_script_mode_relaunches_via_python(self, mock_popen, mock_sys):
        mock_sys.frozen = False
        mock_sys.executable = "/usr/bin/python"
        mock_sys.argv = ["run.py", "--debug"]
        mock_sys.exit = MagicMock(side_effect=SystemExit)

        with self.assertRaises(SystemExit):
            updater.restart_app()

        mock_popen.assert_called_once_with(["/usr/bin/python", "run.py", "--debug"])
        mock_sys.exit.assert_called_once_with(0)


# ---------------------------------------------------------------------------
# _get_app_dir
# ---------------------------------------------------------------------------

class TestGetAppDir(unittest.TestCase):
    def test_frozen_returns_exe_dir(self):
        with patch.object(updater.sys, "frozen", True, create=True):
            with patch.object(updater.sys, "executable", "/some/dir/tts.exe"):
                self.assertEqual(updater._get_app_dir(), "/some/dir")

    def test_not_frozen_returns_cwd(self):
        # Ensure 'frozen' is not set
        with patch.object(updater, "sys") as mock_sys:
            mock_sys.frozen = False
            mock_sys.executable = "/usr/bin/python"
            with patch("os.getcwd", return_value="/working"):
                self.assertEqual(updater._get_app_dir(), "/working")


if __name__ == "__main__":
    unittest.main()
