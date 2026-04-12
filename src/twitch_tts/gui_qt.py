"""
Twitch TTS Bot GUI using PySide6 (Qt)
Full Unicode/emoji support, native look on all platforms
"""

import sys
import os
import html
import json
import shutil
import threading
import queue
import logging
import asyncio
import commentjson
from datetime import datetime
from io import StringIO

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QLineEdit, QTextEdit, QCheckBox,
    QComboBox, QGroupBox, QFormLayout, QScrollArea, QFrame,
    QMessageBox, QFileDialog, QMenuBar, QMenu, QSplitter, QDialog,
    QDialogButtonBox, QTextBrowser, QSizePolicy, QToolButton, QLayout,
    QWidgetItem, QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QSize, QRect, QPoint
from PySide6.QtGui import QFont, QColor, QTextCharFormat, QAction, QPixmap, QIcon

from . import conf
from . import constants
from . import run as bot_runner


# ---------------------------------------------------------------------------
# ClickOnlyComboBox — QComboBox that ignores keyboard type-ahead search
# ---------------------------------------------------------------------------
class ClickOnlyComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Force list-view popup so setMaxVisibleItems works on Windows
        self.setStyleSheet("QComboBox { combobox-popup: 0; }")

    def keyPressEvent(self, event):
        # Only allow Enter/Space to open dropdown, ignore type-ahead
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space,
                           Qt.Key_Up, Qt.Key_Down):
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        # Prevent accidental mouse-wheel changes while scrolling the settings page.
        if self.view().isVisible():
            super().wheelEvent(event)
        else:
            event.ignore()


def populate_language_combo(combo):
    combo.clear()
    combo.setPlaceholderText("Select language…")
    for code, name in sorted(constants.LANGUAGES.items(), key=lambda x: x[1]):
        combo.addItem(f"{name.title()} ({code})", code)
    combo.setCurrentIndex(-1)


def set_language_combo_value(combo, code):
    normalized = str(code).strip().lower() if code is not None else ""
    if not normalized:
        combo.setCurrentIndex(-1)
        return

    idx = combo.findData(normalized)
    if idx >= 0:
        combo.setCurrentIndex(idx)
        return

    combo.setCurrentIndex(-1)


# ---------------------------------------------------------------------------
# FlowLayout — items wrap to the next line when the width is exceeded
# ---------------------------------------------------------------------------
class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=4, h_spacing=4, v_spacing=4):
        super().__init__(parent)
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self._items = []
        if margin >= 0:
            self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, test_only):
        m = self.contentsMargins()
        effective = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x = effective.x()
        y = effective.y()
        line_height = 0
        for item in self._items:
            wid = item.widget()
            space_x = self._h_spacing
            space_y = self._v_spacing
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > effective.right() and line_height > 0:
                x = effective.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x = next_x
            line_height = max(line_height, item.sizeHint().height())
        return y + line_height - rect.y() + m.bottom()


# ---------------------------------------------------------------------------
# TagInput — chip/tag style list editor
# ---------------------------------------------------------------------------
class TagInput(QWidget):
    tags_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tags = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._tag_container = QWidget()
        self._flow = FlowLayout(self._tag_container, margin=2, h_spacing=4, v_spacing=4)
        outer.addWidget(self._tag_container)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Type and press Enter to add…")
        self._input.returnPressed.connect(self._add_from_input)
        outer.addWidget(self._input)

    def _rebuild(self):
        while self._flow.count():
            item = self._flow.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        for tag in self._tags:
            chip = QFrame()
            chip.setFrameShape(QFrame.StyledPanel)
            chip.setStyleSheet(
                "QFrame{background:#e0e0e0;border-radius:3px;padding:1px 3px;}"
            )
            hl = QHBoxLayout(chip)
            hl.setContentsMargins(4, 1, 2, 1)
            hl.setSpacing(2)
            lbl = QLabel(tag)
            hl.addWidget(lbl)
            btn = QPushButton("✕")
            btn.setFixedSize(18, 18)
            btn.setStyleSheet("border:none;font-weight:bold;color:#666;")
            btn.clicked.connect(lambda checked=False, t=tag: self._remove(t))
            hl.addWidget(btn)
            self._flow.addWidget(chip)
        self._tag_container.updateGeometry()

    def _add_from_input(self):
        text = self._input.text().strip()
        if text and text not in self._tags:
            self._tags.append(text)
            self._rebuild()
            self.tags_changed.emit()
        self._input.clear()

    def _remove(self, tag):
        if tag in self._tags:
            self._tags.remove(tag)
            self._rebuild()
            self.tags_changed.emit()

    def get_tags(self):
        return list(self._tags)

    def set_tags(self, tags):
        self._tags = [t for t in tags if t]
        self._rebuild()


