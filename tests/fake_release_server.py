"""
Fake Release Server: a stand-in for GitHub's "latest release" endpoint,
used to test the Updater.

Used by the integration tests (see ``start_in_background``) and runnable by
hand for the manual end-to-end check (see docs/testing-the-updater.md):

    # Serve dummy exe files (quick smoke test):
    uv run python tests/fake_release_server.py

    # Serve a real Release Zip (full end-to-end with working restart):
    uv run python tests/fake_release_server.py --zip path/to/twitch-tts-build.zip

Then launch the app with:
    set TTS_UPDATE_URL=http://<this machine>:8099/releases/latest
    tts-gui.exe

The server:
  - Serves a fake GitHub "latest release" JSON at /releases/latest
  - Serves the zip at /download/<name>.zip
"""

import argparse
import io
import json
import os
import socket
import threading
import zipfile
from http.server import HTTPServer, BaseHTTPRequestHandler

DEFAULT_PORT = 8099
DEFAULT_VERSION = "99.0.0"


def build_dummy_zip() -> bytes:
    """Create an in-memory zip with dummy exe files."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("tts.exe", b"FAKE-TTS-EXE-UPDATED")
        zf.writestr("tts-gui.exe", b"FAKE-TTS-GUI-EXE-UPDATED")
    return buf.getvalue()


def load_zip(path: str) -> bytes:
    """Load a zip file from disk."""
    with open(path, "rb") as f:
        return f.read()


class FakeReleaseServer(HTTPServer):
    """HTTP server advertising *version* and serving *zip_data* as its Release Zip."""

    def __init__(self, address, zip_data: bytes, version: str, quiet: bool = False):
        super().__init__(address, FakeReleaseHandler)
        self.zip_data = zip_data
        self.version = version
        self.quiet = quiet

    @property
    def latest_release_url(self) -> str:
        host, port = self.server_address[:2]
        if host == "0.0.0.0":
            host = "localhost"
        return f"http://{host}:{port}/releases/latest"


class FakeReleaseHandler(BaseHTTPRequestHandler):
    server: FakeReleaseServer

    def do_GET(self):
        if self.path == "/releases/latest":
            self._serve_release_json()
        elif self.path.startswith("/download/"):
            self._serve_zip()
        else:
            self.send_error(404)

    def _serve_release_json(self):
        host = self.headers.get("Host", f"localhost:{self.server.server_port}")
        version = self.server.version
        tag = f"v{version}"
        zip_name = f"twitch-tts-{version}.zip"
        payload = {
            "tag_name": tag,
            "html_url": f"http://{host}/releases/tag/{tag}",
            "assets": [
                {
                    "name": zip_name,
                    "browser_download_url": f"http://{host}/download/{zip_name}",
                }
            ],
        }
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_zip(self):
        zip_data = self.server.zip_data
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Length", str(len(zip_data)))
        self.end_headers()
        self.wfile.write(zip_data)

    def log_message(self, fmt, *args):
        if not self.server.quiet:
            print(f"  [{self.address_string()}] {fmt % args}")


def start_in_background(zip_data: bytes, version: str) -> FakeReleaseServer:
    """Start a quiet server on a free localhost port in a daemon thread.

    Stop it with ``server.shutdown()`` followed by ``server.server_close()``.
    """
    server = FakeReleaseServer(("127.0.0.1", 0), zip_data, version, quiet=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _routable_ips() -> set[str]:
    ips = set()
    try:
        for iface in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(iface[4][0])
    except socket.gaierror:
        pass
    # Also try connecting to a public IP to find the default route IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    ips.discard("127.0.0.1")
    ips.discard("127.0.1.1")
    return ips


def main():
    parser = argparse.ArgumentParser(description="Fake Release Server for twitch-tts")
    parser.add_argument("--host", default="0.0.0.0",
                        help="Address to bind to (default: %(default)s)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--version", default=DEFAULT_VERSION,
                        help="Version to advertise (default: %(default)s)")
    parser.add_argument("--zip", default=None, metavar="PATH",
                        help="Path to a real Release Zip to serve (default: dummy zip)")
    args = parser.parse_args()

    if args.zip:
        if not os.path.isfile(args.zip):
            parser.error(f"Zip file not found: {args.zip}")
        zip_data = load_zip(args.zip)
        print(f"Serving real zip: {args.zip}")
    else:
        zip_data = build_dummy_zip()
        print("Serving dummy zip (use --zip to serve a real build)")

    server = FakeReleaseServer((args.host, args.port), zip_data, args.version)

    print(f"Fake Release Server running on http://{args.host}:{args.port}")
    print(f"  Advertising version: v{args.version}")
    print(f"  Zip size: {len(zip_data)} bytes")
    print()
    print("Launch the app with:")
    ips = _routable_ips()
    for ip in sorted(ips):
        url = f"http://{ip}:{args.port}/releases/latest"
        print(f"  set TTS_UPDATE_URL={url}")
    if not ips:
        print(f"  set TTS_UPDATE_URL=http://localhost:{args.port}/releases/latest")
    print()
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
