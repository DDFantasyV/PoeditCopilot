import sys
import os
import re
import configparser
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QFileDialog, QTableWidget, QTableWidgetItem,
                             QSplitter, QLabel, QHeaderView, QInputDialog, QMessageBox, QLineEdit)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QAction

import api_request
from ui_components import LogWindow, LargeInputDialog, FindReplaceDialog, LanguageDialog
from workers import TranslatorWorker
from po_manager import POManager
from search_engine import SearchEngine


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))

        self.config_path = os.path.join(base_path, 'PoeditCopilot.ini')

        try:
            from version import __version__ as app_version
        except ImportError:
            app_version = "0.0.0"

        self.setWindowTitle(f"Poedit Copilot v{app_version}")
        self.po_manager = POManager()
        self.current_idx = -1

        self.log_window = LogWindow()
        self.log_window.show()

        self.init_menu()
        self.init_ui()

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

        lang_settings_action = QAction("Target Language", self)
        lang_settings_action.triggered.connect(self.show_language_settings)
        trans_menu.addAction(lang_settings_action)

        metadata_action = QAction("Metadata", self)
        metadata_action.triggered.connect(self.show_metadata_settings)
        trans_menu.addAction(metadata_action)

    def init_ui(self):
        main_widget = QWidget()
        layout = QVBoxLayout()

        top_group = QHBoxLayout()
        self.btn_load_new_ru = QPushButton("1. Load NEW Original MO")
        self.btn_load_old_ru = QPushButton("2. Load OLD Original MO")
        self.btn_load_old_cn = QPushButton("3. Load OLD Translated MO")
        self.btn_final = QPushButton("4. Export NEW Translated MO")

        self.btn_load_new_ru.clicked.connect(self.load_new_ru)
        self.btn_load_old_ru.clicked.connect(self.load_old_ru)
        self.btn_load_old_cn.clicked.connect(self.load_old_cn)
        self.btn_final.clicked.connect(self.do_export)

        top_group.addWidget(self.btn_load_new_ru)
        top_group.addWidget(self.btn_load_old_ru)
        top_group.addWidget(self.btn_load_old_cn)
        top_group.addWidget(self.btn_final)

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
        api_key = self.get_valid_api_key()
        if not api_key:
            self.log("Translation cancelled: No valid API Key.")
            return

        config = configparser.ConfigParser()
        config.read(self.config_path)
        source_lang = config.get('Settings', 'OriginLanguage', fallback='Russian')
        target_lang = config.get('Settings', 'TargetLanguage', fallback='Simplified Chinese')

        self.worker = TranslatorWorker(self.po_manager.entries, api_key, source_lang, target_lang)
        self.worker.log_signal.connect(self.log)
        self.worker.finished.connect(self.on_ai_finished)
        self.worker.start()

    def show_language_settings(self):
        config = configparser.ConfigParser()
        config.read(self.config_path)
        origin = config.get('Settings', 'OriginLanguage', fallback='Russian')
        target = config.get('Settings', 'TargetLanguage', fallback='Simplified Chinese')

        dlg = LanguageDialog(self, origin, target)
        if dlg.exec():
            if 'Settings' not in config:
                config['Settings'] = {}
            config['Settings']['OriginLanguage'] = dlg.txt_origin.text().strip()
            config['Settings']['TargetLanguage'] = dlg.txt_target.text().strip()
            try:
                with open(self.config_path, 'w') as f:
                    config.write(f)
                self.log("Language settings saved.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save settings:\n{e}")

    def show_metadata_settings(self):
        config = configparser.ConfigParser()
        config.read(self.config_path)

        # 默认的 Metadata 文本
        default_meta = (
            "Project-Id-Version: Mir Korabley\n"
            "Last-Translator: DDF_FantasyV\n"
            "Language-Team: <REPAD Localization Team>\n"
            "Language: zh_SG\n"
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
                with open(self.config_path, 'w') as f:
                    config.write(f)
                self.log("Metadata settings saved.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save settings:\n{e}")

    def get_valid_api_key(self):
        config = configparser.ConfigParser()
        current_key = ""
        if os.path.exists(self.config_path):
            try:
                config.read(self.config_path)
                if 'Settings' in config and 'GeminiKey' in config['Settings']:
                    current_key = config['Settings']['GeminiKey'].strip()
            except Exception as e:
                self.log(f"Config read error: {e}")

        if current_key:
            return current_key

        while True:
            text, ok = QInputDialog.getText(self, "API Key Missing",
                                            "Please enter your Google Gemini API Key:\n",
                                            QLineEdit.EchoMode.Normal, "")
            if not ok:
                return None
            input_key = text.strip()
            if not input_key: continue

            self.log("Verifying API Key...")
            is_valid, msg = api_request.validate_api_key(input_key)
            if is_valid:
                self.save_api_key(input_key)
                self.log("API Key has verified and saved.")
                return input_key
            else:
                QMessageBox.warning(self, "Verification Failed", f"Invalid API Key.\nServer response: {msg}")

    def save_api_key(self, key):
        config = configparser.ConfigParser()
        config['Settings'] = {'GeminiKey': key}
        try:
            with open(self.config_path, 'w') as f:
                config.write(f)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save config file:\n{e}")

    def log(self, msg):
        self.log_window.log(msg)
        print(msg)

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

        config = configparser.ConfigParser()
        config.read(self.config_path)
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
            QMessageBox.information(self, "Completed", f"Export Completed！{count} Total.")
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

        self.btn_load_new_ru.setStyleSheet("")
        self.btn_load_old_ru.setStyleSheet("")
        self.btn_load_old_cn.setStyleSheet("")
        self.btn_final.setStyleSheet("")

        self.log("New Project Created. Environment cleared.")