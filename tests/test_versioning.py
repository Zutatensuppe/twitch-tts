import unittest
from unittest.mock import patch

from twitch_tts import versioning


class VersioningTests(unittest.TestCase):
    def test_prefers_build_version_when_present(self):
        with patch.object(versioning, "BUILD_VERSION", "v9.9.9"):
            self.assertEqual(versioning.get_version(), "v9.9.9")

    def test_falls_back_to_package_metadata(self):
        with patch.object(versioning, "BUILD_VERSION", None):
            with patch.object(versioning.metadata, "version", return_value="1.2.3"):
                self.assertEqual(versioning.get_version(), "1.2.3")

    def test_returns_unknown_when_metadata_missing(self):
        with patch.object(versioning, "BUILD_VERSION", None):
            with patch.object(
                versioning.metadata,
                "version",
                side_effect=versioning.metadata.PackageNotFoundError,
            ):
                self.assertEqual(versioning.get_version(), "unknown")


if __name__ == "__main__":
    unittest.main()
