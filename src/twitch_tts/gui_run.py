"""
GUI entry point for Twitch TTS Bot (PySide6/Qt version)
"""
import sys
import os
import certifi

# Ensure SSL certificates are found in PyInstaller bundles
os.environ.setdefault('SSL_CERT_FILE', certifi.where())

from twitch_tts.gui_qt import main

if __name__ == "__main__":
    sys.exit(main())
