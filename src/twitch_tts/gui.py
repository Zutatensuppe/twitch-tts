import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import threading
import queue
import logging
import os
import asyncio
import commentjson
from datetime import datetime
from . import conf
from . import constants
from . import run as bot_runner


class TextHandler(logging.Handler):
    """Logging handler that sends logs to a queue for GUI display"""
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        msg = self.format(record)
        self.log_queue.put((record.levelname, msg))


class TwitchTTSGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Twitch TTS Bot")
        self.root.geometry("900x700")
        
        # Apply modern theme - must be done before creating widgets
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except:
            pass  # Use default if clam not available
        
        # For CJK/Unicode support, use a generic font that triggers system fallback
        # On Linux, "Sans" or "Helvetica" will use fontconfig to find appropriate glyphs
        # This allows rendering Japanese, emoji, etc. through font substitution
        import sys
        if sys.platform.startswith('linux'):
            # Use Sans which fontconfig will map to appropriate fonts
            self.ui_font_name = 'Sans'
        elif sys.platform == 'darwin':
            self.ui_font_name = 'Helvetica'
        else:
            # Windows - Segoe UI has good Unicode coverage
            self.ui_font_name = 'Segoe UI'
        
        self.ui_font = (self.ui_font_name, 10)
        
        # Configure ttk styles with the font
        style.configure('.', font=self.ui_font)
        style.configure('TLabel', font=self.ui_font)
        style.configure('TButton', font=self.ui_font, padding=5)
        style.configure('TCheckbutton', font=self.ui_font)
        style.configure('TRadiobutton', font=self.ui_font)
        style.configure('TLabelframe.Label', font=(self.ui_font_name, 10, 'bold'))
        style.configure('TNotebook.Tab', font=self.ui_font, padding=[10, 5])
        
        # State
        self.config_data = {}
        self.bot_thread = None
        self.bot_running = False
        self.log_queue = queue.Queue()
        
        # Setup logging handler
        self.setup_logging()
        
        # Create menu bar
        self.create_menu()
        
        # Create notebook (tabs)
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Create tabs
        self.create_control_tab()
        self.create_config_tab()
        self.create_logs_tab()
        
        # Load existing config
        self.load_config()
        
        # Start log update loop
        self.update_logs()

    def create_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Exit", command=self.on_closing)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)
        help_menu.add_command(label="OAuth Help", command=self.show_oauth_help)

    def create_control_tab(self):
        """Control tab with start/stop and status"""
        control_frame = ttk.Frame(self.notebook)
        self.notebook.add(control_frame, text="Control")
        
        # Status section
        status_frame = ttk.LabelFrame(control_frame, text="Status", padding=10)
        status_frame.pack(fill='x', padx=10, pady=10)
        
        self.status_label = ttk.Label(status_frame, text="Bot Status: Stopped", 
                                      font=(self.ui_font_name, 12, 'bold'))
        self.status_label.pack()
        
        self.status_indicator = tk.Canvas(status_frame, width=30, height=30)
        self.status_indicator.pack(pady=5)
        self.status_circle = self.status_indicator.create_oval(5, 5, 25, 25, fill='red')
        
        self.info_label = ttk.Label(status_frame, text="", font=(self.ui_font_name, 9))
        self.info_label.pack(pady=5)
        
        # Controls section
        controls_frame = ttk.LabelFrame(control_frame, text="Controls", padding=10)
        controls_frame.pack(fill='x', padx=10, pady=10)
        
        button_frame = ttk.Frame(controls_frame)
        button_frame.pack()
        
        self.start_button = ttk.Button(button_frame, text="Start Bot", command=self.start_bot, width=15)
        self.start_button.pack(side='left', padx=5)
        
        self.stop_button = ttk.Button(button_frame, text="Stop Bot", command=self.stop_bot, 
                                      width=15, state='disabled')
        self.stop_button.pack(side='left', padx=5)
        
        # Statistics section
        stats_frame = ttk.LabelFrame(control_frame, text="Statistics", padding=10)
        stats_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        self.stats_text = scrolledtext.ScrolledText(stats_frame, height=15, state='disabled', wrap='word',
                                                     font=self.ui_font)
        self.stats_text.pack(fill='both', expand=True)

    def create_config_tab(self):
        """Configuration tab with all settings"""
        config_frame = ttk.Frame(self.notebook)
        self.notebook.add(config_frame, text="Configuration")
        
        # Initialize widget references dictionary first
        self.config_widgets = {}
        
        # Create canvas and scrollbar for scrollable config
        canvas = tk.Canvas(config_frame)
        scrollbar = ttk.Scrollbar(config_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Required settings
        self.create_required_section(scrollable_frame)
        
        # Optional settings
        self.create_optional_section(scrollable_frame)
        
        # Language settings
        self.create_language_section(scrollable_frame)
        
        # TTS settings
        self.create_tts_section(scrollable_frame)
        
        # Advanced settings
        self.create_advanced_section(scrollable_frame)
        
        # Buttons
        button_frame = ttk.Frame(scrollable_frame)
        button_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Button(button_frame, text="Load Config", command=self.load_config).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Save Config", command=self.save_config).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Validate", command=self.validate_config).pack(side='left', padx=5)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def create_required_section(self, parent):
        """Required configuration fields"""
        frame = ttk.LabelFrame(parent, text="Required Settings", padding=10)
        frame.pack(fill='x', padx=10, pady=5)
        
        self.config_widgets['Twitch_Channel'] = self.create_field(frame, "Twitch Channel:", 0, 
            "The Twitch channel name to monitor (without #)")
        self.config_widgets['Trans_Username'] = self.create_field(frame, "Bot Username:", 1,
            "Your Twitch bot account username")
        
        oauth_frame = ttk.Frame(frame)
        oauth_frame.grid(row=2, column=0, columnspan=2, sticky='ew', pady=2)
        ttk.Label(oauth_frame, text="OAuth Token:").pack(side='left')
        self.config_widgets['Trans_OAUTH'] = tk.Entry(oauth_frame, show='*', width=40, font=self.ui_font)
        self.config_widgets['Trans_OAUTH'].pack(side='left', padx=5, fill='x', expand=True)
        ttk.Button(oauth_frame, text="Help", command=self.show_oauth_help).pack(side='left')
        
        self.config_widgets['YoutubeChannelUrl'] = self.create_field(frame, "YouTube Channel URL:", 3,
            "Optional: YouTube channel URL (e.g., https://www.youtube.com/@channel)")
        self.config_widgets['YoutubeApiKey'] = self.create_field(frame, "YouTube API Key:", 4,
            "Optional: YouTube API key for live chat")

    def create_optional_section(self, parent):
        """Optional configuration fields"""
        frame = ttk.LabelFrame(parent, text="Optional Settings", padding=10)
        frame.pack(fill='x', padx=10, pady=5)
        
        # Text color
        color_frame = ttk.Frame(frame)
        color_frame.grid(row=0, column=0, columnspan=2, sticky='ew', pady=2)
        ttk.Label(color_frame, text="Text Color:").pack(side='left')
        self.config_widgets['Trans_TextColor'] = ttk.Combobox(color_frame, width=15, font=self.ui_font, values=[
            "Blue", "Coral", "DodgerBlue", "SpringGreen", "YellowGreen", "Green",
            "OrangeRed", "Red", "GoldenRod", "HotPink", "CadetBlue", "SeaGreen",
            "Chocolate", "BlueViolet", "Firebrick"
        ])
        self.config_widgets['Trans_TextColor'].pack(side='left', padx=5)
        
        # Show options
        show_frame = ttk.Frame(frame)
        show_frame.grid(row=1, column=0, columnspan=2, sticky='ew', pady=2)
        self.config_widgets['Show_ByName'] = tk.BooleanVar()
        ttk.Checkbutton(show_frame, text="Show by Name", variable=self.config_widgets['Show_ByName']).pack(side='left', padx=10)
        self.config_widgets['Show_ByLang'] = tk.BooleanVar()
        ttk.Checkbutton(show_frame, text="Show by Language", variable=self.config_widgets['Show_ByLang']).pack(side='left', padx=10)
        
        # Translator selection
        trans_frame = ttk.Frame(frame)
        trans_frame.grid(row=2, column=0, columnspan=2, sticky='ew', pady=2)
        ttk.Label(trans_frame, text="Translator:").pack(side='left')
        self.config_widgets['Translator'] = ttk.Combobox(trans_frame, width=15, values=["google", "deepl"], font=self.ui_font)
        self.config_widgets['Translator'].pack(side='left', padx=5)
        
        # Google Translate suffix
        suffix_frame = ttk.Frame(frame)
        suffix_frame.grid(row=3, column=0, columnspan=2, sticky='ew', pady=2)
        ttk.Label(suffix_frame, text="Google Translate Suffix:").pack(side='left')
        self.config_widgets['GoogleTranslate_suffix'] = tk.Entry(suffix_frame, width=15, font=self.ui_font)
        self.config_widgets['GoogleTranslate_suffix'].pack(side='left', padx=5)
        ttk.Label(suffix_frame, text="(e.g., co.jp, com)").pack(side='left')

    def create_language_section(self, parent):
        """Language configuration fields"""
        frame = ttk.LabelFrame(parent, text="Language Settings", padding=10)
        frame.pack(fill='x', padx=10, pady=5)
        
        self.config_widgets['lang_TransToHome'] = self.create_field(frame, "Translate to Home Lang:", 0,
            "Language code for home language (e.g., en, ja, uk)")
        self.config_widgets['lang_HomeToOther'] = self.create_field(frame, "Home to Other Lang:", 1,
            "Language code for other language")
        self.config_widgets['lang_Default'] = self.create_field(frame, "Default Language:", 2,
            "Default language code when detection fails")
        
        skip_frame = ttk.Frame(frame)
        skip_frame.grid(row=3, column=0, columnspan=2, sticky='ew', pady=2)
        self.config_widgets['lang_SkipDetect'] = tk.BooleanVar()
        ttk.Checkbutton(skip_frame, text="Skip Language Detection (use default for all)", 
                       variable=self.config_widgets['lang_SkipDetect']).pack(side='left')

    def create_tts_section(self, parent):
        """TTS configuration fields"""
        frame = ttk.LabelFrame(parent, text="Text-to-Speech Settings", padding=10)
        frame.pack(fill='x', padx=10, pady=5)
        
        tts_frame = ttk.Frame(frame)
        tts_frame.pack(fill='x')
        
        self.config_widgets['TTS_IN'] = tk.BooleanVar()
        ttk.Checkbutton(tts_frame, text="TTS for Input (User messages)", 
                       variable=self.config_widgets['TTS_IN']).pack(side='left', padx=10)
        
        self.config_widgets['TTS_OUT'] = tk.BooleanVar()
        ttk.Checkbutton(tts_frame, text="TTS for Output (Bot messages)", 
                       variable=self.config_widgets['TTS_OUT']).pack(side='left', padx=10)
        
        # Read only these languages
        read_frame = ttk.Frame(frame)
        read_frame.pack(fill='x', pady=5)
        ttk.Label(read_frame, text="TTS Only for Languages (comma-separated, empty = all):").pack(side='left')
        self.config_widgets['ReadOnlyTheseLang'] = tk.Entry(read_frame, width=30, font=self.ui_font)
        self.config_widgets['ReadOnlyTheseLang'].pack(side='left', padx=5)

    def create_advanced_section(self, parent):
        """Advanced configuration fields"""
        frame = ttk.LabelFrame(parent, text="Advanced Settings", padding=10)
        frame.pack(fill='x', padx=10, pady=5)
        
        # Ignore settings
        ttk.Label(frame, text="Ignore Languages (comma-separated):").grid(row=0, column=0, sticky='w', pady=2)
        self.config_widgets['Ignore_Lang'] = tk.Entry(frame, width=50, font=self.ui_font)
        self.config_widgets['Ignore_Lang'].grid(row=0, column=1, sticky='ew', pady=2, padx=5)
        
        ttk.Label(frame, text="Ignore Users (comma-separated):").grid(row=1, column=0, sticky='w', pady=2)
        self.config_widgets['Ignore_Users'] = tk.Entry(frame, width=50, font=self.ui_font)
        self.config_widgets['Ignore_Users'].grid(row=1, column=1, sticky='ew', pady=2, padx=5)
        
        ttk.Label(frame, text="Ignore Lines (comma-separated):").grid(row=2, column=0, sticky='w', pady=2)
        self.config_widgets['Ignore_Line'] = tk.Entry(frame, width=50, font=self.ui_font)
        self.config_widgets['Ignore_Line'].grid(row=2, column=1, sticky='ew', pady=2, padx=5)
        
        ttk.Label(frame, text="Delete Words (comma-separated):").grid(row=3, column=0, sticky='w', pady=2)
        self.config_widgets['Delete_Words'] = tk.Entry(frame, width=50, font=self.ui_font)
        self.config_widgets['Delete_Words'].grid(row=3, column=1, sticky='ew', pady=2, padx=5)
        
        ttk.Label(frame, text="Delete Links (replacement text):").grid(row=4, column=0, sticky='w', pady=2)
        self.config_widgets['Delete_Links'] = tk.Entry(frame, width=50, font=self.ui_font)
        self.config_widgets['Delete_Links'].grid(row=4, column=1, sticky='ew', pady=2, padx=5)
        
        # Debug and whisper
        check_frame = ttk.Frame(frame)
        check_frame.grid(row=5, column=0, columnspan=2, sticky='ew', pady=5)
        
        self.config_widgets['Debug'] = tk.BooleanVar()
        ttk.Checkbutton(check_frame, text="Debug Mode", 
                       variable=self.config_widgets['Debug']).pack(side='left', padx=10)
        
        self.config_widgets['Bot_SendWhisper'] = tk.BooleanVar()
        ttk.Checkbutton(check_frame, text="Send Whisper Messages", 
                       variable=self.config_widgets['Bot_SendWhisper']).pack(side='left', padx=10)

    def create_logs_tab(self):
        """Logs tab with real-time log viewing"""
        logs_frame = ttk.Frame(self.notebook)
        self.notebook.add(logs_frame, text="Logs")
        
        # Controls
        controls_frame = ttk.Frame(logs_frame)
        controls_frame.pack(fill='x', padx=5, pady=5)
        
        self.auto_scroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls_frame, text="Auto-scroll", variable=self.auto_scroll_var).pack(side='left', padx=5)
        ttk.Button(controls_frame, text="Clear Logs", command=self.clear_logs).pack(side='left', padx=5)
        ttk.Button(controls_frame, text="Save Logs", command=self.save_logs).pack(side='left', padx=5)
        
        # Log display - use Monospace for consistent rendering
        import sys
        if sys.platform.startswith('linux'):
            mono_font = 'Monospace'  # Generic name, fontconfig will handle it
        else:
            mono_font = 'Consolas'
        
        self.log_text = scrolledtext.ScrolledText(logs_frame, height=30, state='disabled', wrap='word',
                                                   font=(mono_font, 9))
        self.log_text.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Configure tags for colored logs
        self.log_text.tag_config('INFO', foreground='black')
        self.log_text.tag_config('WARNING', foreground='orange')
        self.log_text.tag_config('ERROR', foreground='red')
        self.log_text.tag_config('DEBUG', foreground='gray')
        self.log_text.tag_config('CRITICAL', foreground='red', background='yellow')

    def create_field(self, parent, label_text, row, tooltip=""):
        """Helper to create a labeled entry field"""
        ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky='w', pady=2)
        entry = tk.Entry(parent, width=40, font=self.ui_font)
        entry.grid(row=row, column=1, sticky='ew', pady=2, padx=5)
        if tooltip:
            self.create_tooltip(entry, tooltip)
        return entry

    def create_tooltip(self, widget, text):
        """Create a tooltip for a widget"""
        def on_enter(event):
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
            label = ttk.Label(tooltip, text=text, background="lightyellow", relief='solid', borderwidth=1)
            label.pack()
            widget.tooltip = tooltip
        
        def on_leave(event):
            if hasattr(widget, 'tooltip'):
                widget.tooltip.destroy()
                del widget.tooltip
        
        widget.bind('<Enter>', on_enter)
        widget.bind('<Leave>', on_leave)

    def setup_logging(self):
        """Setup logging to capture logs to GUI"""
        handler = TextHandler(self.log_queue)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

    def update_logs(self):
        """Update log display from queue"""
        while not self.log_queue.empty():
            try:
                level, msg = self.log_queue.get_nowait()
                self.log_text.config(state='normal')
                self.log_text.insert('end', msg + '\n', level)
                if self.auto_scroll_var.get():
                    self.log_text.see('end')
                self.log_text.config(state='disabled')
            except queue.Empty:
                break
        
        self.root.after(100, self.update_logs)

    def clear_logs(self):
        """Clear the log display"""
        self.log_text.config(state='normal')
        self.log_text.delete('1.0', 'end')
        self.log_text.config(state='disabled')

    def save_logs(self):
        """Save logs to file"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=f"tts_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.get('1.0', 'end'))
                logging.info(f"Logs saved to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save logs: {str(e)}")

    def load_config(self):
        """Load configuration from config.jsonc"""
        config_path = os.path.join(os.getcwd(), "config.jsonc")
        if not os.path.exists(config_path):
            messagebox.showwarning("No Config", "config.jsonc not found. Using defaults.")
            return
        
        try:
            with open(config_path, encoding='utf-8') as f:
                self.config_data = commentjson.load(f)
            
            # Populate fields
            self.populate_config_fields()
            logging.info("Configuration loaded successfully")
            messagebox.showinfo("Success", "Configuration loaded successfully")
        except Exception as e:
            logging.error(f"Failed to load config: {str(e)}")
            messagebox.showerror("Error", f"Failed to load config: {str(e)}")

    def populate_config_fields(self):
        """Populate GUI fields from config data"""
        # Simple string fields
        string_fields = [
            'Twitch_Channel', 'Trans_Username', 'Trans_OAUTH',
            'YoutubeChannelUrl', 'YoutubeApiKey', 'Trans_TextColor',
            'lang_TransToHome', 'lang_HomeToOther', 'lang_Default',
            'Translator', 'GoogleTranslate_suffix'
        ]
        
        for field in string_fields:
            if field in self.config_data and field in self.config_widgets:
                widget = self.config_widgets[field]
                if isinstance(widget, tk.Entry):
                    widget.delete(0, 'end')
                    widget.insert(0, str(self.config_data[field]))
                elif isinstance(widget, ttk.Combobox):
                    widget.set(str(self.config_data[field]))
        
        # Boolean fields
        bool_fields = {
            'Show_ByName': self.config_data.get('Show_ByName', True),
            'Show_ByLang': self.config_data.get('Show_ByLang', True),
            'lang_SkipDetect': self.config_data.get('lang_SkipDetect', False),
            'TTS_IN': self.config_data.get('TTS_IN', True),
            'TTS_OUT': self.config_data.get('TTS_OUT', False),
            'Debug': self.config_data.get('Debug', False),
            'Bot_SendWhisper': self.config_data.get('Bot_SendWhisper', False),
        }
        
        for field, value in bool_fields.items():
            if field in self.config_widgets:
                self.config_widgets[field].set(value)
        
        # List fields (comma-separated)
        list_fields = ['Ignore_Lang', 'Ignore_Users', 'Ignore_Line', 'Delete_Words', 'ReadOnlyTheseLang']
        for field in list_fields:
            if field in self.config_data and field in self.config_widgets:
                widget = self.config_widgets[field]
                if isinstance(self.config_data[field], list):
                    widget.delete(0, 'end')
                    widget.insert(0, ', '.join(self.config_data[field]))
        
        # Delete_Links special handling
        if 'Delete_Links' in self.config_data and 'Delete_Links' in self.config_widgets:
            self.config_widgets['Delete_Links'].delete(0, 'end')
            self.config_widgets['Delete_Links'].insert(0, str(self.config_data.get('Delete_Links', '')))

    def save_config(self):
        """Save configuration to config.jsonc"""
        if not self.validate_config():
            return
        
        config_path = os.path.join(os.getcwd(), "config.jsonc")
        
        # Build config dict from GUI
        config = {}
        
        # String fields
        string_fields = [
            'Twitch_Channel', 'Trans_Username', 'Trans_OAUTH',
            'YoutubeChannelUrl', 'YoutubeApiKey', 'Trans_TextColor',
            'lang_TransToHome', 'lang_HomeToOther', 'lang_Default',
            'Translator', 'GoogleTranslate_suffix'
        ]
        
        for field in string_fields:
            if field in self.config_widgets:
                widget = self.config_widgets[field]
                if isinstance(widget, (tk.Entry, ttk.Combobox)):
                    config[field] = widget.get()
        
        # Boolean fields
        bool_fields = ['Show_ByName', 'Show_ByLang', 'lang_SkipDetect', 
                      'TTS_IN', 'TTS_OUT', 'Debug', 'Bot_SendWhisper']
        for field in bool_fields:
            if field in self.config_widgets:
                config[field] = self.config_widgets[field].get()
        
        # List fields
        list_fields = ['Ignore_Lang', 'Ignore_Users', 'Ignore_Line', 'Delete_Words', 'ReadOnlyTheseLang']
        for field in list_fields:
            if field in self.config_widgets:
                text = self.config_widgets[field].get().strip()
                if text:
                    config[field] = [x.strip() for x in text.split(',')]
                else:
                    config[field] = []
        
        # Special fields
        config['Delete_Links'] = self.config_widgets['Delete_Links'].get() if self.config_widgets['Delete_Links'].get() else ""
        config['AssignRandomLangToUser'] = self.config_data.get('AssignRandomLangToUser', [])
        config['UserToLangMap'] = self.config_data.get('UserToLangMap', {})
        
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                commentjson.dump(config, f, indent=2)
            
            self.config_data = config
            logging.info("Configuration saved successfully")
            messagebox.showinfo("Success", "Configuration saved successfully")
        except Exception as e:
            logging.error(f"Failed to save config: {str(e)}")
            messagebox.showerror("Error", f"Failed to save config: {str(e)}")

    def validate_config(self):
        """Validate configuration fields"""
        errors = []
        
        # Check required fields
        if not self.config_widgets['Twitch_Channel'].get().strip():
            errors.append("Twitch Channel is required")
        
        if not self.config_widgets['Trans_Username'].get().strip():
            errors.append("Bot Username is required")
        
        if not self.config_widgets['Trans_OAUTH'].get().strip():
            errors.append("OAuth Token is required")
        
        if errors:
            messagebox.showerror("Validation Error", "\n".join(errors))
            return False
        
        messagebox.showinfo("Validation", "Configuration is valid!")
        return True

    def start_bot(self):
        """Start the bot in a separate thread"""
        if self.bot_running:
            messagebox.showwarning("Already Running", "Bot is already running")
            return
        
        if not self.validate_config():
            return
        
        # Save config before starting
        self.save_config()
        
        # Start bot thread
        self.bot_thread = threading.Thread(target=self.run_bot, daemon=True)
        self.bot_thread.start()
        
        self.bot_running = True
        self.update_status(True)
        self.start_button.config(state='disabled')
        self.stop_button.config(state='normal')
        logging.info("Bot started")

    def stop_bot(self):
        """Stop the bot"""
        if not self.bot_running:
            return
        
        try:
            bot_runner.stop_tts()
            self.bot_running = False
            self.update_status(False)
            self.start_button.config(state='normal')
            self.stop_button.config(state='disabled')
            logging.info("Bot stopped")
        except Exception as e:
            logging.error(f"Error stopping bot: {str(e)}")

    def run_bot(self):
        """Run the bot (called in separate thread)"""
        try:
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Now reload and run the bot
            import importlib
            importlib.reload(bot_runner)
            
            bot_runner.start_tts()
            # Use run_bot_core() instead of main() to avoid signal handler issues
            bot_runner.run_bot_core()
        except Exception as e:
            logging.error(f"Bot error: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
            self.bot_running = False
            self.root.after(0, lambda: self.update_status(False))
            self.root.after(0, lambda: self.start_button.config(state='normal'))
            self.root.after(0, lambda: self.stop_button.config(state='disabled'))
        finally:
            # Clean up the event loop
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.stop()
                loop.close()
            except:
                pass

    def update_status(self, running):
        """Update status display"""
        if running:
            self.status_label.config(text="Bot Status: Running")
            self.status_indicator.itemconfig(self.status_circle, fill='green')
            channel = self.config_widgets['Twitch_Channel'].get()
            username = self.config_widgets['Trans_Username'].get()
            self.info_label.config(text=f"Channel: {channel} | Bot: {username}")
            self.update_stats()
        else:
            self.status_label.config(text="Bot Status: Stopped")
            self.status_indicator.itemconfig(self.status_circle, fill='red')
            self.info_label.config(text="")

    def update_stats(self):
        """Update statistics display"""
        if self.bot_running:
            stats = f"Bot running since: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            stats += f"Configuration loaded\n"
            stats += f"Monitoring channel: {self.config_widgets['Twitch_Channel'].get()}\n"
            
            self.stats_text.config(state='normal')
            self.stats_text.delete('1.0', 'end')
            self.stats_text.insert('1.0', stats)
            self.stats_text.config(state='disabled')
            
            if self.bot_running:
                self.root.after(5000, self.update_stats)

    def show_about(self):
        """Show about dialog"""
        try:
            from importlib import metadata
            version = metadata.version('twitch-tts')
        except:
            version = "unknown"
        
        about_text = f"""Twitch TTS Bot - GUI Version
