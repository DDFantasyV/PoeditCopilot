import sys
import os
import polib
import pickle
import re
import configparser
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QFileDialog, QTableWidget, QTableWidgetItem,
                             QSplitter, QLabel, QHeaderView, QInputDialog, QMessageBox, QLineEdit)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

import api_request
from ui_components import LogWindow, LargeInputDialog, FinalReviewDialog
from workers import TranslatorWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Poedit Copilot v0.2.0")

        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))

        self.config_path = os.path.join(base_path, 'PoeditCopilot.ini')
        self.po_entries = []

        self.log_window = LogWindow()
        self.log_window.show()

        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        layout = QVBoxLayout()

        top_group = QHBoxLayout()
        self.btn_load_new_ru = QPushButton("1. Load NEW Original MO")
        self.btn_load_old_ru = QPushButton("2. Load OLD Original MO")
        self.btn_load_old_cn = QPushButton("3. Load OLD Translated MO")
        self.btn_load_new_ru.clicked.connect(self.load_new_ru)
        self.btn_load_old_ru.clicked.connect(self.load_old_ru)
        self.btn_load_old_cn.clicked.connect(self.load_old_cn)
        top_group.addWidget(self.btn_load_new_ru)
        top_group.addWidget(self.btn_load_old_ru)
        top_group.addWidget(self.btn_load_old_cn)

        func_group = QHBoxLayout()
        self.btn_auto_trans = QPushButton("AI Translate")
        self.btn_temp_save = QPushButton("Save Project")
        self.btn_temp_load = QPushButton("Load Project")
        self.btn_final = QPushButton("Review and Export")
        self.btn_auto_trans.clicked.connect(self.start_ai_trans)
        self.btn_temp_save.clicked.connect(self.save_progress)
        self.btn_temp_load.clicked.connect(self.load_progress)
        self.btn_final.clicked.connect(self.show_final_dialog)
        func_group.addWidget(self.btn_auto_trans)
        func_group.addWidget(self.btn_temp_save)
        func_group.addWidget(self.btn_temp_load)
        func_group.addWidget(self.btn_final)

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
        layout.addLayout(func_group)
        layout.addWidget(splitter, 1)
        layout.addLayout(edit_group)

        main_widget.setLayout(layout)
        self.setCentralWidget(main_widget)
        self.current_idx = -1

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()

    def start_ai_trans(self):
        api_key = self.get_valid_api_key()
        if not api_key:
            self.log("Translation cancelled: No valid API Key.")
            return

        self.worker = TranslatorWorker(self.po_entries, api_key)
        self.worker.log_signal.connect(self.log)
        self.worker.finished.connect(self.on_ai_finished)
        self.worker.start()

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
            mo = polib.mofile(path)
            self.po_entries = []
            for idx, entry in enumerate(mo):
                is_plural = bool(entry.msgid_plural)
                new_ru_text = entry.msgstr_plural.get(0, "") if is_plural else entry.msgstr
                self.po_entries.append({
                    'entry_id': idx + 1, 'msgid': entry.msgid, 'is_plural': is_plural,
                    'msgid_plural': entry.msgid_plural if is_plural else '',
                    'new_ru_text': new_ru_text, 'old_ru_text': '', 'status': 'New',
                    'translated_text': '', 'translated_plural': {}
                })
            self.log(f"Load NEW File Completed: {len(self.po_entries)}")
            self.refresh_ui()
        except Exception as e:
            self.log(f"Error: {e}")

    def load_old_ru(self):
        if not self.po_entries: return
        path, _ = QFileDialog.getOpenFileName(self, "2. Choose OLD Original MO", "", "MO Files (*.mo)")
        if not path: return
        try:
            old_mo = polib.mofile(path)
            old_map = {e.msgid: e for e in old_mo}
            new_ids = set()

            for item in self.po_entries:
                mid = item['msgid']
                new_ids.add(mid)
                if mid in old_map:
                    old_entry = old_map[mid]
                    item['old_ru_text'] = old_entry.msgstr_plural.get(0, "") if item['is_plural'] else old_entry.msgstr

                    plural_changed = item['is_plural'] and (old_entry.msgid_plural != item['msgid_plural'])
                    text_changed = (item['new_ru_text'] != item['old_ru_text'])

                    item['status'] = 'Modified' if (text_changed or plural_changed) else 'Normal'
                else:
                    item['status'] = 'New'

            for entry in old_mo:
                if entry.msgid not in new_ids:
                    self.po_entries.append({
                        'entry_id': -1, 'msgid': entry.msgid, 'is_plural': bool(entry.msgid_plural),
                        'msgid_plural': entry.msgid_plural, 'new_ru_text': '', 'old_ru_text': entry.msgstr,
                        'status': 'Deleted', 'translated_text': '', 'translated_plural': {}
                    })
            self.log("Compared Completed.")
            self.refresh_ui()
        except Exception as e:
            self.log(f"Error: {e}")

    def load_old_cn(self):
        if not self.po_entries: return
        path, _ = QFileDialog.getOpenFileName(self, "3. Choose OLD Translated MO", "", "MO Files (*.mo)")
        if not path: return
        try:
            cn_mo = polib.mofile(path)
            cn_map = {e.msgid: e for e in cn_mo}
            count = 0
            for item in self.po_entries:
                if item['msgid'] in cn_map:
                    target_entry = cn_map[item['msgid']]
                    if item['is_plural']:
                        if target_entry.msgstr_plural:
                            item['translated_plural'] = target_entry.msgstr_plural.copy()
                        elif target_entry.msgstr:
                            item['translated_plural'] = {0: target_entry.msgstr}
                    else:
                        item['translated_text'] = target_entry.msgstr
                    count += 1
            self.log(f"Translation Loaded. {count} Paired.")
            self.refresh_ui()
        except Exception as e:
            self.log(f"Error: {e}")

    def refresh_ui(self):
        self.left_table.setUpdatesEnabled(False)
        self.right_table.setUpdatesEnabled(False)

        self.left_table.setRowCount(0)
        self.right_table.setRowCount(0)

        display_list = [(idx, item) for idx, item in enumerate(self.po_entries) if item['status'] != 'Normal']

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

        # 恢复表格更新
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
        entry = self.po_entries[idx]
        source_show = f"[Plural ID] {entry['msgid_plural']}\n[Singular Source] {entry['new_ru_text']}" if entry[
            'is_plural'] else entry['new_ru_text']
        self.lbl_id.setText(f"ID: {entry['msgid']}")
        self.lbl_source.setText(f"Source: {source_show}")
        is_del = (entry['status'] == 'Deleted')
        self.btn_accept.setEnabled(not is_del)
        self.btn_edit.setEnabled(not is_del)

    def action_accept(self):
        if self.current_idx < 0: return
        self.po_entries[self.current_idx]['status'] = 'Saved'
        self.refresh_ui()

    def action_edit(self):
        if self.current_idx < 0: return
        entry = self.po_entries[self.current_idx]
        if entry['is_plural']:
            current_dict = entry['translated_plural']
            if not current_dict:
                edit_text = "[0]: "
            else:
                edit_text = "\n".join([f"[{k}]: {v}" for k, v in sorted(current_dict.items())])

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
        entry = self.po_entries[idx]
        if entry['is_plural']:
            entry['translated_plural'] = text_dict
        else:
            entry['translated_text'] = text_str
        self.refresh_ui()

    def save_progress(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Project", "progress.tmp", "Tmp (*.tmp)")
        if path:
            with open(path, 'wb') as f:
                pickle.dump(self.po_entries, f)
            self.log("Project Saved")

    def load_progress(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Project", "", "Tmp (*.tmp)")
        if path:
            with open(path, 'rb') as f:
                self.po_entries = pickle.load(f)
            self.refresh_ui()

    def show_final_dialog(self):
        d = FinalReviewDialog(self.po_entries, self)
        if d.exec():
            self.do_export()

    def do_export(self):
        save_path, _ = QFileDialog.getSaveFileName(self, "Export NEW Translated MO", "global.mo", "MO Files (*.mo)")
        if not save_path: return

        try:
            new_po = polib.POFile(wrapwidth=0)
            new_po.metadata = {
                'Project-Id-Version': 'Mir Korabley',
                'Last-Translator': 'DDF_FantasyV',
                'Language-Team': '<REPAD Localization Team>',
                'Language': 'zh_SG',
                'Content-Type': 'text/plain; charset=UTF-8',
                'Content-Transfer-Encoding': '8bit',
                'Plural-Forms': 'nplurals=1; plural=0;'
            }
            count = 0
            for item in self.po_entries:
                if item['status'] == 'Deleted': continue
                if item['is_plural']:
                    clean_plural_dict = {int(k): str(v) for k, v in item['translated_plural'].items()}
                    entry = polib.POEntry(msgid=item['msgid'], msgid_plural=item['msgid_plural'],
                                          msgstr_plural=clean_plural_dict)
                else:
                    entry = polib.POEntry(msgid=item['msgid'], msgstr=item['translated_text'])
                new_po.append(entry)
                count += 1

            new_po.save_as_mofile(save_path)
            new_po.save(save_path.replace('.mo', '.po'))
            QMessageBox.information(self, "Completed", f"Export Completed！{count} Total.")
        except Exception as e:
            self.log(f"Error: {e}")
            QMessageBox.critical(self, "Error", str(e))

    def closeEvent(self, event):
        if hasattr(self, 'log_window'):
            self.log_window.close()
        event.accept()