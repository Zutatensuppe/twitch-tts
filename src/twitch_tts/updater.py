"""
Auto-updater for twitch-tts.

Checks GitHub releases for new versions, downloads the release zip,
replaces exe files, and restarts the application.
"""

import logging
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from typing import Optional, Tuple
from urllib import request, error

import json

log = logging.getLogger(__name__)

GITHUB_API_LATEST = os.environ.get(
    "TTS_UPDATE_URL",
    "https://api.github.com/repos/Zutatensuppe/twitch-tts/releases/latest",
)
# Files to update from the release zip (never overwrite config)
UPDATE_FILES = ("tts.exe", "tts-gui.exe")


def _parse_version(version_str: str) -> Optional[Tuple[int, ...]]:
    """Parse a version string like '1.3.2' into a comparable tuple."""
    m = re.match(r"^v?(\d+(?:\.\d+)*)", version_str.strip())
    if not m:
        return None
    return tuple(int(x) for x in m.group(1).split("."))


def check_for_update(current_version: str) -> Optional[dict]:
    """Check GitHub for a newer release.

    Returns a dict with 'tag_name', 'version', 'asset_url', 'asset_name',
    and 'html_url' if a newer version is available, or None.
    """
    current = _parse_version(current_version)
    if current is None:
        log.warning("Cannot parse current version '%s', skipping update check", current_version)
        return None

    try:
        req = request.Request(GITHUB_API_LATEST, headers={"Accept": "application/vnd.github.v3+json"})
        with request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (error.URLError, OSError, json.JSONDecodeError) as e:
        log.warning("Update check failed: %s", e)
        return None

    tag = data.get("tag_name", "")
    latest = _parse_version(tag)
    if latest is None:
        log.warning("Cannot parse remote version '%s'", tag)
        return None

    if latest <= current:
        log.debug("Already up to date (%s >= %s)", current_version, tag)
        return None

    # Find the zip asset
    for asset in data.get("assets", []):
        name = asset.get("name", "")
        if name.endswith(".zip"):
            return {
                "tag_name": tag,
                "version": ".".join(str(x) for x in latest),
                "asset_url": asset["browser_download_url"],
                "asset_name": name,
                "html_url": data.get("html_url", ""),
            }

    log.warning("No zip asset found in release %s", tag)
    return None


def download_update(
    asset_url: str,
    dest_dir: Optional[str] = None,
    progress_callback=None,
) -> str:
    """Download the release zip to *dest_dir* (default: temp dir).

    *progress_callback*, if provided, is called with (bytes_downloaded, total_bytes).
    total_bytes may be -1 if unknown.

    Returns the path to the downloaded zip file.
    """
    if dest_dir is None:
        dest_dir = tempfile.mkdtemp(prefix="twitch-tts-update-")

    req = request.Request(asset_url)
    with request.urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length", -1))
        filename = asset_url.rsplit("/", 1)[-1]
        zip_path = os.path.join(dest_dir, filename)
        downloaded = 0
        with open(zip_path, "wb") as f:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    progress_callback(downloaded, total)

    return zip_path


def apply_update(zip_path: str, app_dir: Optional[str] = None) -> list[str]:
    """Apply an update from *zip_path* into *app_dir*.

    For each exe in UPDATE_FILES found in the zip:
      1. Rename the existing file to ``<name>.old``
      2. Extract the new file

    Returns a list of files that were updated.
    """
    if app_dir is None:
        app_dir = _get_app_dir()

    updated: list[str] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        zip_names = zf.namelist()
        for target in UPDATE_FILES:
            # The file may be at root or inside a single top-level folder
            match = _find_in_zip(zip_names, target)
            if match is None:
                log.warning("'%s' not found in update zip", target)
                continue

            dest = os.path.join(app_dir, target)
            old = dest + ".old"

            # Remove leftover .old from a previous update
            if os.path.exists(old):
                try:
                    os.remove(old)
                except OSError as e:
                    log.warning("Cannot remove %s: %s — skipping %s", old, e, target)
                    continue

            # Rename current exe so we can write the new one
            if os.path.exists(dest):
                os.rename(dest, old)

            # Extract
            data = zf.read(match)
            with open(dest, "wb") as f:
                f.write(data)

            updated.append(target)
            log.info("Updated %s", target)

    return updated


def cleanup_old_files(app_dir: Optional[str] = None) -> None:
    """Remove leftover .old files from a previous update."""
    if app_dir is None:
        app_dir = _get_app_dir()

    for target in UPDATE_FILES:
        old = os.path.join(app_dir, target + ".old")
        if os.path.exists(old):
            try:
                os.remove(old)
                log.debug("Cleaned up %s", old)
            except OSError as e:
                log.warning("Could not remove %s: %s", old, e)


def restart_app() -> None:
    """Restart the current application.

    On Windows with a PyInstaller exe, re-launches the same exe.
    Otherwise, re-launches via the Python interpreter.
    """
    exe = sys.executable
    if getattr(sys, "frozen", False):
        # PyInstaller bundle — sys.executable is the exe itself
        log.info("Restarting %s", exe)
        subprocess.Popen([exe] + sys.argv[1:])
    else:
        log.info("Restarting via Python: %s %s", exe, sys.argv)
        subprocess.Popen([exe] + sys.argv)
    sys.exit(0)


def cleanup_download(zip_path: str) -> None:
    """Remove the downloaded zip and its temp directory."""
    try:
        parent = os.path.dirname(zip_path)
        os.remove(zip_path)
        # Remove temp dir if empty
        if parent and os.path.isdir(parent) and not os.listdir(parent):
            os.rmdir(parent)
    except OSError as e:
        log.warning("Could not clean up download: %s", e)


# ---- internal helpers ----

def _get_app_dir() -> str:
    """Return the directory the application exe lives in."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.getcwd()


def _find_in_zip(names: list[str], target: str) -> Optional[str]:
    """Find *target* filename in a zip's name list (may be nested one level)."""
    for name in names:
        basename = name.rsplit("/", 1)[-1] if "/" in name else name
        if basename == target:
            return name
    return None
