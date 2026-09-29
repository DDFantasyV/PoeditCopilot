import sys
import os
import re
import configparser
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QFileDialog, QTableWidget, QTableWidgetItem,
                             QSplitter, QLabel, QHeaderView, QMessageBox, QProgressBar,
                             QProgressDialog)
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QColor, QAction, QDesktopServices

import api_request
import updater
from ui_components import AboutDialog, LogWindow, LargeInputDialog, FindReplaceDialog, AITranslateDialog
from workers import TranslatorWorker
from po_manager import POManager
from search_engine import SearchEngine


DEVELOPER_NAME = "DDF_FantasyV"
REPO_URL = f"https://github.com/{updater.GITHUB_REPO}"
LICENSE_FILE = "LICENSE"


def resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    else:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        self.base_path = base_path
        self.config_path = os.path.join(base_path, 'PoeditCopilot.ini')

        try:
            from version import __version__ as app_version
        except ImportError:
            app_version = "0.0.0"

        self.app_version = app_version
        self.setWindowTitle(f"Poedit Copilot v{app_version}")
        self.po_manager = POManager()
        self.current_idx = -1
        self.worker = None
        self.update_worker = None
        self.update_download_worker = None
        self.pending_staged_update = None
        self.update_progress = None
        self._download_version = ""
        self._staged_prompt_shown = False
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(250)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.timeout.connect(self.refresh_ui)

        self.log_window = LogWindow()
        self.log_window.show()

        self.maybe_finish_staged_update()
        self.init_menu()
        self.init_ui()

        # Check for updates shortly after startup so it never delays the UI.
        QTimer.singleShot(3000, self.auto_check_update)
        QTimer.singleShot(1500, self.prompt_ready_staged_update)

    def init_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")
        new_action = QAction("New", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self.new_project)
        file_menu.addAction(new_action)

        load_project_action = QAction("Load Project", self)
        load_project_action.setShortcut("Ctrl+O")
        load_project_action.triggered.connect(self.load_progress)
        file_menu.addAction(load_project_action)

        save_project_action = QAction("Save Project", self)
        save_project_action.setShortcut("Ctrl+S")
        save_project_action.triggered.connect(self.save_progress)
        file_menu.addAction(save_project_action)

        edit_menu = menubar.addMenu("Edit")
        find_action = QAction("Find", self)
        find_action.setShortcut("Ctrl+F")
        find_action.triggered.connect(self.show_find_dialog)
        edit_menu.addAction(find_action)

        replace_action = QAction("Replace", self)
        replace_action.setShortcut("Ctrl+H")
        replace_action.triggered.connect(self.show_replace_dialog)
        edit_menu.addAction(replace_action)

        trans_menu = menubar.addMenu("Translate")
        ai_trans_action = QAction("AI Translate", self)
        ai_trans_action.triggered.connect(self.start_ai_trans)
        trans_menu.addAction(ai_trans_action)

        metadata_action = QAction("Metadata", self)
        metadata_action.triggered.connect(self.show_metadata_settings)
        trans_menu.addAction(metadata_action)

        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        menubar.addAction(about_action)

    def init_ui(self):
        main_widget = QWidget()
        layout = QVBoxLayout()

        top_group = QHBoxLayout()
        self.btn_load_new_ru = QPushButton("1. Load NEW Original MO")
        self.btn_load_old_ru = QPushButton("2. Load OLD Original MO")
        self.btn_load_old_cn = QPushButton("3. Load OLD Translated MO")
        self.btn_final = QPushButton("4. Export NEW Translated MO")
        self.workflow_buttons = [
            self.btn_load_new_ru,
            self.btn_load_old_ru,
            self.btn_load_old_cn,
            self.btn_final,
        ]
        button_width = max(button.sizeHint().width() for button in self.workflow_buttons)
        for button in self.workflow_buttons:
            button.setFixedWidth(button_width)

        self.translation_progress = QProgressBar()
        self.translation_progress.setMinimumWidth(220)
        self.translation_progress.setFormat("Translated: %v/%m (%p%)")
        self.translation_progress.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_load_new_ru.clicked.connect(self.load_new_ru)
        self.btn_load_old_ru.clicked.connect(self.load_old_ru)
        self.btn_load_old_cn.clicked.connect(self.load_old_cn)
        self.btn_final.clicked.connect(self.do_export)

        top_group.addWidget(self.btn_load_new_ru)
        top_group.addWidget(self.btn_load_old_ru)
        top_group.addWidget(self.btn_load_old_cn)
        top_group.addWidget(self.btn_final)
        top_group.addStretch(1)
        top_group.addWidget(self.translation_progress)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.left_table = QTableWidget()
        self.left_table.setColumnCount(3)
        self.left_table.setHorizontalHeaderLabels(["ID", "New", "Old"])
        self.left_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.left_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.left_table.itemClicked.connect(self.on_table_click)

        self.right_table = QTableWidget()
        self.right_table.setColumnCount(3)
        self.right_table.setHorizontalHeaderLabels(["Status", "Translation", "Action"])
        self.right_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.right_table.itemClicked.connect(self.on_table_click)

        splitter.addWidget(self.left_table)
        splitter.addWidget(self.right_table)

        left_v_bar = self.left_table.verticalScrollBar()
        right_v_bar = self.right_table.verticalScrollBar()
        left_v_bar.valueChanged.connect(right_v_bar.setValue)
        right_v_bar.valueChanged.connect(left_v_bar.setValue)
        splitter.setSizes([768, 768])

        edit_group = QHBoxLayout()
        self.lbl_id = QLabel("ID: -")
        self.lbl_source = QLabel("Source: -")
        self.lbl_source.setWordWrap(True)
        self.btn_accept = QPushButton("Pass")
        self.btn_edit = QPushButton("Edit")
        self.btn_accept.setStyleSheet("background-color: #d4f0f0;")
        self.btn_accept.clicked.connect(self.action_accept)
        self.btn_edit.clicked.connect(self.action_edit)

        edit_group.addWidget(self.lbl_id)
        edit_group.addWidget(self.lbl_source, 1)
        edit_group.addWidget(self.btn_accept)
        edit_group.addWidget(self.btn_edit)

        layout.addLayout(top_group)
        layout.addWidget(splitter, 1)
        layout.addLayout(edit_group)

        main_widget.setLayout(layout)
        self.setCentralWidget(main_widget)
        self.update_translation_progress()
        self.update_workflow_button_styles()

    def is_entry_translated(self, entry):
        if entry.get('status') == 'Deleted':
            return False
        if entry.get('is_plural'):
            return any(str(value) != '' for value in entry.get('translated_plural', {}).values())
        return str(entry.get('translated_text', '')) != ''

    def is_entry_reviewed(self, entry):
        status = entry.get('status')
        if status == 'Deleted':
            return False
        if status == 'Saved':
            return True
        if status == 'Normal':
            return self.is_entry_translated(entry)
        return False

    def update_translation_progress(self):
        active_entries = [entry for entry in self.po_manager.entries if entry.get('status') != 'Deleted']
        total_count = len(active_entries)
        translated_count = sum(1 for entry in active_entries if self.is_entry_reviewed(entry))

        self.translation_progress.setMaximum(total_count)
        self.translation_progress.setValue(translated_count)
        if total_count == 0:
            self.translation_progress.setFormat("Translated: 0/0 (0%)")
        else:
            self.translation_progress.setFormat("Translated: %v/%m (%p%)")

    def update_workflow_button_styles(self):
        for button in self.workflow_buttons:
            button.setStyleSheet("")

        active_entries = [entry for entry in self.po_manager.entries if entry.get('status') != 'Deleted']
        if not active_entries:
            return

        self.btn_load_new_ru.setStyleSheet("background-color: rgb(200, 255, 200);")

        has_comparison = any(
            entry.get('status') in ('Normal', 'Modified', 'Deleted') or entry.get('old_ru_text')
            for entry in self.po_manager.entries
        )
        if has_comparison:
            self.btn_load_old_ru.setStyleSheet("background-color: rgb(200, 255, 200);")

        has_translation = any(self.is_entry_translated(entry) for entry in active_entries)
        if has_translation:
            self.btn_load_old_cn.setStyleSheet("background-color: rgb(200, 255, 200);")

        if all(self.is_entry_reviewed(entry) for entry in active_entries):
            self.btn_final.setStyleSheet("background-color: rgb(200, 255, 200);")

    def show_find_dialog(self):
        if not hasattr(self, 'find_dialog'):
            self.find_dialog = FindReplaceDialog(self, is_replace=False)
            self.find_dialog.btn_find_prev.clicked.connect(lambda: self.do_find(is_replace_dialog=False, forward=False))
            self.find_dialog.btn_find.clicked.connect(lambda: self.do_find(is_replace_dialog=False, forward=True))
        self.find_dialog.show()
        self.find_dialog.raise_()
        self.find_dialog.activateWindow()

    def show_replace_dialog(self):
        if not hasattr(self, 'replace_dialog'):
            self.replace_dialog = FindReplaceDialog(self, is_replace=True)
            self.replace_dialog.btn_find_prev.clicked.connect(
                lambda: self.do_find(is_replace_dialog=True, forward=False))
            self.replace_dialog.btn_find.clicked.connect(lambda: self.do_find(is_replace_dialog=True, forward=True))
            self.replace_dialog.btn_replace.clicked.connect(self.do_replace)
            self.replace_dialog.btn_replace_all.clicked.connect(self.do_replace_all)
        self.replace_dialog.show()
        self.replace_dialog.raise_()
        self.replace_dialog.activateWindow()

    def do_find(self, is_replace_dialog=False, forward=True):
        dlg = self.replace_dialog if is_replace_dialog else self.find_dialog
        search_text = dlg.txt_find.text()
        if not search_text: return

        ignore_case = dlg.chk_ignore_case.isChecked()
        exact_match = dlg.chk_exact_match.isChecked()
        whole_word = dlg.chk_whole_word.isChecked()
        compiled_pattern = SearchEngine.get_compiled_pattern(search_text, ignore_case, whole_word)

        row_count = self.left_table.rowCount()
        if row_count == 0: return

        current_row = self.left_table.currentRow()
        start_row = 0 if forward else row_count - 1
        if current_row >= 0:
            start_row = (current_row + 1) % row_count if forward else (current_row - 1) % row_count

        for i in range(row_count):
            row = (start_row + i) % row_count if forward else (start_row - i) % row_count
            real_idx = self.left_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            entry = self.po_manager.entries[real_idx]

            texts_to_search = [
                str(entry.get('msgid', '')), entry.get('new_ru_text', ''), entry.get('old_ru_text', '')
            ]

            if entry['is_plural']:
                for val in entry.get('translated_plural', {}).values():
                    texts_to_search.append(str(val))
            else:
                texts_to_search.append(str(entry.get('translated_text', '')))

            match_found = any(SearchEngine.match_text(search_text, text, ignore_case, exact_match, compiled_pattern)
                              for text in texts_to_search)

            if match_found:
                self.left_table.selectRow(row)
                self.right_table.selectRow(row)
                self.on_table_click(self.left_table.item(row, 0))
                self.left_table.scrollToItem(self.left_table.item(row, 0))
                return

        QMessageBox.information(self, "Find", "No further matches.")

    def do_replace(self):
        row = self.left_table.currentRow()
        if row < 0:
            self.do_find(True, forward=True)
            return

        dlg = self.replace_dialog
        search_text = dlg.txt_find.text()
        replace_text = dlg.txt_replace.text()
        if not search_text: return

        ignore_case = dlg.chk_ignore_case.isChecked()
        exact_match = dlg.chk_exact_match.isChecked()
        whole_word = dlg.chk_whole_word.isChecked()
        compiled_pattern = SearchEngine.get_compiled_pattern(search_text, ignore_case, whole_word)

        real_idx = self.left_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        entry = self.po_manager.entries[real_idx]

        changed = False
        if entry['is_plural']:
            new_plural = {}
            for k, v in entry.get('translated_plural', {}).items():
                new_v = SearchEngine.replace_in_text(v, search_text, replace_text, ignore_case, exact_match,
                                                     compiled_pattern)
                if new_v != v: changed = True
                new_plural[k] = new_v
            if changed: entry['translated_plural'] = new_plural
        else:
            old_val = entry.get('translated_text', '')
            new_val = SearchEngine.replace_in_text(old_val, search_text, replace_text, ignore_case, exact_match,
                                                   compiled_pattern)
            if new_val != old_val:
                entry['translated_text'] = new_val
                changed = True

        if changed:
            entry['status'] = 'Saved'
            self.refresh_ui()
            for r in range(self.left_table.rowCount()):
                if self.left_table.item(r, 0).data(Qt.ItemDataRole.UserRole) == real_idx:
                    self.left_table.selectRow(r)
                    self.right_table.selectRow(r)
                    break

        self.do_find(True, forward=True)

    def do_replace_all(self):
        dlg = self.replace_dialog
        search_text = dlg.txt_find.text()
        replace_text = dlg.txt_replace.text()
        if not search_text: return

        ignore_case = dlg.chk_ignore_case.isChecked()
        exact_match = dlg.chk_exact_match.isChecked()
        whole_word = dlg.chk_whole_word.isChecked()
        compiled_pattern = SearchEngine.get_compiled_pattern(search_text, ignore_case, whole_word)

        count = 0
        for entry in self.po_manager.entries:
            changed = False
            if entry['is_plural']:
                new_plural = {}
                for k, v in entry.get('translated_plural', {}).items():
                    new_v = SearchEngine.replace_in_text(v, search_text, replace_text, ignore_case, exact_match,
                                                         compiled_pattern)
                    if new_v != v: changed = True
                    new_plural[k] = new_v
                if changed: entry['translated_plural'] = new_plural
            else:
                old_val = entry.get('translated_text', '')
                new_val = SearchEngine.replace_in_text(old_val, search_text, replace_text, ignore_case, exact_match,
                                                       compiled_pattern)
                if new_val != old_val:
                    entry['translated_text'] = new_val
                    changed = True

            if changed:
                entry['status'] = 'Saved'
                count += 1

        if count > 0:
            self.refresh_ui()
            QMessageBox.information(self, "Replace all", f"Replace Completed. {count} total.")
        else:
            QMessageBox.information(self, "Replace all", "No further matches.")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            event.ignore()
        else:
            super().keyPressEvent(event)

    def start_ai_trans(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "AI Translate", "AI translation is already running.")
            return

        settings = self.read_ai_settings()
        dlg = AITranslateDialog(self, settings, api_request.validate_api_settings)
        if not dlg.exec():
            self.log("Translation cancelled: AI Translate settings were not confirmed.")
            return

        settings = dlg.get_settings()
        if not self.save_ai_settings(settings):
            return

        self.log("AI Translate settings verified and saved.")
        self.worker = TranslatorWorker(self.po_manager.entries, settings)
        self.worker.log_signal.connect(self.log)
        self.worker.finished.connect(self.on_ai_finished)
        self.worker.process_finished.connect(self.on_ai_process_finished)
        self.worker.start()

    def read_ai_settings(self):
        config = configparser.RawConfigParser()
        config.read(self.config_path, encoding='utf-8')

        def get_float(section, option, fallback):
            try:
                return config.getfloat(section, option, fallback=fallback)
            except ValueError:
                return fallback

        def get_int(section, option, fallback):
            try:
                return config.getint(section, option, fallback=fallback)
            except ValueError:
                return fallback

        def get_bool(section, option, fallback):
            try:
                return config.getboolean(section, option, fallback=fallback)
            except ValueError:
                return fallback

        api_key = config.get('AITranslate', 'ApiKey', fallback='')
        if not api_key:
            api_key = config.get('Settings', 'GeminiKey', fallback='')

        return {
            "base_url": config.get('AITranslate', 'BaseUrl', fallback=''),
            "api_key": api_key,
            "model": config.get('AITranslate', 'Model', fallback=''),
            "source_lang": config.get('Settings', 'OriginLanguage', fallback='Russian'),
            "target_lang": config.get('Settings', 'TargetLanguage', fallback=''),
            "prompt_preset": config.get('AITranslate', 'PromptPreset', fallback='Game Localization'),
            "prompt_template": config.get(
                'AITranslate',
                'PromptTemplate',
                fallback=api_request.DEFAULT_PROMPT_TEMPLATE,
            ),
            "use_context_cache": get_bool('AITranslate', 'UseContextCache', False),
            "context_cache_limit": get_int('AITranslate', 'ContextCacheLimit', 20),
            "use_advanced_params": get_bool('AITranslate', 'UseAdvancedParams', False),
            "temperature": get_float('AITranslate', 'Temperature', 0.7),
            "top_p": get_float('AITranslate', 'TopP', 0.95),
            "max_output_tokens": get_int('AITranslate', 'MaxOutputTokens', 2048),
            "request_delay": get_float('AITranslate', 'RequestDelay', 0.0),
            "request_timeout": get_float('AITranslate', 'RequestTimeout', 45.0),
            "max_concurrent_requests": get_int('AITranslate', 'MaxConcurrentRequests', 3),
        }

    def save_ai_settings(self, settings):
        config = configparser.RawConfigParser()
        config.read(self.config_path, encoding='utf-8')
        if 'Settings' not in config:
            config['Settings'] = {}
        if 'AITranslate' not in config:
            config['AITranslate'] = {}

        config['Settings']['OriginLanguage'] = settings["source_lang"]
        config['Settings']['TargetLanguage'] = settings["target_lang"]

        config['AITranslate']['ApiKey'] = settings["api_key"]
        config['AITranslate']['BaseUrl'] = settings["base_url"]
        config['AITranslate']['Model'] = settings["model"]
        config['AITranslate']['PromptPreset'] = settings["prompt_preset"]
        config['AITranslate']['PromptTemplate'] = settings["prompt_template"]
        config['AITranslate']['UseContextCache'] = str(settings["use_context_cache"])
        config['AITranslate']['ContextCacheLimit'] = str(settings["context_cache_limit"])
        config['AITranslate']['UseAdvancedParams'] = str(settings["use_advanced_params"])
        config['AITranslate']['Temperature'] = str(settings["temperature"])
        config['AITranslate']['TopP'] = str(settings["top_p"])
        config['AITranslate']['MaxOutputTokens'] = str(settings["max_output_tokens"])
        config['AITranslate']['RequestDelay'] = str(settings["request_delay"])
        config['AITranslate']['RequestTimeout'] = str(settings["request_timeout"])
        config['AITranslate']['MaxConcurrentRequests'] = str(settings["max_concurrent_requests"])

        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                config.write(f)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save AI Translate settings:\n{e}")
            return False

    def show_metadata_settings(self):
        config = configparser.RawConfigParser()
        config.read(self.config_path, encoding='utf-8')

        # Default metadata used when no saved metadata exists.
        default_meta = (
            "Project-Id-Version: Mir Korabley\n"
            "Last-Translator: \n"
            "Language-Team: \n"
            "Language: \n"
            "Content-Type: text/plain; charset=UTF-8\n"
            "Content-Transfer-Encoding: 8bit\n"
            "Plural-Forms: nplurals=1; plural=0;"
        )

        current_meta = config.get('Settings', 'Metadata', fallback=default_meta)

        dlg = LargeInputDialog(self, "Edit Metadata", "Enter Metadata (Key: Value per line):", current_meta)
        if dlg.exec():
            if 'Settings' not in config:
                config['Settings'] = {}
            config['Settings']['Metadata'] = dlg.textValue().strip()
            try:
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    config.write(f)
                self.log("Metadata settings saved.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save settings:\n{e}")

    def log(self, msg):
        self.log_window.log(msg)
        print(msg)

    def read_update_settings(self):
        config = configparser.RawConfigParser()
        config.read(self.config_path, encoding='utf-8')

        def get_bool(option, fallback):
            try:
                return config.getboolean('Update', option, fallback=fallback)
            except ValueError:
                return fallback

        def get_int(option, fallback):
            try:
                return config.getint('Update', option, fallback=fallback)
            except ValueError:
                return fallback

        return {
            "auto_check": get_bool('AutoCheck', True),
            "interval_hours": get_int('CheckIntervalHours', updater.DEFAULT_INTERVAL_HOURS),
            "last_check": config.get('Update', 'LastCheck', fallback=''),
            "skip_version": config.get('Update', 'SkipVersion', fallback=''),
        }

    def write_update_settings(self, **options):
        config = configparser.RawConfigParser()
        config.read(self.config_path, encoding='utf-8')
        if 'Update' not in config:
            config['Update'] = {}
        for option, value in options.items():
            config['Update'][option] = str(value)
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                config.write(f)
            return True
        except Exception as e:
            self.log(f"Update settings could not be saved: {e}")
            return False

    def auto_check_update(self):
        settings = self.read_update_settings()
        if not settings["auto_check"]:
            self.log("Startup update check skipped: AutoCheck is disabled in PoeditCopilot.ini.")
            return
        if not updater.is_check_due(settings["last_check"], settings["interval_hours"]):
            self.log(
                "Startup update check skipped: last check was "
                f"{settings['last_check'] or 'unknown'} and the interval is "
                f"{settings['interval_hours']}h."
            )
            return
        if self.update_worker and self.update_worker.isRunning():
            self.log("Startup update check skipped: another update check is already running.")
            return
        self.log("Startup update check triggered.")
        self.check_for_updates(manual=False)

    def check_for_updates(self, manual=False):
        if self.update_worker and self.update_worker.isRunning():
            if manual:
                QMessageBox.information(self, "Check for Updates", "An update check is already running.")
            return

        self.log("Checking GitHub for newer release...")
        self.update_worker = updater.UpdateCheckWorker(self.app_version)
        self.update_worker.check_finished.connect(
            lambda info: self.on_update_check_finished(info, manual)
        )
        self.update_worker.check_failed.connect(
            lambda message: self.on_update_check_failed(message, manual)
        )
        self.update_worker.start()

    def on_update_check_finished(self, info, manual=False):
        self.write_update_settings(LastCheck=updater.format_check_time())

        if not updater.is_newer_version(info.latest_version, info.current_version):
            self.log(f"Poedit Copilot is up to date (v{info.current_version}).")
            if manual:
                QMessageBox.information(
                    self,
                    "Check for Updates",
                    f"Poedit Copilot v{info.current_version} is the latest version.",
                )
            return

        skip_version = self.read_update_settings()["skip_version"]
        self.log(
            f"Update available: v{info.current_version} -> v{info.latest_version} "
            f"({info.release_url})"
        )
        if not manual and str(skip_version).strip().lstrip("vV") == info.latest_version.lstrip("vV"):
            self.log(f"Update v{info.latest_version} is marked as skipped; not prompting.")
            return

        self.prompt_update(info)

    def on_update_check_failed(self, message, manual=False):
        self.log(f"Update check failed: {message}")
        if manual:
            QMessageBox.warning(self, "Check for Updates", f"Could not check for updates.\n\n{message}")

    def prompt_update(self, info):
        box = QMessageBox(self)
        box.setWindowTitle("Update Available")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(
            "A newer version of Poedit Copilot is available.\n\n"
            f"v{info.current_version} -> v{info.latest_version}"
        )
        details = (
            "Download it now; the new build replaces this one and restarts "
            "automatically when you close the app."
        )
        if info.published_at:
            details += f"\n\nPublished: {info.published_at}"
        box.setInformativeText(details)
        download_button = box.addButton("Download Update", QMessageBox.ButtonRole.AcceptRole)
        open_button = box.addButton("Open Release Page", QMessageBox.ButtonRole.ActionRole)
        box.addButton("Skip This Version", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        box.exec()

        clicked = box.clickedButton()
        if clicked is download_button:
            self.start_update_download(info)
        elif clicked is open_button:
            QDesktopServices.openUrl(QUrl(info.release_url))
            self.log(f"Release page opened: {info.release_url}")
        elif clicked is not None and box.buttonRole(clicked) == QMessageBox.ButtonRole.DestructiveRole:
            self.write_update_settings(SkipVersion=info.latest_version)
            self.log(f"Version v{info.latest_version} will not prompt again.")

    def start_update_download(self, info):
        if self.update_download_worker and self.update_download_worker.isRunning():
            self.log("Update download skipped: another download is already running.")
            return

        version = info.version or str(info.latest_version)
        self._download_version = version
        staged_path = updater.staged_exe_path(self.base_path, version)

        self.update_progress = QProgressDialog("Downloading update...", "Cancel", 0, 0, self)
        self.update_progress.setWindowTitle("Download Update")
        self.update_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.update_progress.setMinimumDuration(0)
        self.update_progress.setAutoClose(False)
        self.update_progress.setAutoReset(False)
        self.update_progress.canceled.connect(self.cancel_update_download)
        self.update_progress.show()

        self.log(f"Downloading Poedit Copilot v{version}...")
        self.update_download_worker = updater.UpdateDownloadWorker(
            info.exe_url, staged_path, checksum_url=info.checksum_url
        )
        self.update_download_worker.progress.connect(self.on_update_download_progress)
        self.update_download_worker.download_finished.connect(self.on_update_download_finished)
        self.update_download_worker.download_failed.connect(self.on_update_download_failed)
        self.update_download_worker.start()

    def on_update_download_progress(self, done, total):
        if getattr(self, "update_progress", None) is None:
            return
        if total > 0:
            self.update_progress.setMaximum(total)
            self.update_progress.setValue(min(done, total))
        else:
            self.update_progress.setMaximum(0)

    def cancel_update_download(self):
        if self.update_download_worker and self.update_download_worker.isRunning():
            self.log("Update download cancelled.")
            self.update_download_worker.cancel()

    def close_update_progress(self):
        if getattr(self, "update_progress", None) is not None:
            self.update_progress.reset()
            self.update_progress.close()
            self.update_progress = None

    def on_update_download_finished(self, staged_path):
        self.close_update_progress()
        version = getattr(self, "_download_version", "")
        self.pending_staged_update = (version, staged_path)
        self._staged_prompt_shown = False
        self.log(f"Update v{version} downloaded and verified: {staged_path}")
        self.prompt_ready_staged_update()

    def on_update_download_failed(self, message):
        self.close_update_progress()
        self.log(f"Update download failed: {message}")
        QMessageBox.warning(self, "Download Update", f"Could not download the update.\n\n{message}")

    def maybe_finish_staged_update(self):
        staged = updater.find_staged_update(self.base_path, self.app_version)
        if staged:
            self.pending_staged_update = staged

    def prompt_ready_staged_update(self):
        if not self.pending_staged_update or self._staged_prompt_shown:
            return
        self._staged_prompt_shown = True
        version, staged_path = self.pending_staged_update
        self.log(f"Prepared update v{version} is ready: {os.path.basename(staged_path)}")
        answer = QMessageBox.question(
            self,
            "Update Ready",
            f"Poedit Copilot v{version} has been downloaded.\n\n"
            "Apply it now and restart? If you choose No, it is applied "
            "automatically the next time you close the app.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.apply_pending_update()

    def launch_update_swap(self, staged_path):
        script_path = updater.write_swap_script(
            staged_path,
            old_exe_path=sys.executable,
            log_path=os.path.join(self.base_path, "update.log"),
        )
        updater.launch_swap_script(script_path)
        return script_path

    def auto_apply_pending_update(self):
        """Start the on-exit replacement. Returns True when nothing blocks closing."""
        if not self.pending_staged_update:
            return True
        version, staged_path = self.pending_staged_update
        if not updater.is_frozen_app():
            self.log(
                "Staged update kept: automatic replacement only runs from the packaged EXE."
            )
            return True
        try:
            script_path = self.launch_update_swap(staged_path)
        except Exception as error:
            self.log(f"Could not start the update helper: {error}")
            return False
        self.log(f"Update helper started: {script_path}")
        self.log(f"Poedit Copilot v{version} will be applied and restarted after exit.")
        self.pending_staged_update = None
        return True

    def apply_pending_update(self):
        if not self.pending_staged_update:
            QMessageBox.information(self, "Apply Update", "No downloaded update is waiting.")
            return
        version, staged_path = self.pending_staged_update
        if not updater.is_frozen_app():
            self.log("Staged update kept: automatic replacement only runs from the packaged EXE.")
            QMessageBox.information(
                self,
                "Apply Update",
                "Automatic replacement only runs from the packaged EXE.\n\n"
                f"A prepared build is waiting at:\n{staged_path}",
            )
            return
        QMessageBox.information(
            self,
            "Apply Update",
            f"Poedit Copilot v{version} is ready to be applied.\n\n"
            "The application will close, replace, and restart automatically.",
        )
        QTimer.singleShot(0, self.close_for_update)

    def close_for_update(self):
        """Exit the app after the user confirmed an update, including the log window."""
        if self.log_window is not None:
            self.log_window.close()
        self.close()

    def on_about_to_quit(self):
        """Last hook before the process exits: apply a staged update and restart."""
        if self.update_download_worker and self.update_download_worker.isRunning():
            self.update_download_worker.cancel()
            self.update_download_worker.wait(3000)
        self.auto_apply_pending_update()

    def read_license_text(self):
        path = resource_path(LICENSE_FILE)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except OSError as e:
            self.log(f"License file could not be read: {e}")
            return ""

    def show_about(self):
        dialog = AboutDialog(
            self,
            app_name="Poedit Copilot",
            version=self.app_version,
            developer=DEVELOPER_NAME,
            icon_path=resource_path('PoeditCopilot.png'),
            repo_url=REPO_URL,
            license_name="MIT License",
            license_text=self.read_license_text(),
            on_check_update=lambda: self.check_for_updates(manual=True),
        )
        dialog.exec()

    def load_new_ru(self):
        path, _ = QFileDialog.getOpenFileName(self, "1. Choose NEW Original MO", "", "MO Files (*.mo)")
        if not path: return
        try:
            count = self.po_manager.load_new_mo(path)
            self.log(f"Load NEW File Completed: {count}")
            self.refresh_ui()
            self.btn_load_new_ru.setStyleSheet("background-color: rgb(200, 255, 200);")
        except Exception as e:
            self.log(f"Error: {e}")
            self.btn_load_new_ru.setStyleSheet("background-color: rgb(255, 200, 200);")

    def load_old_ru(self):
        if not self.po_manager.entries: return
        path, _ = QFileDialog.getOpenFileName(self, "2. Choose OLD Original MO", "", "MO Files (*.mo)")
        if not path: return
        try:
            self.po_manager.load_old_mo(path)
            self.log("Compared Completed.")
            self.refresh_ui()
            self.btn_load_old_ru.setStyleSheet("background-color: rgb(200, 255, 200);")
        except Exception as e:
            self.log(f"Error: {e}")
            self.btn_load_old_ru.setStyleSheet("background-color: rgb(255, 200, 200);")

    def load_old_cn(self):
        if not self.po_manager.entries: return
        path, _ = QFileDialog.getOpenFileName(self, "3. Choose OLD Translated MO", "", "MO Files (*.mo)")
        if not path: return
        try:
            count = self.po_manager.load_translated_mo(path)
            self.log(f"Translation Loaded. {count} Paired.")
            self.refresh_ui()
            self.btn_load_old_cn.setStyleSheet("background-color: rgb(200, 255, 200);")
        except Exception as e:
            self.log(f"Error: {e}")
            self.btn_load_old_cn.setStyleSheet("background-color: rgb(255, 200, 200);")

    def do_export(self):
        save_path, _ = QFileDialog.getSaveFileName(self, "Export NEW Translated MO", "global.mo", "MO Files (*.mo)")
        if not save_path: return

        config = configparser.RawConfigParser()
        config.read(self.config_path, encoding='utf-8')
        meta_str = config.get('Settings', 'Metadata', fallback="")
        meta_dict = None
        if meta_str:
            meta_dict = {}
            for line in meta_str.split('\n'):
                if ':' in line:
                    k, v = line.split(':', 1)
                    meta_dict[k.strip()] = v.strip()

        try:
            count = self.po_manager.export_mo(save_path)
            QMessageBox.information(self, "Completed", f"Export Completed. {count} Total.")
            self.btn_final.setStyleSheet("background-color: rgb(200, 255, 200);")
        except Exception as e:
            self.log(f"Error: {e}")
            QMessageBox.critical(self, "Error", str(e))
            self.btn_final.setStyleSheet("background-color: rgb(255, 200, 200);")

    def refresh_ui(self):
        self.left_table.setUpdatesEnabled(False)
        self.right_table.setUpdatesEnabled(False)

        self.left_table.setRowCount(0)
        self.right_table.setRowCount(0)

        modified_list = [(idx, item) for idx, item in enumerate(self.po_manager.entries) if item['status'] != 'Normal']
        normal_list = [(idx, item) for idx, item in enumerate(self.po_manager.entries) if item['status'] == 'Normal']
        display_list = modified_list + normal_list

        self.left_table.setRowCount(len(display_list))
        self.right_table.setRowCount(len(display_list))

        for row, (real_idx, item) in enumerate(display_list):
            st = item['status']
            color = QColor(255, 255, 255)
            if st == 'New':
                color = QColor(200, 255, 200)
            elif st == 'Modified':
                color = QColor(255, 255, 200)
            elif st == 'Deleted':
                color = QColor(255, 200, 200)
            elif st == 'Saved':
                color = QColor(200, 200, 255)

            id_str = str(item['entry_id']) if item['entry_id'] != -1 else "DEL"
            if item['is_plural']: id_str += " (PL)"

            self._set_item(self.left_table, row, 0, id_str, color, real_idx)
            self._set_item(self.left_table, row, 1, item['new_ru_text'], color, real_idx)
            self._set_item(self.left_table, row, 2, item['old_ru_text'], color, real_idx)
            self._set_item(self.right_table, row, 0, st, color, real_idx)

            if item['is_plural']:
                trans_txt = "; ".join([f"[{k}]{v}" for k, v in item['translated_plural'].items()])
            else:
                trans_txt = item['translated_text']

            self._set_item(self.right_table, row, 1, trans_txt, color, real_idx)
            act_txt = "TBD" if st in ['New', 'Modified'] else ""
            self._set_item(self.right_table, row, 2, act_txt, color, real_idx)

        self.left_table.setUpdatesEnabled(True)
        self.right_table.setUpdatesEnabled(True)
        self.update_translation_progress()
        self.update_workflow_button_styles()

    def _set_item(self, table, row, col, text, color, user_data):
        item = QTableWidgetItem(str(text))
        item.setData(Qt.ItemDataRole.UserRole, user_data)
        item.setBackground(color)
        table.setItem(row, col, item)

    def on_table_click(self, item):
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is None: return
        self.current_idx = idx
        entry = self.po_manager.entries[idx]
        source_show = f"[Plural ID] {entry['msgid_plural']}\n[Singular Source] {entry['new_ru_text']}" if entry[
            'is_plural'] else entry['new_ru_text']
        self.lbl_id.setText(f"ID: {entry['msgid']}")
        self.lbl_source.setText(f"Source: {source_show}")

        is_del = (entry['status'] == 'Deleted')
        self.btn_accept.setEnabled(not is_del)
        self.btn_edit.setEnabled(not is_del)

    def action_accept(self):
        if self.current_idx < 0: return
        self.po_manager.entries[self.current_idx]['status'] = 'Saved'
        self.refresh_ui()

    def action_edit(self):
        if self.current_idx < 0: return
        entry = self.po_manager.entries[self.current_idx]
        if entry['is_plural']:
            current_dict = entry['translated_plural']
            edit_text = "\n".join([f"[{k}]: {v}" for k, v in sorted(current_dict.items())]) if current_dict else "[0]: "
            instruction = "Format: [Index]: Content\nNormally index is only [0]"
            dlg = LargeInputDialog(self, "Edit Plural Translation", instruction, edit_text)
            if dlg.exec():
                text = dlg.textValue()
                new_dict = {}
                pattern = re.compile(r'^\[(\d+)\]:\s*(.*)$')
                for line in text.split('\n'):
                    line = line.strip()
                    if not line: continue
                    match = pattern.match(line)
                    if match:
                        new_dict[int(match.group(1))] = match.group(2)
                    else:
                        new_dict[0] = line
                entry['translated_plural'] = new_dict
                entry['status'] = 'Saved'
                self.refresh_ui()
        else:
            dlg = LargeInputDialog(self, "Edit Translation", "Content:", entry['translated_text'])
            if dlg.exec():
                entry['translated_text'] = dlg.textValue()
                entry['status'] = 'Saved'
                self.refresh_ui()

    def on_ai_finished(self, idx, text_str, text_dict):
        entry = self.po_manager.entries[idx]
        if entry['is_plural']:
            entry['translated_plural'] = text_dict
        else:
            entry['translated_text'] = text_str
        self.update_translation_progress()
        if not self.refresh_timer.isActive():
            self.refresh_timer.start()

    def on_ai_process_finished(self):
        if self.refresh_timer.isActive():
            self.refresh_timer.stop()
        self.refresh_ui()

    def save_progress(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Project", "progress.tmp", "Tmp (*.tmp)")
        if path:
            self.po_manager.save_progress(path)
            self.log("Project Saved")

    def load_progress(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Project", "", "Tmp (*.tmp)")
        if path:
            self.po_manager.load_progress(path)
            self.refresh_ui()

    def closeEvent(self, event):
        if hasattr(self, 'log_window'):
            self.log_window.close()
        event.accept()

    def new_project(self):
        if self.po_manager.entries:
            reply = QMessageBox.question(self, 'New Project',
                                         'Create a new project? ALL unsaved progress will be lost!',
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.po_manager.clear()
        self.current_idx = -1
        self.left_table.setRowCount(0)
        self.right_table.setRowCount(0)
        self.lbl_id.setText("ID: -")
        self.lbl_source.setText("Source: -")

        self.update_translation_progress()
        self.update_workflow_button_styles()
        self.log("New Project Created. Environment cleared.")
