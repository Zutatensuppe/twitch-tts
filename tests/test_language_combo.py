import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from PySide6.QtWidgets import QApplication

from twitch_tts.gui_qt import ClickOnlyComboBox, populate_language_combo, set_language_combo_value


class LanguageComboTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_valid_language_code_is_restored(self):
        combo = ClickOnlyComboBox()
        populate_language_combo(combo)

        set_language_combo_value(combo, "ja")

        self.assertEqual(combo.currentData(), "ja")
        self.assertEqual(combo.currentText(), "Japanese (ja)")

    def test_language_code_is_normalized_before_lookup(self):
        combo = ClickOnlyComboBox()
        populate_language_combo(combo)

        set_language_combo_value(combo, " EN ")

        self.assertEqual(combo.currentData(), "en")
        self.assertEqual(combo.currentText(), "English (en)")

    def test_invalid_language_code_clears_previous_selection(self):
        combo = ClickOnlyComboBox()
        populate_language_combo(combo)
        set_language_combo_value(combo, "ja")

        set_language_combo_value(combo, "not-a-language")

        self.assertEqual(combo.currentIndex(), -1)
        self.assertIsNone(combo.currentData())
        self.assertEqual(combo.currentText(), "")


if __name__ == "__main__":
    unittest.main()