class LanguageTagInput(TagInput):
    """TagInput with a language dropdown instead of free-text input."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Replace the QLineEdit with a searchable QComboBox
        self._input.deleteLater()
        self._combo = ClickOnlyComboBox()
        self._combo.setFocusPolicy(Qt.ClickFocus)
        self._combo.setMaxVisibleItems(20)
        self._combo.setPlaceholderText("Select language to add…")
        self._combo.addItem("", "")
        for code, name in sorted(constants.LANGUAGES.items(), key=lambda x: x[1]):
            self._combo.addItem(f"{name.title()} ({code})", code)
        self._combo.activated.connect(self._add_from_combo)
        self.layout().addWidget(self._combo)

    def _add_from_combo(self, index):
        code = self._combo.itemData(index)
        if not code:
            return
        name = constants.LANGUAGES.get(code, code)
        display = f"{name.title()} ({code})"
        if code not in self._tags:
            self._tags.append(code)
            self._rebuild()
            self.tags_changed.emit()
        self._combo.setCurrentIndex(0)

    def _rebuild(self):
        while self._flow.count():
            item = self._flow.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        for tag in self._tags:
            chip = QFrame()
            chip.setFrameShape(QFrame.StyledPanel)
            chip.setStyleSheet(
                "QFrame{background:#e0e0e0;border-radius:3px;padding:1px 3px;}"
            )
            hl = QHBoxLayout(chip)
            hl.setContentsMargins(4, 1, 2, 1)
            hl.setSpacing(2)
            name = constants.LANGUAGES.get(tag, tag)
            lbl = QLabel(f"{name.title()} ({tag})")
            hl.addWidget(lbl)
            btn = QPushButton("✕")
            btn.setFixedSize(18, 18)
            btn.setStyleSheet("border:none;font-weight:bold;color:#666;")
            btn.clicked.connect(lambda checked=False, t=tag: self._remove(t))
            hl.addWidget(btn)
            self._flow.addWidget(chip)
        self._tag_container.updateGeometry()


# ---------------------------------------------------------------------------
# UserLangMapWidget — table mapping usernames to language overrides
# ---------------------------------------------------------------------------
class UserLangMapWidget(QWidget):
    data_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Username", "Language"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setMaximumHeight(150)
        layout.addWidget(self._table)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("+ Add")
        add_btn.clicked.connect(self._add_row)
        btn_layout.addWidget(add_btn)
        remove_btn = QPushButton("− Remove")
        remove_btn.clicked.connect(self._remove_selected)
        btn_layout.addWidget(remove_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _make_lang_combo(self):
        combo = ClickOnlyComboBox()
        combo.setFocusPolicy(Qt.ClickFocus)
        combo.setMaxVisibleItems(20)
        populate_language_combo(combo)
        combo.currentIndexChanged.connect(lambda: self.data_changed.emit())
        return combo

    def _add_row(self):
        row = self._table.rowCount()
        self._table.insertRow(row)
        username_item = QTableWidgetItem("")
        self._table.setItem(row, 0, username_item)
        combo = self._make_lang_combo()
        self._table.setCellWidget(row, 1, combo)
        self.data_changed.emit()
        self._table.itemChanged.connect(lambda: self.data_changed.emit())

    def _remove_selected(self):
        rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()), reverse=True)
        for row in rows:
            self._table.removeRow(row)
        if rows:
            self.data_changed.emit()

    def get_data(self):
        result = {}
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            username = item.text().strip() if item else ""
            combo = self._table.cellWidget(row, 1)
            lang_code = combo.currentData() if combo else ""
            if not lang_code:
                text = combo.currentText().strip() if combo else ""
                if '(' in text and text.endswith(')'):
                    lang_code = text.split('(')[-1].rstrip(')')
                else:
                    lang_code = text
            if username and lang_code:
                result[username.lower()] = lang_code
        return result

    def set_data(self, data):
        self._table.setRowCount(0)
        if not isinstance(data, dict):
            return
        for username, lang_code in data.items():
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(str(username)))
            combo = self._make_lang_combo()
            for i in range(combo.count()):
                if combo.itemData(i) == lang_code:
                    combo.setCurrentIndex(i)
                    break
            self._table.setCellWidget(row, 1, combo)


# ---------------------------------------------------------------------------
# CollapsibleSection — clickable header that shows / hides content
# ---------------------------------------------------------------------------
class CollapsibleSection(QWidget):
    toggled = Signal(bool)

    def __init__(self, title, parent=None, expanded=False):
        super().__init__(parent)
        self._title = title
        self._toggle_btn = QToolButton()
        self._toggle_btn.setStyleSheet("QToolButton{border:none;font-weight:bold;}")
        self._toggle_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._toggle_btn.setText(title)
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.setChecked(expanded)
        self._toggle_btn.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self._toggle_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._toggle_btn.toggled.connect(self._on_toggle)

        self._content = QWidget()
        self._content.setVisible(expanded)
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._toggle_btn)
        lay.addWidget(self._content)

    def _on_toggle(self, checked):
        self._toggle_btn.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        self._content.setVisible(checked)
        self.toggled.emit(checked)

    def is_expanded(self):
        return self._toggle_btn.isChecked()

    def set_expanded(self, expanded):
        self._toggle_btn.setChecked(expanded)

    def title(self):
        return self._title

    def content_layout(self):
        return self._content_layout


# ---------------------------------------------------------------------------
# HelpDialog
# ---------------------------------------------------------------------------
class HelpDialog(QDialog):
    """Dialog to show help for a config field with clickable links"""
    def __init__(self, parent, title, help_text):
        super().__init__(parent)
        self.setWindowTitle(f"Help: {title}")
        self.setMinimumWidth(450)
        self.setMinimumHeight(200)

        layout = QVBoxLayout(self)

        # Use QTextBrowser for clickable links
        text_browser = QTextBrowser()
        text_browser.setOpenExternalLinks(True)
        docs_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "docs"))
        text_browser.setSearchPaths([docs_dir])
        text_browser.setHtml(help_text)
        layout.addWidget(text_browser)

        # Close button
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.close)
        layout.addWidget(button_box)


# ---------------------------------------------------------------------------
# Logging helpers (unchanged)
# ---------------------------------------------------------------------------
class LogSignal(QObject):
    """Signal for thread-safe log updates"""
    log_message = Signal(str, str)  # level, message


class LogHandler(logging.Handler):
    """Logging handler that emits Qt signals"""
    def __init__(self, signal):
        super().__init__()
        self.signal = signal

    def emit(self, record):
        msg = self.format(record)
        self.signal.log_message.emit(record.levelname, msg)


class StdoutRedirector:
    """Redirects stdout to a Qt signal for GUI display"""
    def __init__(self, signal):
        self.signal = signal
        self.original_stdout = sys.stdout
        self.buffer = ""

    def write(self, text):
        if self.original_stdout is not None:
            self.original_stdout.write(text)
        if text.strip():
            self.signal.log_message.emit('OUTPUT', text.rstrip())

    def flush(self):
        if self.original_stdout is not None:
            self.original_stdout.flush()


# ---------------------------------------------------------------------------
# Main GUI
# ---------------------------------------------------------------------------
class TwitchTTSGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Twitch TTS Bot")
        self.setMinimumSize(900, 700)

        # State
        self.config_data = {}
        self.bot_thread = None
        self.bot_running = False
        self.bot_loop = None
        self.config_widgets = {}
        self._dirty = False
        self._loading = False
        self._saved_snapshot = {}  # snapshot of config values at last load/save
        self._sections = []  # CollapsibleSection instances for state persistence
        self._ui_state_path = os.path.join(os.getcwd(), ".tts_gui_settings.json")

        # Setup logging
        self.log_signal = LogSignal()
        self.log_signal.log_message.connect(self.append_log)
        self.setup_logging()

        # Create UI
        self.create_menu()
        self.create_ui()

        # Load config
        self.load_config()

        # Load GUI settings (sections, tabs, checkboxes) and handle autostart
        self._load_ui_state()
        if self.autostart_check.isChecked():
            QTimer.singleShot(500, self.start_bot)

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------
    def create_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        help_menu = menubar.addMenu("Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    # ------------------------------------------------------------------
    # Top-level layout: sidebar | tabs
    # ------------------------------------------------------------------
    def create_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        root_layout = QHBoxLayout(central_widget)

        # --- Sidebar ---
        sidebar = QWidget()
        sidebar.setFixedWidth(220)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(6, 6, 6, 6)

        # Status indicator
        status_row = QHBoxLayout()
        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("font-size: 22px; color: red;")
        status_row.addWidget(self.status_indicator)
        self.status_label = QLabel("Stopped")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        status_row.addWidget(self.status_label)
        status_row.addStretch()
        sb_layout.addLayout(status_row)

        # Toggle button
        self.toggle_button = QPushButton("▶ Start Bot")
        self.toggle_button.setStyleSheet(
            "QPushButton{padding:8px;font-weight:bold;background:#4CAF50;color:white;border-radius:4px;}"
            "QPushButton:hover{background:#45a049;}"
        )
        self.toggle_button.clicked.connect(self._on_toggle_bot)
        sb_layout.addWidget(self.toggle_button)

        # Channel info (visible when running)
        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        sb_layout.addWidget(self.info_label)

        sb_layout.addSpacing(10)

        # Checkboxes
        self.autostart_check = QCheckBox("Auto-start on launch")
        self.autostart_check.setChecked(False)
        sb_layout.addWidget(self.autostart_check)

        self.warn_on_exit_check = QCheckBox("Warn on exit")
        self.warn_on_exit_check.setChecked(True)
        sb_layout.addWidget(self.warn_on_exit_check)

        sb_layout.addStretch()
        root_layout.addWidget(sidebar)

        # --- Right-side tabs ---
        self.tabs = QTabWidget()
        self.tabs.addTab(self.create_settings_tab(), "Settings")
        self.tabs.addTab(self.create_logs_tab(), "Logs")
        self.tabs.currentChanged.connect(lambda _: self._save_ui_state())
        root_layout.addWidget(self.tabs, 1)

    # ------------------------------------------------------------------
    # Settings tab (replaces old config tab)
    # ------------------------------------------------------------------
    def create_settings_tab(self):
        self.help_texts = {
            'Twitch_Channel': '<b>Twitch Channel</b><br><br>The Twitch channel to monitor for chat messages.<br>Enter the channel name without the # symbol.',
            'Trans_Username': '<b>Bot Username</b><br><br>Your Twitch bot account username.<br>This is the account that will post translated messages to chat.',
            'Trans_OAUTH': '<b>OAuth Token</b><br><br><b>How to get OAuth Token:</b><br><br>'
                '1. In the browser login to twitch.tv with your account. Right click in the browser and click \'Inspect\'<br>'
                '<img src="1.png" style="max-width: 100%; height: auto;"><br><br>'
                '2. Click the \'Network\' tab<br>'
                '<img src="2.png" style="max-width: 100%; height: auto;"><br><br>'
                '3. There should be a \'Filter\' input box, type gql in there<br>'
                '<img src="3.png" style="max-width: 100%; height: auto;"><br><br>'
                '4. Click one of the remaining rows, if there is no row, hit F5 once, and then click one of the rows<br>'
                '<img src="4.png" style="max-width: 100%; height: auto;"><br><br>'
                '5. More details and tabs for the row will appear. Click the Headers tab.<br>'
                '<img src="5.png" style="max-width: 100%; height: auto;"><br><br>'
                '6. Scroll down to find \'Authorization: OAuth XXXXX\' in the Request Headers section. The XXXXX part is what you have to use<br>'
                '<img src="6.png" style="max-width: 100%; height: auto;"><br><br>'
                '7. Copy the XXXXX part (without \'OAuth \' prefix) and paste it in the OAuth Token field',
            'YoutubeChannelUrl': '<b>YouTube Channel URL</b><br><br>Optional. The YouTube channel to also monitor for chat messages.<br><br>For example <a href="https://www.youtube.com/@achan_jp">https://www.youtube.com/@achan_jp</a>',
            'YoutubeApiKey': '<b>YouTube API Key</b><br><br>Required if you want to use YouTube chat integration.<br><br>Please refer to <a href="https://support.google.com/googleapi/answer/6158862?hl=en">https://support.google.com/googleapi/answer/6158862?hl=en</a> to see how you can get an API key.',
            'Translator': '<b>Translator</b><br><br>Select the translate engine: \'deepl\' or \'google\'',
            'GoogleTranslate_suffix': '<b>Google Translate Suffix</b><br><br>Enter the suffix of the Google Translate URL you normally use.<br><br>Example: translate.google.co.jp -> \'co.jp\'<br>Example: translate.google.com -> \'com\'',
            'Send_Translation_To_Chat': '<b>Send Translation to Chat</b><br><br>When enabled, translated messages are posted back to Twitch chat.<br><br>Format: <code>[language] username: translated text</code><br><br>Requires a valid OAuth token with chat write permissions.',
            'lang_TransToHome': '<b>Primary Language</b><br><br>Your native language. Foreign chat messages are translated into this language.<br>The bot auto-detects message languages for TTS — this is only needed for translation.<br><br><b>Example:</b> If you speak Japanese, set this to Japanese. English messages will then be translated to Japanese for you.',
            'lang_HomeToOther': '<b>Secondary Language</b><br><br>When a message is already in your primary language, it gets translated to this language instead.<br>Set this to the language most of your viewers understand.<br><br><b>Example:</b> If your primary language is Japanese and most viewers speak English, set this to English. Your Japanese messages will be translated to English for them.<br><br>Leave empty if not needed.',
            'lang_Default': '<b>Fallback Language</b><br><br>Used when the language of a message cannot be detected.<br>Also the fallback for TTS when a detected language is not supported for speech synthesis.',
            'lang_SkipDetect': '<b>Skip Language Detection</b><br><br>If enabled, the default language will be used for all texts. No automatic detection of the language will happen.',
            'TTS_IN': '<b>TTS for Original Messages</b><br><br>Read incoming chat messages aloud in their detected language.',
            'TTS_OUT': '<b>TTS for Translated Messages</b><br><br>Read the translated version of messages aloud (requires translation to be configured).',
            'ReadOnlyTheseLang': '<b>TTS Only for These Languages</b><br><br>If you want TTS for only certain languages, add them here.<br>Leave empty for all languages.',
            'Ignore_Lang': '<b>Ignore Languages</b><br><br>Do not translate messages detected as these languages.',
            'Ignore_Users': '<b>Ignore Users</b><br><br>Do not process messages from these users (comma-separated, case-insensitive).',
            'Ignore_Line': '<b>Ignore Lines</b><br><br>Do not process messages containing these phrases (comma-separated).',
            'Delete_Words': '<b>Delete Words</b><br><br>Remove these words/phrases from messages before processing (comma-separated).<br><br>Supports Unicode including emoji.',
            'Ignore_Links': '<b>Replace Links</b><br><br>If enabled, all URLs in messages are replaced with the text you specify (default: "URL").<br>Leave the replacement field empty to remove links entirely.',
            'Ignore_Emojis': '<b>Ignore All Emojis</b><br><br>If enabled, all emoji characters will be removed from messages before processing.',
            'Ignore_Mentions': '<b>Ignore @Mentions / Replies</b><br><br>If enabled, messages containing @username mentions will not be read aloud.<br>This also covers replies, since Twitch automatically adds @username to reply messages.',
            'Mentions_Allow_Channel': '<b>Allow Channel Mentions</b><br><br>If enabled (and Ignore @Mentions is on), messages that only mention the channel name will still be read. Messages mentioning other users will be skipped.',
            'Delete_Mention_Names': '<b>Delete @Mention Names</b><br><br>If enabled, @username mentions are stripped from the text before TTS reads it. The rest of the message is still read.',
            'Debug': '<b>Debug Mode</b><br><br>If you encounter any bugs, you can enable debug mode to see error messages in the logs.',
            'Bot_SendWhisper': '<b>Send Startup Message</b><br><br>If enabled, the bot will announce itself in chat when it starts.',
            'Bot_StartupMessage': '<b>Startup Message</b><br><br>The message the bot sends when it joins the channel (if Send Startup Message is enabled).<br><br>The message is sent as-is. Use /me for action style. Default: "/me has landed!"',

            'UserToLangMap': '<b>User Language Map</b><br><br>Override the detected language for specific users.<br>Useful when language detection gets it wrong for a particular chatter.<br><br>Example: if user "bob" always writes in Japanese, map bob → Japanese.',
            'AssignRandomLangToUser': '<b>Random Language per User</b><br><br>When enabled, each user is assigned a random TTS language from the list below.<br>If no specific languages are listed, all available languages are used.<br>This is a novelty/fun feature.',
        }

        # Helpers ---------------------------------------------------------
        def create_help_button(field_name, label_text):
            btn = QPushButton("?")
            btn.setFixedSize(20, 20)
            btn.setToolTip("Click for help")
            btn.clicked.connect(lambda: HelpDialog(self, label_text, self.help_texts[field_name]).exec())
            return btn

        def create_toggle_button(line_edit):
            btn = QPushButton("Show")
            btn.setFixedSize(45, 20)
            def toggle():
                if line_edit.echoMode() == QLineEdit.Password:
                    line_edit.setEchoMode(QLineEdit.Normal)
                    btn.setText("Hide")
                else:
                    line_edit.setEchoMode(QLineEdit.Password)
                    btn.setText("Show")
            btn.clicked.connect(toggle)
            return btn

        def add_field_with_help(form_layout, label_text, widget, field_name):
            row_layout = QHBoxLayout()
            row_layout.addWidget(widget, 1)
            row_layout.addWidget(create_help_button(field_name, label_text))
            form_layout.addRow(label_text + ":", row_layout)

        def make_lang_combo():
            combo = ClickOnlyComboBox()
            combo.setFocusPolicy(Qt.ClickFocus)
            combo.setMaxVisibleItems(20)
            populate_language_combo(combo)
            combo.currentIndexChanged.connect(self.mark_dirty)
            return combo

        def make_suffix_combo():
            combo = ClickOnlyComboBox()
            combo.setFocusPolicy(Qt.ClickFocus)
            combo.setMaxVisibleItems(20)
            priority = ["com", "co.jp", "co.uk", "co.kr", "de", "fr"]
            added = set()
            for s in priority:
                if s in constants.SERVICE_URL_SUFFIXES:
                    combo.addItem(s, s)
                    added.add(s)
            for s in constants.SERVICE_URL_SUFFIXES:
                if s not in added:
                    combo.addItem(s, s)
            combo.currentIndexChanged.connect(self.mark_dirty)
            return combo

        # Container -------------------------------------------------------
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        sections_layout = QVBoxLayout(scroll_widget)

        # ===== Connection (expanded) =====================================
        sec_connection = CollapsibleSection("Connection", expanded=True)
        conn_form = QFormLayout()
        conn_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.config_widgets['Twitch_Channel'] = QLineEdit()
        self.config_widgets['Twitch_Channel'].setPlaceholderText("Channel name (without #)")
        self.config_widgets['Twitch_Channel'].textChanged.connect(self.mark_dirty)
        add_field_with_help(conn_form, "Twitch Channel", self.config_widgets['Twitch_Channel'], 'Twitch_Channel')

        self.config_widgets['Trans_Username'] = QLineEdit()
        self.config_widgets['Trans_Username'].setPlaceholderText("Your bot's username")
        self.config_widgets['Trans_Username'].textChanged.connect(self.mark_dirty)
        add_field_with_help(conn_form, "Bot Username", self.config_widgets['Trans_Username'], 'Trans_Username')

        oauth_layout = QHBoxLayout()
        self.config_widgets['Trans_OAUTH'] = QLineEdit()
        self.config_widgets['Trans_OAUTH'].setEchoMode(QLineEdit.Password)
        self.config_widgets['Trans_OAUTH'].setPlaceholderText("OAuth token")
        self.config_widgets['Trans_OAUTH'].textChanged.connect(self.mark_dirty)
        oauth_layout.addWidget(self.config_widgets['Trans_OAUTH'], 1)
        oauth_layout.addWidget(create_toggle_button(self.config_widgets['Trans_OAUTH']))
        oauth_layout.addWidget(create_help_button('Trans_OAUTH', "OAuth Token"))
        conn_form.addRow("OAuth Token:", oauth_layout)

        self.config_widgets['YoutubeChannelUrl'] = QLineEdit()
        self.config_widgets['YoutubeChannelUrl'].setPlaceholderText("Optional: https://www.youtube.com/@channel")
        self.config_widgets['YoutubeChannelUrl'].textChanged.connect(self.mark_dirty)
        add_field_with_help(conn_form, "YouTube Channel URL", self.config_widgets['YoutubeChannelUrl'], 'YoutubeChannelUrl')

        youtube_key_layout = QHBoxLayout()
        self.config_widgets['YoutubeApiKey'] = QLineEdit()
        self.config_widgets['YoutubeApiKey'].setEchoMode(QLineEdit.Password)
        self.config_widgets['YoutubeApiKey'].setPlaceholderText("Optional: YouTube API key")
        self.config_widgets['YoutubeApiKey'].textChanged.connect(self.mark_dirty)
        youtube_key_layout.addWidget(self.config_widgets['YoutubeApiKey'], 1)
        youtube_key_layout.addWidget(create_toggle_button(self.config_widgets['YoutubeApiKey']))
        youtube_key_layout.addWidget(create_help_button('YoutubeApiKey', "YouTube API Key"))
        conn_form.addRow("YouTube API Key:", youtube_key_layout)

        sec_connection.content_layout().addLayout(conn_form)
        sections_layout.addWidget(sec_connection)

        # ===== Translation & Language (collapsed) ========================
        sec_trans_lang = CollapsibleSection("Translation & Language", expanded=False)
        tl_form = QFormLayout()
        tl_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.config_widgets['Translator'] = QComboBox()
        self.config_widgets['Translator'].addItems(["google", "deepl"])
        self.config_widgets['Translator'].currentIndexChanged.connect(self.mark_dirty)
        self.config_widgets['Translator'].currentTextChanged.connect(self._on_translator_changed)
        add_field_with_help(tl_form, "Translator", self.config_widgets['Translator'], 'Translator')

        self.config_widgets['GoogleTranslate_suffix'] = make_suffix_combo()
        add_field_with_help(tl_form, "Google Translate Suffix", self.config_widgets['GoogleTranslate_suffix'], 'GoogleTranslate_suffix')
        self._suffix_label_row_widget = self.config_widgets['GoogleTranslate_suffix']

        self.config_widgets['lang_TransToHome'] = make_lang_combo()
        add_field_with_help(tl_form, "Primary Language", self.config_widgets['lang_TransToHome'], 'lang_TransToHome')

        self.config_widgets['lang_HomeToOther'] = make_lang_combo()
        add_field_with_help(tl_form, "Secondary Language", self.config_widgets['lang_HomeToOther'], 'lang_HomeToOther')

        self.config_widgets['lang_Default'] = make_lang_combo()
        add_field_with_help(tl_form, "Fallback Language", self.config_widgets['lang_Default'], 'lang_Default')

        skip_detect_layout = QHBoxLayout()
        self.config_widgets['lang_SkipDetect'] = QCheckBox("Skip Language Detection (use fallback for all)")
        self.config_widgets['lang_SkipDetect'].stateChanged.connect(self.mark_dirty)
        skip_detect_layout.addWidget(self.config_widgets['lang_SkipDetect'])
        skip_detect_layout.addWidget(create_help_button('lang_SkipDetect', "Skip Language Detection"))
        skip_detect_layout.addStretch()
        tl_form.addRow("", skip_detect_layout)

        # UserToLangMap table
        self.config_widgets['UserToLangMap'] = UserLangMapWidget()
        self.config_widgets['UserToLangMap'].data_changed.connect(self.mark_dirty)
        add_field_with_help(tl_form, "User Language Map", self.config_widgets['UserToLangMap'], 'UserToLangMap')

        # AssignRandomLangToUser
        assign_random_layout = QVBoxLayout()
        self.config_widgets['AssignRandomLangToUser_enabled'] = QCheckBox("Assign random language per user")
        self.config_widgets['AssignRandomLangToUser_enabled'].stateChanged.connect(self.mark_dirty)
        self.config_widgets['AssignRandomLangToUser_enabled'].stateChanged.connect(self._on_assign_random_changed)
        assign_random_layout.addWidget(self.config_widgets['AssignRandomLangToUser_enabled'])
        self.config_widgets['AssignRandomLangToUser'] = LanguageTagInput()
        self.config_widgets['AssignRandomLangToUser'].tags_changed.connect(self.mark_dirty)
        assign_random_layout.addWidget(self.config_widgets['AssignRandomLangToUser'])
        assign_random_wrapper = QWidget()
        assign_random_wrapper.setLayout(assign_random_layout)
        add_field_with_help(tl_form, "Random Language", assign_random_wrapper, 'AssignRandomLangToUser')

        sec_trans_lang.content_layout().addLayout(tl_form)
        sections_layout.addWidget(sec_trans_lang)

        # ===== Text-to-Speech (collapsed) ================================
        sec_tts = CollapsibleSection("Text-to-Speech", expanded=False)
        tts_form = QFormLayout()
        tts_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        tts_check_layout = QHBoxLayout()
        self.config_widgets['TTS_IN'] = QCheckBox("Read original messages aloud")
        self.config_widgets['TTS_IN'].stateChanged.connect(self.mark_dirty)
        tts_check_layout.addWidget(self.config_widgets['TTS_IN'])
        tts_check_layout.addWidget(create_help_button('TTS_IN', "TTS for Input"))
        self.config_widgets['TTS_OUT'] = QCheckBox("Read translated messages aloud")
        self.config_widgets['TTS_OUT'].stateChanged.connect(self.mark_dirty)
        tts_check_layout.addWidget(self.config_widgets['TTS_OUT'])
        tts_check_layout.addWidget(create_help_button('TTS_OUT', "TTS for Output"))
        tts_form.addRow("", tts_check_layout)

        self.config_widgets['ReadOnlyTheseLang'] = LanguageTagInput()
        self.config_widgets['ReadOnlyTheseLang'].tags_changed.connect(self.mark_dirty)
        add_field_with_help(tts_form, "TTS Only for Languages", self.config_widgets['ReadOnlyTheseLang'], 'ReadOnlyTheseLang')

        sec_tts.content_layout().addLayout(tts_form)
        sections_layout.addWidget(sec_tts)

        # ===== Chat Output (collapsed) ===================================
        sec_chat = CollapsibleSection("Chat Output", expanded=False)
        chat_form = QFormLayout()
        chat_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        send_trans_layout = QHBoxLayout()
        self.config_widgets['Send_Translation_To_Chat'] = QCheckBox("Send translations to chat")
        self.config_widgets['Send_Translation_To_Chat'].stateChanged.connect(self.mark_dirty)
        send_trans_layout.addWidget(self.config_widgets['Send_Translation_To_Chat'])
        send_trans_layout.addWidget(create_help_button('Send_Translation_To_Chat', "Send Translation to Chat"))
        send_trans_layout.addStretch()
        chat_form.addRow("", send_trans_layout)

        startup_layout = QHBoxLayout()
        self.config_widgets['Bot_SendWhisper'] = QCheckBox("Send Startup Message")
        self.config_widgets['Bot_SendWhisper'].stateChanged.connect(self.mark_dirty)
        self.config_widgets['Bot_SendWhisper'].stateChanged.connect(self._on_send_whisper_changed)
        startup_layout.addWidget(self.config_widgets['Bot_SendWhisper'])
        startup_layout.addWidget(create_help_button('Bot_SendWhisper', "Send Startup Message"))
        startup_layout.addStretch()
        chat_form.addRow("", startup_layout)

        self.config_widgets['Bot_StartupMessage'] = QLineEdit()
        self.config_widgets['Bot_StartupMessage'].setPlaceholderText("/me has landed!")
        self.config_widgets['Bot_StartupMessage'].textChanged.connect(self.mark_dirty)
        add_field_with_help(chat_form, "Startup Message", self.config_widgets['Bot_StartupMessage'], 'Bot_StartupMessage')

        # Color combo with swatches

        sec_chat.content_layout().addLayout(chat_form)
        sections_layout.addWidget(sec_chat)

        # ===== Message Filtering (collapsed) =============================
        sec_filter = CollapsibleSection("Message Filtering", expanded=False)
        filter_form = QFormLayout()
        filter_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.config_widgets['Ignore_Lang'] = LanguageTagInput()
        self.config_widgets['Ignore_Lang'].tags_changed.connect(self.mark_dirty)
        add_field_with_help(filter_form, "Ignore Languages", self.config_widgets['Ignore_Lang'], 'Ignore_Lang')

        self.config_widgets['Ignore_Users'] = TagInput()
        self.config_widgets['Ignore_Users'].tags_changed.connect(self.mark_dirty)
        add_field_with_help(filter_form, "Ignore Users", self.config_widgets['Ignore_Users'], 'Ignore_Users')

        self.config_widgets['Ignore_Line'] = TagInput()
        self.config_widgets['Ignore_Line'].tags_changed.connect(self.mark_dirty)
        add_field_with_help(filter_form, "Ignore Lines", self.config_widgets['Ignore_Line'], 'Ignore_Line')

        self.config_widgets['Delete_Words'] = TagInput()
        self.config_widgets['Delete_Words'].tags_changed.connect(self.mark_dirty)
        add_field_with_help(filter_form, "Delete Words", self.config_widgets['Delete_Words'], 'Delete_Words')

        link_check_layout = QHBoxLayout()
        self.config_widgets['Ignore_Links'] = QCheckBox("Replace Links")
        self.config_widgets['Ignore_Links'].stateChanged.connect(self.mark_dirty)
        self.config_widgets['Ignore_Links'].stateChanged.connect(self._on_ignore_links_changed)
        link_check_layout.addWidget(self.config_widgets['Ignore_Links'])
        link_check_layout.addWidget(create_help_button('Ignore_Links', "Replace Links"))
        link_check_layout.addStretch()
        filter_form.addRow(link_check_layout)

        self.config_widgets['Link_Replacement'] = QLineEdit()
        self.config_widgets['Link_Replacement'].setPlaceholderText("e.g. URL")
        self.config_widgets['Link_Replacement'].setMaximumWidth(200)
        self.config_widgets['Link_Replacement'].textChanged.connect(self.mark_dirty)
        self._link_replacement_label = QLabel("Replacement text:")
        filter_form.addRow(self._link_replacement_label, self.config_widgets['Link_Replacement'])

        emoji_layout = QHBoxLayout()
        self.config_widgets['Ignore_Emojis'] = QCheckBox("Ignore All Emojis")
        self.config_widgets['Ignore_Emojis'].stateChanged.connect(self.mark_dirty)
        emoji_layout.addWidget(self.config_widgets['Ignore_Emojis'])
        emoji_layout.addWidget(create_help_button('Ignore_Emojis', "Ignore All Emojis"))
        emoji_layout.addStretch()
        filter_form.addRow(emoji_layout)

        mention_layout = QHBoxLayout()
        self.config_widgets['Ignore_Mentions'] = QCheckBox("Ignore @Mentions / Replies")
        self.config_widgets['Ignore_Mentions'].stateChanged.connect(self.mark_dirty)
        self.config_widgets['Ignore_Mentions'].stateChanged.connect(self._on_ignore_mentions_changed)
        mention_layout.addWidget(self.config_widgets['Ignore_Mentions'])
        mention_layout.addWidget(create_help_button('Ignore_Mentions', "Ignore @Mentions"))
        mention_layout.addStretch()
        filter_form.addRow(mention_layout)

        allow_channel_layout = QHBoxLayout()
        self.config_widgets['Mentions_Allow_Channel'] = QCheckBox("Allow Channel @Mentions")
        self.config_widgets['Mentions_Allow_Channel'].stateChanged.connect(self.mark_dirty)
        allow_channel_layout.addWidget(self.config_widgets['Mentions_Allow_Channel'])
        allow_channel_layout.addWidget(create_help_button('Mentions_Allow_Channel', "Allow Channel Mentions"))
        allow_channel_layout.addStretch()
        filter_form.addRow(allow_channel_layout)

        delete_mention_layout = QHBoxLayout()
        self.config_widgets['Delete_Mention_Names'] = QCheckBox("Delete @Mention Names from TTS")
        self.config_widgets['Delete_Mention_Names'].stateChanged.connect(self.mark_dirty)
        delete_mention_layout.addWidget(self.config_widgets['Delete_Mention_Names'])
        delete_mention_layout.addWidget(create_help_button('Delete_Mention_Names', "Delete @Mention Names"))
        delete_mention_layout.addStretch()
        filter_form.addRow(delete_mention_layout)

        sec_filter.content_layout().addLayout(filter_form)
        sections_layout.addWidget(sec_filter)

        # ===== Debug (standalone checkbox) ================================
        debug_layout = QHBoxLayout()
        self.config_widgets['Debug'] = QCheckBox("Debug Mode")
        self.config_widgets['Debug'].stateChanged.connect(self.mark_dirty)
        debug_layout.addWidget(self.config_widgets['Debug'])
        debug_layout.addWidget(create_help_button('Debug', "Debug Mode"))
        debug_layout.addStretch()
        sections_layout.addLayout(debug_layout)

        # Register sections for state persistence
        self._sections = [sec_connection, sec_trans_lang, sec_tts, sec_chat, sec_filter]
        for sec in self._sections:
            sec.toggled.connect(lambda _: self._save_ui_state())

        sections_layout.addStretch()
        scroll.setWidget(scroll_widget)
        container_layout.addWidget(scroll, 1)

        # ===== Sticky save bar ===========================================
        save_bar = QHBoxLayout()
        save_bar.setContentsMargins(6, 4, 6, 4)
        self.config_status_label = QLabel("")
        self.config_status_label.setStyleSheet("font-weight: bold;")
        save_bar.addWidget(self.config_status_label)
        save_bar.addStretch()
        self.save_btn = QPushButton("Save Config")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save_config)
        save_bar.addWidget(self.save_btn)
        container_layout.addLayout(save_bar)

        # Apply initial conditional visibility
        self._on_translator_changed(self.config_widgets['Translator'].currentText())
        self._on_ignore_mentions_changed()
        self._on_send_whisper_changed()
        self._on_ignore_links_changed()

        return container

    # ------------------------------------------------------------------
    # Logs tab (unchanged)
    # ------------------------------------------------------------------
    def create_logs_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        controls_layout = QHBoxLayout()

        self.auto_scroll_check = QCheckBox("Auto-scroll")
        self.auto_scroll_check.setChecked(True)
        controls_layout.addWidget(self.auto_scroll_check)

        self.verbose_logs_check = QCheckBox("Verbose (show namespace)")
        self.verbose_logs_check.setChecked(False)
        self.verbose_logs_check.stateChanged.connect(self.update_log_format)
        controls_layout.addWidget(self.verbose_logs_check)

        clear_btn = QPushButton("Clear Logs")
        clear_btn.clicked.connect(self.clear_logs)
        controls_layout.addWidget(clear_btn)

        save_btn = QPushButton("Save Logs")
        save_btn.clicked.connect(self.save_logs)
        controls_layout.addWidget(save_btn)

        controls_layout.addStretch()
        layout.addLayout(controls_layout)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Monospace", 9))
        layout.addWidget(self.log_text)

        return widget

    # ------------------------------------------------------------------
    # Conditional visibility helpers
    # ------------------------------------------------------------------
    def _on_translator_changed(self, text=None):
        is_google = self.config_widgets['Translator'].currentText() == "google"
        self.config_widgets['GoogleTranslate_suffix'].setVisible(is_google)

    def _on_ignore_mentions_changed(self, _state=None):
        enabled = self.config_widgets['Ignore_Mentions'].isChecked()
        self.config_widgets['Mentions_Allow_Channel'].setEnabled(enabled)

    def _on_send_whisper_changed(self, _state=None):
        enabled = self.config_widgets['Bot_SendWhisper'].isChecked()
        self.config_widgets['Bot_StartupMessage'].setEnabled(enabled)

    def _on_assign_random_changed(self, _state=None):
        enabled = self.config_widgets['AssignRandomLangToUser_enabled'].isChecked()
        self.config_widgets['AssignRandomLangToUser'].setVisible(enabled)

    def _on_ignore_links_changed(self, _state=None):
        enabled = self.config_widgets['Ignore_Links'].isChecked()
        self.config_widgets['Link_Replacement'].setVisible(enabled)
        # Also hide the form label for the replacement row
        if hasattr(self, '_link_replacement_label'):
            self._link_replacement_label.setVisible(enabled)

    # ------------------------------------------------------------------
    # Dirty tracking
    # ------------------------------------------------------------------
    def _get_current_values(self):
        """Extract current widget values as a comparable dict."""
        vals = {}
        for field in ['Twitch_Channel', 'Trans_Username', 'Trans_OAUTH',
                       'YoutubeChannelUrl', 'YoutubeApiKey', 'Bot_StartupMessage']:
            if field in self.config_widgets:
                vals[field] = self.config_widgets[field].text()
        for field in ['lang_TransToHome', 'lang_HomeToOther', 'lang_Default']:
            w = self.config_widgets.get(field)
            if w:
                data = w.currentData()
                if data:
                    vals[field] = data
                else:
                    text = w.currentText().strip()
                    if '(' in text and text.endswith(')'):
                        vals[field] = text.split('(')[-1].rstrip(')')
                    else:
                        vals[field] = text
        for field in ['GoogleTranslate_suffix']:
            w = self.config_widgets.get(field)
            if w:
                data = w.currentData()
                vals[field] = data if data else w.currentText().strip()
        for field in ['Translator']:
            w = self.config_widgets.get(field)
            if w:
                vals[field] = w.currentText()
        for field in ['lang_SkipDetect', 'TTS_IN', 'TTS_OUT', 'Send_Translation_To_Chat',
                       'Debug', 'Bot_SendWhisper',
                       'Ignore_Links', 'Ignore_Emojis', 'Ignore_Mentions',
                       'Mentions_Allow_Channel', 'Delete_Mention_Names']:
            w = self.config_widgets.get(field)
            if w:
                vals[field] = w.isChecked()
        for field in ['Ignore_Lang', 'Ignore_Users', 'Ignore_Line', 'Delete_Words', 'ReadOnlyTheseLang']:
            w = self.config_widgets.get(field)
            if w:
                vals[field] = tuple(w.get_tags())
        w = self.config_widgets.get('Link_Replacement')
        if w:
            vals['Link_Replacement'] = w.text()
        # UserToLangMap
        w = self.config_widgets.get('UserToLangMap')
        if w:
            vals['UserToLangMap'] = str(sorted(w.get_data().items()))
        # AssignRandomLangToUser
        w_enabled = self.config_widgets.get('AssignRandomLangToUser_enabled')
        w_tags = self.config_widgets.get('AssignRandomLangToUser')
        if w_enabled:
            vals['AssignRandomLangToUser_enabled'] = w_enabled.isChecked()
        if w_tags:
            vals['AssignRandomLangToUser_tags'] = tuple(w_tags.get_tags())
        return vals

    def mark_dirty(self, *_args):
        if self._loading:
            return
        actually_dirty = self._get_current_values() != self._saved_snapshot
        self._dirty = actually_dirty
        self.save_btn.setEnabled(actually_dirty)
        if actually_dirty:
            self.config_status_label.setText("Unsaved changes")
            self.config_status_label.setStyleSheet("color: orange; font-weight: bold;")
        else:
            self.config_status_label.setText("")

    def mark_clean(self):
        self._saved_snapshot = self._get_current_values()
        self._dirty = False
        self.save_btn.setEnabled(False)
        self.config_status_label.setText("✓ Saved")
        self.config_status_label.setStyleSheet("color: green; font-weight: bold;")
        QTimer.singleShot(3000, lambda: (
            self.config_status_label.setText("") if not self._dirty else None
        ))

    # ------------------------------------------------------------------
    # UI state persistence (all GUI settings in one file)
    # ------------------------------------------------------------------
    def _load_ui_state(self):
        try:
            with open(self._ui_state_path, 'r') as f:
                state = json.loads(f.read())
            sections_state = state.get('sections', {})
            for sec in self._sections:
                if sec.title() in sections_state:
                    sec.set_expanded(sections_state[sec.title()])
            active_tab = state.get('active_tab', 0)
            if 0 <= active_tab < self.tabs.count():
                self.tabs.setCurrentIndex(active_tab)
            self.autostart_check.setChecked(state.get('autostart', False))
            self.auto_scroll_check.setChecked(state.get('auto_scroll', True))
            self.verbose_logs_check.setChecked(state.get('verbose_logs', False))
            self.warn_on_exit_check.setChecked(state.get('warn_on_exit', True))
            if state.get('verbose_logs', False):
                self.update_log_format()
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def _save_ui_state(self):
        state = {
            'sections': {sec.title(): sec.is_expanded() for sec in self._sections},
            'active_tab': self.tabs.currentIndex(),
            'autostart': self.autostart_check.isChecked(),
            'auto_scroll': self.auto_scroll_check.isChecked(),
            'verbose_logs': self.verbose_logs_check.isChecked(),
            'warn_on_exit': self.warn_on_exit_check.isChecked(),
        }
        try:
            with open(self._ui_state_path, 'w') as f:
                f.write(json.dumps(state, indent=2))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    def setup_logging(self):
        self.log_handler = LogHandler(self.log_signal)
        self.log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(self.log_handler)
        logging.getLogger().setLevel(logging.INFO)

        self.stdout_redirector = StdoutRedirector(self.log_signal)
        sys.stdout = self.stdout_redirector

    def update_log_format(self):
        """Toggle between simple and verbose log format"""
        if self.verbose_logs_check.isChecked():
            self.log_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        else:
            self.log_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s'))

    def append_log(self, level, message):
        colors = {
            'INFO': 'black',
            'WARNING': 'orange',
            'ERROR': 'red',
            'DEBUG': 'gray',
            'CRITICAL': 'darkred',
            'OUTPUT': '#0066cc'
        }
        color = colors.get(level, 'black')
        safe_message = html.escape(message)
        self.log_text.append(f'<span style="color:{color}">{safe_message}</span>')

        if self.auto_scroll_check.isChecked():
            self.log_text.verticalScrollBar().setValue(
                self.log_text.verticalScrollBar().maximum()
            )

    def clear_logs(self):
        self.log_text.clear()

    def save_logs(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Logs",
            f"tts_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Text files (*.txt);;All files (*.*)"
        )
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.toPlainText())
                logging.info(f"Logs saved to {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save logs: {str(e)}")

    # ------------------------------------------------------------------
    # Config load / save / validate
    # ------------------------------------------------------------------
    def load_config(self):
        config_path = os.path.join(os.getcwd(), "config.jsonc")
        if not os.path.exists(config_path):
            # First-run: copy example config
            example_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config_example.jsonc')
            if os.path.exists(example_path):
                shutil.copy(example_path, config_path)
                logging.info("Created config.jsonc from config_example.jsonc")
            else:
                logging.warning("config.jsonc not found and no example config available.")
                return

        try:
            with open(config_path, encoding='utf-8') as f:
                self.config_data = commentjson.load(f)
            self.populate_config_fields()
            logging.info("Configuration loaded successfully")
            self._highlight_required_empty()
        except Exception as e:
            logging.error(f"Failed to load config: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to load config: {str(e)}")

    def _highlight_required_empty(self):
        """Highlight required fields that are still empty."""
        required_fields = ['Twitch_Channel', 'Trans_Username', 'Trans_OAUTH']
        for field in required_fields:
            w = self.config_widgets.get(field)
            if w and isinstance(w, QLineEdit) and not w.text().strip():
                w.setStyleSheet("border: 1px solid #cc0000;")
            elif w and isinstance(w, QLineEdit):
                w.setStyleSheet("")

    def populate_config_fields(self):
        self._loading = True

        # Plain string fields
        plain_string_fields = [
            'Twitch_Channel', 'Trans_Username', 'Trans_OAUTH',
            'YoutubeChannelUrl', 'YoutubeApiKey',
            'Bot_StartupMessage'
        ]
        for field in plain_string_fields:
            if field in self.config_data and field in self.config_widgets:
                self.config_widgets[field].setText(str(self.config_data.get(field, '')))

        # Language combo fields
        lang_combo_fields = ['lang_TransToHome', 'lang_HomeToOther', 'lang_Default']
        for field in lang_combo_fields:
            set_language_combo_value(self.config_widgets[field], self.config_data.get(field, ""))

        # GoogleTranslate_suffix combo
        if 'GoogleTranslate_suffix' in self.config_data:
            suffix = str(self.config_data['GoogleTranslate_suffix'])
            idx = self.config_widgets['GoogleTranslate_suffix'].findData(suffix)
            if idx >= 0:
                self.config_widgets['GoogleTranslate_suffix'].setCurrentIndex(idx)
            else:
                self.config_widgets['GoogleTranslate_suffix'].setCurrentText(suffix)

        # Translator combo
        if 'Translator' in self.config_data:
            idx = self.config_widgets['Translator'].findText(self.config_data['Translator'])
            if idx >= 0:
                self.config_widgets['Translator'].setCurrentIndex(idx)



        # Boolean fields
        bool_fields = {
            'lang_SkipDetect': False,
            'TTS_IN': True, 'TTS_OUT': False, 'Send_Translation_To_Chat': False,
            'Debug': False, 'Bot_SendWhisper': False,
            'Ignore_Links': False, 'Ignore_Emojis': False,
            'Ignore_Mentions': False,
            'Mentions_Allow_Channel': True, 'Delete_Mention_Names': True
        }
        for field, default in bool_fields.items():
            if field in self.config_widgets:
                self.config_widgets[field].setChecked(self.config_data.get(field, default))

        # Tag fields
        tag_fields = ['Ignore_Lang', 'Ignore_Users', 'Ignore_Line', 'Delete_Words', 'ReadOnlyTheseLang']
        for field in tag_fields:
            if field in self.config_data and isinstance(self.config_data[field], list):
                self.config_widgets[field].set_tags(self.config_data[field])

        # UserToLangMap
        if 'UserToLangMap' in self.config_data:
            self.config_widgets['UserToLangMap'].set_data(self.config_data.get('UserToLangMap', {}))

        # AssignRandomLangToUser
        assign_val = self.config_data.get('AssignRandomLangToUser', [])
        if assign_val == True or (isinstance(assign_val, list) and len(assign_val) > 0):
            self.config_widgets['AssignRandomLangToUser_enabled'].setChecked(True)
            if isinstance(assign_val, list):
                self.config_widgets['AssignRandomLangToUser'].set_tags(assign_val)
        else:
            self.config_widgets['AssignRandomLangToUser_enabled'].setChecked(False)
            self.config_widgets['AssignRandomLangToUser'].set_tags([])

        # Link replacement text (from Delete_Links config field)
        replacement = self.config_data.get('Delete_Links', 'URL')
        if replacement == False or replacement == '':
            replacement = ''
        self.config_widgets['Link_Replacement'].setText(str(replacement))

        # Re-apply conditional visibility after populating
        self._on_translator_changed()
        self._on_ignore_mentions_changed()
        self._on_send_whisper_changed()
        self._on_ignore_links_changed()
        self._on_assign_random_changed()

        self._loading = False
        self.mark_clean()

    def save_config(self):
        if not self.validate_config(show_success=False):
            return

        config_path = os.path.join(os.getcwd(), "config.jsonc")

        old_channel = self.config_data.get('Twitch_Channel', '')
        old_username = self.config_data.get('Trans_Username', '')
        old_oauth = self.config_data.get('Trans_OAUTH', '')

        config = {}

        # Plain string fields
        plain_string_fields = [
            'Twitch_Channel', 'Trans_Username', 'Trans_OAUTH',
            'YoutubeChannelUrl', 'YoutubeApiKey',
            'Bot_StartupMessage'
        ]
        for field in plain_string_fields:
            if field in self.config_widgets:
                config[field] = self.config_widgets[field].text()

        # Language combo fields
        lang_combo_fields = ['lang_TransToHome', 'lang_HomeToOther', 'lang_Default']
        for field in lang_combo_fields:
            data = self.config_widgets[field].currentData()
            if data:
                config[field] = data
            else:
                text = self.config_widgets[field].currentText().strip()
                if '(' in text and text.endswith(')'):
                    config[field] = text.split('(')[-1].rstrip(')')
                else:
                    config[field] = text

        # GoogleTranslate_suffix combo
        suffix_data = self.config_widgets['GoogleTranslate_suffix'].currentData()
        if suffix_data:
            config['GoogleTranslate_suffix'] = suffix_data
        else:
            config['GoogleTranslate_suffix'] = self.config_widgets['GoogleTranslate_suffix'].currentText().strip()

        # Combobox fields
        config['Translator'] = self.config_widgets['Translator'].currentText()


        # Boolean fields
        bool_fields = ['lang_SkipDetect',
                      'TTS_IN', 'TTS_OUT', 'Send_Translation_To_Chat',
                      'Debug', 'Bot_SendWhisper',
                      'Ignore_Links', 'Ignore_Emojis',
                      'Ignore_Mentions',
                      'Mentions_Allow_Channel', 'Delete_Mention_Names']
        for field in bool_fields:
            if field in self.config_widgets:
                config[field] = self.config_widgets[field].isChecked()

        # Tag fields
        tag_fields = ['Ignore_Lang', 'Ignore_Users', 'Ignore_Line', 'Delete_Words', 'ReadOnlyTheseLang']
        for field in tag_fields:
            config[field] = self.config_widgets[field].get_tags()

        # Link replacement
        config['Delete_Links'] = self.config_widgets['Link_Replacement'].text() or ''

        # UserToLangMap
        config['UserToLangMap'] = self.config_widgets['UserToLangMap'].get_data()

        # AssignRandomLangToUser
        if self.config_widgets['AssignRandomLangToUser_enabled'].isChecked():
            tags = self.config_widgets['AssignRandomLangToUser'].get_tags()
            config['AssignRandomLangToUser'] = tags if tags else True
        else:
            config['AssignRandomLangToUser'] = []

        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                commentjson.dump(config, f, indent=2, ensure_ascii=False)
            self.config_data = config
            logging.info("Configuration saved successfully")

            # Re-read config to refresh UI
            self.load_config()

            # Reload runtime config for running bot
            if self.bot_running:
                bot_runner.reload_config()

            new_channel = config.get('Twitch_Channel', '')
            new_username = config.get('Trans_Username', '')
            new_oauth = config.get('Trans_OAUTH', '')
            connection_changed = (
                old_channel != new_channel
                or old_username != new_username
                or old_oauth != new_oauth
            )
            if connection_changed and self.bot_running:
                logging.info("Connection settings changed, restarting bot...")
                self.stop_bot()
                QTimer.singleShot(200, self._start_bot_when_ready)

            self.mark_clean()
        except Exception as e:
            logging.error(f"Failed to save config: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to save config: {str(e)}")

    def validate_config(self, show_success=True):
        """Validate config. Only show feedback on success if show_success=True"""
        errors = []

        required = {
            'Twitch_Channel': "Twitch Channel is required",
            'Trans_Username': "Bot Username is required",
            'Trans_OAUTH': "OAuth Token is required",
        }
        for field, msg in required.items():
            w = self.config_widgets[field]
            if not w.text().strip():
                errors.append(msg)
                w.setStyleSheet("border: 1px solid #cc0000;")
            else:
                w.setStyleSheet("")

        if errors:
            self.config_status_label.setText("✗ " + "; ".join(errors))
            self.config_status_label.setStyleSheet("color: red; font-weight: bold;")
            return False

        if show_success:
            self.config_status_label.setText("✓ Configuration is valid")
            self.config_status_label.setStyleSheet("color: green; font-weight: bold;")
            QTimer.singleShot(3000, lambda: self.config_status_label.setText(""))
        return True

    # ------------------------------------------------------------------
    # Bot control
    # ------------------------------------------------------------------
    def _on_toggle_bot(self):
        if self.bot_running:
            self.stop_bot()
        else:
            self.start_bot()

    def start_bot(self):
        if self.bot_thread and self.bot_thread.is_alive():
            logging.info("Bot is still shutting down; please wait")
            return
        if self.bot_running:
            QMessageBox.warning(self, "Already Running", "Bot is already running")
            return

        if not self.validate_config(show_success=False):
            return

        self.bot_thread = threading.Thread(target=self.run_bot, daemon=True)
        self.bot_thread.start()

        self.bot_running = True
        self.update_status(True)
        self.toggle_button.setText("⏹ Stop Bot")
        self.toggle_button.setStyleSheet(
            "QPushButton{padding:8px;font-weight:bold;background:#e53935;color:white;border-radius:4px;}"
            "QPushButton:hover{background:#c62828;}"
        )
        logging.info("Bot started")

    def _start_bot_when_ready(self):
        if self.bot_thread and self.bot_thread.is_alive():
            QTimer.singleShot(200, self._start_bot_when_ready)
            return
        self.start_bot()

    def stop_bot(self):
        if not self.bot_running:
            return

        try:
            bot_runner.stop_tts()
            self.bot_running = False
            self.update_status(False)
            self.toggle_button.setText("▶ Start Bot")
            self.toggle_button.setStyleSheet(
                "QPushButton{padding:8px;font-weight:bold;background:#4CAF50;color:white;border-radius:4px;}"
                "QPushButton:hover{background:#45a049;}"
            )
            logging.info("Bot stopped")
        except Exception as e:
            logging.error(f"Error stopping bot: {str(e)}")

    def run_bot(self):
        try:
            self.bot_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.bot_loop)

            import importlib
            importlib.reload(bot_runner)

            bot_runner.start_tts()
            bot_runner.run_bot_core()
        except Exception as e:
            logging.error(f"Bot error: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
            self.bot_running = False
            QTimer.singleShot(0, lambda: self.update_status(False))
            QTimer.singleShot(0, lambda: self.toggle_button.setText("▶ Start Bot"))
            QTimer.singleShot(0, lambda: self.toggle_button.setStyleSheet(
                "QPushButton{padding:8px;font-weight:bold;background:#4CAF50;color:white;border-radius:4px;}"
                "QPushButton:hover{background:#45a049;}"
            ))
        finally:
            try:
                if self.bot_loop and self.bot_loop.is_running():
                    self.bot_loop.stop()
                if self.bot_loop:
                    self.bot_loop.close()
                self.bot_loop = None
            except:
                pass

    def update_status(self, running):
        if running:
            self.status_label.setText("Running")
            self.status_indicator.setStyleSheet("font-size: 22px; color: green;")
            channel = self.config_widgets['Twitch_Channel'].text()
            username = self.config_widgets['Trans_Username'].text()
            self.info_label.setText(f"Channel: {channel}\nBot: {username}")
        else:
            self.status_label.setText("Stopped")
            self.status_indicator.setStyleSheet("font-size: 22px; color: red;")
            self.info_label.setText("")

    # ------------------------------------------------------------------
    # About
    # ------------------------------------------------------------------
    def show_about(self):
        try:
            from importlib import metadata
            version = metadata.version('twitch-tts')
        except:
            version = "unknown"

        QMessageBox.about(self, "About Twitch TTS Bot",
            f"Twitch TTS Bot - GUI Version\n"
            f"Version: {version}\n\n"
            f"A text-to-speech bot for Twitch chat with translation support.\n\n"
            f"Created by: Zutatensuppe\n"
            f"GitHub: https://github.com/Zutatensuppe/twitch-tts"
        )

    # ------------------------------------------------------------------
    # GUI settings persistence
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Close event
    # ------------------------------------------------------------------
    def closeEvent(self, event):
        self._save_ui_state()

        if hasattr(self, 'stdout_redirector'):
            sys.stdout = self.stdout_redirector.original_stdout

        if self.bot_running:
            if self.warn_on_exit_check.isChecked():
                reply = QMessageBox.question(self, "Quit",
                    "Bot is running. Stop and quit?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if reply == QMessageBox.Yes:
                    self.stop_bot()
                    event.accept()
                else:
                    event.ignore()
            else:
                self.stop_bot()
                event.accept()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)

    app.setStyle('Fusion')

    window = TwitchTTSGUI()
    window.show()

    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
