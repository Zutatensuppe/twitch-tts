"""
Twitch TTS Bot GUI using PySide6 (Qt)
Full Unicode/emoji support, native look on all platforms
"""

import sys
import os
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
    QDialogButtonBox, QTextBrowser
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QFont, QColor, QTextCharFormat, QAction

from . import conf
from . import constants
from . import run as bot_runner


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
        # Also write to original stdout (console)
        self.original_stdout.write(text)
        
        # Send to GUI
        if text.strip():  # Only send non-empty lines
            self.signal.log_message.emit('OUTPUT', text.rstrip())

    def flush(self):
        self.original_stdout.flush()


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
        
        # Setup logging
        self.log_signal = LogSignal()
        self.log_signal.log_message.connect(self.append_log)
        self.setup_logging()
        
        # Create UI
        self.create_menu()
        self.create_ui()
        
        # Load config
        self.load_config()
        
        # Load GUI settings and handle autostart
        self.load_gui_settings()
        if self.autostart_check.isChecked():
            # Use QTimer to start bot after GUI is fully loaded
            QTimer.singleShot(500, self.start_bot)

    def create_menu(self):
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def create_ui(self):
        # Central widget with tabs
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Tab widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # Create tabs
        self.tabs.addTab(self.create_control_tab(), "Control")
        self.tabs.addTab(self.create_config_tab(), "Configuration")
        self.tabs.addTab(self.create_logs_tab(), "Logs")

    def create_control_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Status group
        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout(status_group)
        
        self.status_label = QLabel("Bot Status: Stopped")
        self.status_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.status_label.setAlignment(Qt.AlignCenter)
        status_layout.addWidget(self.status_label)
        
        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("font-size: 24px; color: red;")
        self.status_indicator.setAlignment(Qt.AlignCenter)
        status_layout.addWidget(self.status_indicator)
        
        self.info_label = QLabel("")
        self.info_label.setAlignment(Qt.AlignCenter)
        status_layout.addWidget(self.info_label)
        
        layout.addWidget(status_group)
        
        # Controls group
        controls_group = QGroupBox("Controls")
        controls_layout = QVBoxLayout(controls_group)
        
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Bot")
        self.start_button.clicked.connect(self.start_bot)
        button_layout.addWidget(self.start_button)
        
        self.stop_button = QPushButton("Stop Bot")
        self.stop_button.clicked.connect(self.stop_bot)
        self.stop_button.setEnabled(False)
        button_layout.addWidget(self.stop_button)
        controls_layout.addLayout(button_layout)
        
        # Options
        self.autostart_check = QCheckBox("Auto-start bot when application launches")
        self.autostart_check.setChecked(False)
        controls_layout.addWidget(self.autostart_check)
        
        self.warn_on_exit_check = QCheckBox("Warn before closing if bot is running")
        self.warn_on_exit_check.setChecked(True)
        controls_layout.addWidget(self.warn_on_exit_check)
        
        layout.addWidget(controls_group)
        
        # Stats group
        stats_group = QGroupBox("Statistics")
        stats_layout = QVBoxLayout(stats_group)
        
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        stats_layout.addWidget(self.stats_text)
        
        layout.addWidget(stats_group)
        
        return widget

    def create_config_tab(self):
        # Common language codes reference for help texts
        lang_codes_help = '''<br><br><b>Common language codes:</b>
<table>
<tr><td>en = English</td><td>ja = Japanese</td><td>ko = Korean</td></tr>
<tr><td>zh-cn = Chinese (Simplified)</td><td>zh-tw = Chinese (Traditional)</td><td>th = Thai</td></tr>
<tr><td>de = German</td><td>fr = French</td><td>es = Spanish</td></tr>
<tr><td>pt = Portuguese</td><td>it = Italian</td><td>nl = Dutch</td></tr>
<tr><td>ru = Russian</td><td>uk = Ukrainian</td><td>pl = Polish</td></tr>
<tr><td>sv = Swedish</td><td>no = Norwegian</td><td>fi = Finnish</td></tr>
<tr><td>ar = Arabic</td><td>hi = Hindi</td><td>vi = Vietnamese</td></tr>
<tr><td>id = Indonesian</td><td>tl = Filipino</td><td>tr = Turkish</td></tr>
</table>'''

        # Help texts for config fields - user-friendly descriptions, only original links
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
            'lang_TransToHome': '<b>Translate to Home Language</b><br><br>Language code to translate incoming messages TO (your home language).' + lang_codes_help,
            'lang_HomeToOther': '<b>Home to Other Language</b><br><br>Language code to translate FROM your home language to another language.' + lang_codes_help,
            'lang_Default': '<b>Default Language</b><br><br>Default language that is used when no language could or should be detected.<br><br>It is also the default language that text is read in if a detected language is not supported for reading.' + lang_codes_help,
            'lang_SkipDetect': '<b>Skip Language Detection</b><br><br>If enabled, the default language will be used for all texts. No automatic detection of the language will happen.',
            'TTS_IN': '<b>TTS for User Messages</b><br><br>If enabled, user input messages will be read aloud by TTS voice.',
            'TTS_OUT': '<b>TTS for Bot Output</b><br><br>If enabled, bot output (translated) messages will be read aloud by TTS voice.',
            'ReadOnlyTheseLang': '<b>TTS Only for These Languages</b><br><br>If you want TTS for only certain languages, add language codes here.<br><br>For example, \'ja\' means Japanese only, \'ko,en\' means Korean and English are read aloud.<br>Leave empty for all languages.' + lang_codes_help,
            'Ignore_Lang': '<b>Ignore Languages</b><br><br>Do not translate messages detected as these languages (comma-separated codes).' + lang_codes_help,
            'Ignore_Users': '<b>Ignore Users</b><br><br>Do not process messages from these users (comma-separated, case-insensitive).',
            'Ignore_Line': '<b>Ignore Lines</b><br><br>Do not process messages containing these phrases (comma-separated).',
            'Delete_Words': '<b>Delete Words</b><br><br>Remove these words/phrases from messages before processing (comma-separated).<br><br>Supports Unicode including emoji.',
            'Delete_Links': '<b>Delete Links</b><br><br>Set to the desired string that links are replaced with.<br><br>Leave empty if no replacement should happen.',
            'Ignore_Links': '<b>Ignore All Links</b><br><br>If enabled, all URLs will be removed from messages before processing.',
            'Ignore_Emojis': '<b>Ignore All Emojis</b><br><br>If enabled, all emoji characters will be removed from messages before processing.',
            'Debug': '<b>Debug Mode</b><br><br>If you encounter any bugs, you can enable debug mode to see error messages in the logs.',
            'Bot_SendWhisper': '<b>Send Startup Message</b><br><br>If enabled, the bot will announce itself in chat when it starts.',
            'Bot_StartupMessage': '<b>Startup Message</b><br><br>The message the bot sends when it joins the channel (if Send Startup Message is enabled).<br><br>The message is sent as-is. Use /me for action style. Default: "/me has landed!"',
            'Trans_TextColor': '<b>Bot Chat Color</b><br><br>Color for the bot\'s chat messages. This is set via /color command when the bot starts.<br><br>Available colors: Blue, Coral, DodgerBlue, SpringGreen, YellowGreen, Green, OrangeRed, Red, GoldenRod, HotPink, CadetBlue, SeaGreen, Chocolate, BlueViolet, and Firebrick',
        }
        
        def create_help_button(field_name, label_text):
            """Create a small ? button that opens help dialog"""
            btn = QPushButton("?")
            btn.setFixedSize(20, 20)
            btn.setToolTip("Click for help")
            btn.clicked.connect(lambda: HelpDialog(self, label_text, self.help_texts[field_name]).exec())
            return btn

        def create_toggle_button(line_edit):
            """Create a small Show/Hide button for password fields"""
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
            """Add a form row with the widget and a ? help button"""
            row_layout = QHBoxLayout()
            row_layout.addWidget(widget, 1)
            row_layout.addWidget(create_help_button(field_name, label_text))
            form_layout.addRow(label_text + ":", row_layout)
        
        # Scroll area for config
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Required settings
        required_group = QGroupBox("Required Settings")
        required_layout = QFormLayout(required_group)
        
        self.config_widgets['Twitch_Channel'] = QLineEdit()
        self.config_widgets['Twitch_Channel'].setPlaceholderText("Channel name (without #)")
        add_field_with_help(required_layout, "Twitch Channel", self.config_widgets['Twitch_Channel'], 'Twitch_Channel')
        
        self.config_widgets['Trans_Username'] = QLineEdit()
        self.config_widgets['Trans_Username'].setPlaceholderText("Your bot's username")
        add_field_with_help(required_layout, "Bot Username", self.config_widgets['Trans_Username'], 'Trans_Username')
        
        oauth_layout = QHBoxLayout()
        self.config_widgets['Trans_OAUTH'] = QLineEdit()
        self.config_widgets['Trans_OAUTH'].setEchoMode(QLineEdit.Password)
        self.config_widgets['Trans_OAUTH'].setPlaceholderText("OAuth token")
        oauth_layout.addWidget(self.config_widgets['Trans_OAUTH'], 1)
        oauth_layout.addWidget(create_toggle_button(self.config_widgets['Trans_OAUTH']))
        oauth_layout.addWidget(create_help_button('Trans_OAUTH', "OAuth Token"))
        required_layout.addRow("OAuth Token:", oauth_layout)
        
        self.config_widgets['YoutubeChannelUrl'] = QLineEdit()
        self.config_widgets['YoutubeChannelUrl'].setPlaceholderText("Optional: https://www.youtube.com/@channel")
        add_field_with_help(required_layout, "YouTube Channel URL", self.config_widgets['YoutubeChannelUrl'], 'YoutubeChannelUrl')
        
        youtube_key_layout = QHBoxLayout()
        self.config_widgets['YoutubeApiKey'] = QLineEdit()
        self.config_widgets['YoutubeApiKey'].setEchoMode(QLineEdit.Password)
        self.config_widgets['YoutubeApiKey'].setPlaceholderText("Optional: YouTube API key")
        youtube_key_layout.addWidget(self.config_widgets['YoutubeApiKey'], 1)
        youtube_key_layout.addWidget(create_toggle_button(self.config_widgets['YoutubeApiKey']))
        youtube_key_layout.addWidget(create_help_button('YoutubeApiKey', "YouTube API Key"))
        required_layout.addRow("YouTube API Key:", youtube_key_layout)
        
        layout.addWidget(required_group)
        
        # Optional settings
        optional_group = QGroupBox("Translation Settings")
        optional_layout = QFormLayout(optional_group)
        
        self.config_widgets['Translator'] = QComboBox()
        self.config_widgets['Translator'].addItems(["google", "deepl"])
        add_field_with_help(optional_layout, "Translator", self.config_widgets['Translator'], 'Translator')
        
        self.config_widgets['GoogleTranslate_suffix'] = QLineEdit()
        self.config_widgets['GoogleTranslate_suffix'].setPlaceholderText("e.g., co.jp, com")
        add_field_with_help(optional_layout, "Google Translate Suffix", self.config_widgets['GoogleTranslate_suffix'], 'GoogleTranslate_suffix')
        
        layout.addWidget(optional_group)
        
        # Language settings
        lang_group = QGroupBox("Language Settings")
        lang_layout = QFormLayout(lang_group)
        
        self.config_widgets['lang_TransToHome'] = QLineEdit()
        self.config_widgets['lang_TransToHome'].setPlaceholderText("e.g., en, ja, uk")
        add_field_with_help(lang_layout, "Translate to Home Lang", self.config_widgets['lang_TransToHome'], 'lang_TransToHome')
        
        self.config_widgets['lang_HomeToOther'] = QLineEdit()
        add_field_with_help(lang_layout, "Home to Other Lang", self.config_widgets['lang_HomeToOther'], 'lang_HomeToOther')
        
        self.config_widgets['lang_Default'] = QLineEdit()
        add_field_with_help(lang_layout, "Default Language", self.config_widgets['lang_Default'], 'lang_Default')
        
        skip_detect_layout = QHBoxLayout()
        self.config_widgets['lang_SkipDetect'] = QCheckBox("Skip Language Detection (use default for all)")
        skip_detect_layout.addWidget(self.config_widgets['lang_SkipDetect'])
        skip_detect_layout.addWidget(create_help_button('lang_SkipDetect', "Skip Language Detection"))
        skip_detect_layout.addStretch()
        lang_layout.addRow("", skip_detect_layout)
        
        layout.addWidget(lang_group)
        
        # TTS settings
        tts_group = QGroupBox("Text-to-Speech Settings")
        tts_layout = QFormLayout(tts_group)
        
        tts_check_layout = QHBoxLayout()
        self.config_widgets['TTS_IN'] = QCheckBox("TTS for Input (User messages)")
        tts_check_layout.addWidget(self.config_widgets['TTS_IN'])
        tts_check_layout.addWidget(create_help_button('TTS_IN', "TTS for Input"))
        self.config_widgets['TTS_OUT'] = QCheckBox("TTS for Output (Bot messages)")
        tts_check_layout.addWidget(self.config_widgets['TTS_OUT'])
        tts_check_layout.addWidget(create_help_button('TTS_OUT', "TTS for Output"))
        tts_layout.addRow("", tts_check_layout)
        
        self.config_widgets['ReadOnlyTheseLang'] = QLineEdit()
        self.config_widgets['ReadOnlyTheseLang'].setPlaceholderText("Comma-separated, empty = all")
        add_field_with_help(tts_layout, "TTS Only for Languages", self.config_widgets['ReadOnlyTheseLang'], 'ReadOnlyTheseLang')
        
        layout.addWidget(tts_group)
        
        # Advanced settings
        advanced_group = QGroupBox("Advanced Settings")
        advanced_layout = QFormLayout(advanced_group)
        
        self.config_widgets['Ignore_Lang'] = QLineEdit()
        self.config_widgets['Ignore_Lang'].setPlaceholderText("Comma-separated language codes")
        add_field_with_help(advanced_layout, "Ignore Languages", self.config_widgets['Ignore_Lang'], 'Ignore_Lang')
        
        self.config_widgets['Ignore_Users'] = QLineEdit()
        self.config_widgets['Ignore_Users'].setPlaceholderText("Comma-separated usernames")
        add_field_with_help(advanced_layout, "Ignore Users", self.config_widgets['Ignore_Users'], 'Ignore_Users')
        
        self.config_widgets['Ignore_Line'] = QLineEdit()
        self.config_widgets['Ignore_Line'].setPlaceholderText("Comma-separated phrases")
        add_field_with_help(advanced_layout, "Ignore Lines", self.config_widgets['Ignore_Line'], 'Ignore_Line')
        
        self.config_widgets['Delete_Words'] = QLineEdit()
        self.config_widgets['Delete_Words'].setPlaceholderText("Comma-separated (supports emoji: 🫘, まめ)")
        add_field_with_help(advanced_layout, "Delete Words", self.config_widgets['Delete_Words'], 'Delete_Words')
        
        self.config_widgets['Delete_Links'] = QLineEdit()
        self.config_widgets['Delete_Links'].setPlaceholderText("Replacement text for URLs (empty = remove)")
        add_field_with_help(advanced_layout, "Delete Links", self.config_widgets['Delete_Links'], 'Delete_Links')
        
        # Ignore checkboxes
        ignore_layout = QHBoxLayout()
        self.config_widgets['Ignore_Links'] = QCheckBox("Ignore All Links")
        ignore_layout.addWidget(self.config_widgets['Ignore_Links'])
        ignore_layout.addWidget(create_help_button('Ignore_Links', "Ignore All Links"))
        self.config_widgets['Ignore_Emojis'] = QCheckBox("Ignore All Emojis")
        ignore_layout.addWidget(self.config_widgets['Ignore_Emojis'])
        ignore_layout.addWidget(create_help_button('Ignore_Emojis', "Ignore All Emojis"))
        advanced_layout.addRow("", ignore_layout)
        
        self.config_widgets['Debug'] = QCheckBox("Debug Mode")
        advanced_layout.addRow("", self.config_widgets['Debug'])
        
        layout.addWidget(advanced_group)
        
        # Bot Settings (startup announcement)
        bot_group = QGroupBox("Bot Settings")
        bot_layout = QFormLayout(bot_group)
        
        self.config_widgets['Bot_SendWhisper'] = QCheckBox("Send Startup Message")
        bot_layout.addRow("", self.config_widgets['Bot_SendWhisper'])
        
        self.config_widgets['Bot_StartupMessage'] = QLineEdit()
        self.config_widgets['Bot_StartupMessage'].setPlaceholderText("/me has landed!")
        add_field_with_help(bot_layout, "Startup Message", self.config_widgets['Bot_StartupMessage'], 'Bot_StartupMessage')
        
        self.config_widgets['Trans_TextColor'] = QComboBox()
        self.config_widgets['Trans_TextColor'].addItems([
            "Blue", "Coral", "DodgerBlue", "SpringGreen", "YellowGreen", "Green",
            "OrangeRed", "Red", "GoldenRod", "HotPink", "CadetBlue", "SeaGreen",
            "Chocolate", "BlueViolet", "Firebrick"
        ])
        add_field_with_help(bot_layout, "Bot Chat Color", self.config_widgets['Trans_TextColor'], 'Trans_TextColor')
        
        layout.addWidget(bot_group)
        
        # Buttons and status
        button_layout = QHBoxLayout()
        
        load_btn = QPushButton("Load Config")
        load_btn.clicked.connect(self.load_config)
        button_layout.addWidget(load_btn)
        
        self.save_btn = QPushButton("Save Config")
        self.save_btn.clicked.connect(self.save_config)
        button_layout.addWidget(self.save_btn)
        
        # Validate button hidden for now (validation still happens on save)
        # validate_btn = QPushButton("Validate")
        # validate_btn.clicked.connect(lambda: self.validate_config(show_success=True))
        # button_layout.addWidget(validate_btn)
        
        layout.addLayout(button_layout)
        
        # Status label for save feedback
        self.config_status_label = QLabel("")
        self.config_status_label.setStyleSheet("color: green; font-weight: bold;")
        layout.addWidget(self.config_status_label)
        
        layout.addStretch()
        
        scroll.setWidget(widget)
        return scroll

    def create_logs_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Controls
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
        
        # Log display
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Monospace", 9))
        layout.addWidget(self.log_text)
        
        return widget

    def setup_logging(self):
        # Setup logging handler
        self.log_handler = LogHandler(self.log_signal)
        self.log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(self.log_handler)
        logging.getLogger().setLevel(logging.INFO)
        
        # Redirect stdout to capture print() statements from the bot
        self.stdout_redirector = StdoutRedirector(self.log_signal)
        sys.stdout = self.stdout_redirector

    def update_log_format(self):
        """Toggle between simple and verbose log format"""
        if self.verbose_logs_check.isChecked():
            # Verbose format with namespace
            self.log_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        else:
            # Simple format
            self.log_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s'))

    def append_log(self, level, message):
        colors = {
            'INFO': 'black',
            'WARNING': 'orange',
            'ERROR': 'red',
            'DEBUG': 'gray',
            'CRITICAL': 'darkred',
            'OUTPUT': '#0066cc'  # Blue for bot output (print statements)
        }
        color = colors.get(level, 'black')
        
        # Escape HTML entities in message
        import html
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

    def load_config(self):
        config_path = os.path.join(os.getcwd(), "config.jsonc")
        if not os.path.exists(config_path):
            QMessageBox.warning(self, "No Config", "config.jsonc not found. Using defaults.")
            return
        
        try:
            with open(config_path, encoding='utf-8') as f:
                self.config_data = commentjson.load(f)
            self.populate_config_fields()
            logging.info("Configuration loaded successfully")
        except Exception as e:
            logging.error(f"Failed to load config: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to load config: {str(e)}")

    def populate_config_fields(self):
        # String fields
        string_fields = [
            'Twitch_Channel', 'Trans_Username', 'Trans_OAUTH',
            'YoutubeChannelUrl', 'YoutubeApiKey', 'lang_TransToHome',
            'lang_HomeToOther', 'lang_Default', 'GoogleTranslate_suffix',
            'Bot_StartupMessage'
        ]
        for field in string_fields:
            if field in self.config_data and field in self.config_widgets:
                self.config_widgets[field].setText(str(self.config_data.get(field, '')))
        
        # Combobox fields
        if 'Translator' in self.config_data:
            idx = self.config_widgets['Translator'].findText(self.config_data['Translator'])
            if idx >= 0:
                self.config_widgets['Translator'].setCurrentIndex(idx)
        
        if 'Trans_TextColor' in self.config_data:
            idx = self.config_widgets['Trans_TextColor'].findText(self.config_data['Trans_TextColor'])
            if idx >= 0:
                self.config_widgets['Trans_TextColor'].setCurrentIndex(idx)
        
        # Boolean fields
        bool_fields = {
            'lang_SkipDetect': False,
            'TTS_IN': True, 'TTS_OUT': False, 'Debug': False, 'Bot_SendWhisper': False,
            'Ignore_Links': False, 'Ignore_Emojis': False
        }
        for field, default in bool_fields.items():
            if field in self.config_widgets:
                self.config_widgets[field].setChecked(self.config_data.get(field, default))
        
        # List fields (comma-separated)
        list_fields = ['Ignore_Lang', 'Ignore_Users', 'Ignore_Line', 'Delete_Words', 'ReadOnlyTheseLang']
        for field in list_fields:
            if field in self.config_data and field in self.config_widgets:
                if isinstance(self.config_data[field], list):
                    self.config_widgets[field].setText(', '.join(self.config_data[field]))
        
        # Delete_Links
        if 'Delete_Links' in self.config_data:
            self.config_widgets['Delete_Links'].setText(str(self.config_data.get('Delete_Links', '')))

    def save_config(self):
        if not self.validate_config(show_success=False):
            return
        
        config_path = os.path.join(os.getcwd(), "config.jsonc")
        
        # Remember old channel to detect changes
        old_channel = self.config_data.get('Twitch_Channel', '')
        
        config = {}
        
        # String fields
        string_fields = [
            'Twitch_Channel', 'Trans_Username', 'Trans_OAUTH',
            'YoutubeChannelUrl', 'YoutubeApiKey', 'lang_TransToHome',
            'lang_HomeToOther', 'lang_Default', 'GoogleTranslate_suffix',
            'Bot_StartupMessage'
        ]
        for field in string_fields:
            if field in self.config_widgets:
                config[field] = self.config_widgets[field].text()
        
        # Combobox fields
        config['Translator'] = self.config_widgets['Translator'].currentText()
        config['Trans_TextColor'] = self.config_widgets['Trans_TextColor'].currentText()
        
        # Boolean fields
        bool_fields = ['lang_SkipDetect', 
                      'TTS_IN', 'TTS_OUT', 'Debug', 'Bot_SendWhisper',
                      'Ignore_Links', 'Ignore_Emojis']
        for field in bool_fields:
            if field in self.config_widgets:
                config[field] = self.config_widgets[field].isChecked()
        
        # List fields
        list_fields = ['Ignore_Lang', 'Ignore_Users', 'Ignore_Line', 'Delete_Words', 'ReadOnlyTheseLang']
        for field in list_fields:
            if field in self.config_widgets:
                text = self.config_widgets[field].text().strip()
                config[field] = [x.strip() for x in text.split(',')] if text else []
        
        # Special fields
        config['Delete_Links'] = self.config_widgets['Delete_Links'].text()
        config['AssignRandomLangToUser'] = self.config_data.get('AssignRandomLangToUser', [])
        config['UserToLangMap'] = self.config_data.get('UserToLangMap', {})
        
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                commentjson.dump(config, f, indent=2, ensure_ascii=False)
            self.config_data = config
            logging.info("Configuration saved successfully")
            
            # Re-read config to refresh UI (as if program just launched)
            self.load_config()

            # Reload runtime config for running bot
            if self.bot_running:
                bot_runner.reload_config()
            
            # If channel changed and bot is running, restart it
            new_channel = config.get('Twitch_Channel', '')
            if old_channel != new_channel and self.bot_running:
                logging.info(f"Channel changed from '{old_channel}' to '{new_channel}', restarting bot...")
                self.stop_bot()
                # Restart after bot thread has fully stopped
                QTimer.singleShot(200, self._start_bot_when_ready)
            
            # Show success in status label (no popup)
            self.config_status_label.setText("✓ Config saved")
            self.config_status_label.setStyleSheet("color: green; font-weight: bold;")
            # Clear status after 3 seconds
            QTimer.singleShot(3000, lambda: self.config_status_label.setText(""))
        except Exception as e:
            logging.error(f"Failed to save config: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to save config: {str(e)}")

    def validate_config(self, show_success=True):
        """Validate config. Only show feedback on success if show_success=True"""
        errors = []
        
        if not self.config_widgets['Twitch_Channel'].text().strip():
            errors.append("Twitch Channel is required")
        
        if not self.config_widgets['Trans_Username'].text().strip():
            errors.append("Bot Username is required")
        
        if not self.config_widgets['Trans_OAUTH'].text().strip():
            errors.append("OAuth Token is required")
        
        if errors:
            self.config_status_label.setText("✗ " + "; ".join(errors))
            self.config_status_label.setStyleSheet("color: red; font-weight: bold;")
            return False
        
        if show_success:
            self.config_status_label.setText("✓ Configuration is valid")
            self.config_status_label.setStyleSheet("color: green; font-weight: bold;")
            QTimer.singleShot(3000, lambda: self.config_status_label.setText(""))
        return True

    def start_bot(self):
        if self.bot_thread and self.bot_thread.is_alive():
            logging.info("Bot is still shutting down; please wait")
            return
        if self.bot_running:
            QMessageBox.warning(self, "Already Running", "Bot is already running")
            return
        
        # Validate without popup
        if not self.validate_config(show_success=False):
            return
        
        self.bot_thread = threading.Thread(target=self.run_bot, daemon=True)
        self.bot_thread.start()
        
        self.bot_running = True
        self.update_status(True)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
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
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
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
            # Use QTimer to update UI from main thread
            QTimer.singleShot(0, lambda: self.update_status(False))
            QTimer.singleShot(0, lambda: self.start_button.setEnabled(True))
            QTimer.singleShot(0, lambda: self.stop_button.setEnabled(False))
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
            self.status_label.setText("Bot Status: Running")
            self.status_indicator.setStyleSheet("font-size: 24px; color: green;")
            channel = self.config_widgets['Twitch_Channel'].text()
            username = self.config_widgets['Trans_Username'].text()
            self.info_label.setText(f"Channel: {channel} | Bot: {username}")
            self.update_stats()
        else:
            self.status_label.setText("Bot Status: Stopped")
            self.status_indicator.setStyleSheet("font-size: 24px; color: red;")
            self.info_label.setText("")

    def update_stats(self):
        if self.bot_running:
            stats = f"Bot running since: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            stats += f"Configuration loaded\n"
            stats += f"Monitoring channel: {self.config_widgets['Twitch_Channel'].text()}\n"
            self.stats_text.setPlainText(stats)

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

    def load_gui_settings(self):
        """Load GUI-specific settings (autostart, etc.)"""
        settings_path = os.path.join(os.getcwd(), ".tts_gui_settings.json")
        try:
            if os.path.exists(settings_path):
                import json
                with open(settings_path, 'r') as f:
                    settings = json.load(f)
                self.autostart_check.setChecked(settings.get('autostart', False))
                self.auto_scroll_check.setChecked(settings.get('auto_scroll', True))
                self.verbose_logs_check.setChecked(settings.get('verbose_logs', False))
                self.warn_on_exit_check.setChecked(settings.get('warn_on_exit', True))
                if settings.get('verbose_logs', False):
                    self.update_log_format()
        except:
            pass

    def save_gui_settings(self):
        """Save GUI-specific settings"""
        settings_path = os.path.join(os.getcwd(), ".tts_gui_settings.json")
        try:
            import json
            settings = {
                'autostart': self.autostart_check.isChecked(),
                'auto_scroll': self.auto_scroll_check.isChecked(),
                'verbose_logs': self.verbose_logs_check.isChecked(),
                'warn_on_exit': self.warn_on_exit_check.isChecked(),
            }
            with open(settings_path, 'w') as f:
                json.dump(settings, f)
        except:
            pass

    def closeEvent(self, event):
        # Save GUI settings
        self.save_gui_settings()
        
        # Restore stdout
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
                # No warning, just stop and quit
                self.stop_bot()
                event.accept()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    
    # Set application style for native look
    app.setStyle('Fusion')
    
    window = TwitchTTSGUI()
    window.show()
    
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