Version: {version}

A text-to-speech bot for Twitch chat with translation support.

Created by: Zutatensuppe
GitHub: https://github.com/Zutatensuppe/twitch-tts
"""
        messagebox.showinfo("About Twitch TTS Bot", about_text)

    def show_oauth_help(self):
        """Show OAuth token help"""
        help_text = """How to get OAuth Token:

1. Login to twitch.tv in your browser
2. Right-click and select 'Inspect' (or press F12)
3. Click the 'Network' tab
4. Type 'gql' in the Filter input box
5. Click one of the rows (refresh page if no rows)
6. Click the 'Headers' tab
7. Scroll to find 'Authorization: OAuth XXXXX'
8. Copy the XXXXX part (without 'OAuth ' prefix)
9. Paste it in the OAuth Token field

For detailed instructions with screenshots, visit:
https://github.com/Zutatensuppe/twitch-tts#how-to-get-the-trans_oauth-required-in-the-configjsonc
"""
        messagebox.showinfo("OAuth Token Help", help_text)

    def on_closing(self):
        """Handle window closing"""
        if self.bot_running:
            if messagebox.askokcancel("Quit", "Bot is running. Stop and quit?"):
                self.stop_bot()
                self.root.destroy()
        else:
            self.root.destroy()


def main():
    root = tk.Tk()
    app = TwitchTTSGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == '__main__':
    main()
