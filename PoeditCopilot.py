import sys
import time
import os
import polib
import pickle
import re
import configparser
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QFileDialog, QTableWidget,
                             QTableWidgetItem, QSplitter, QLabel, QTextEdit,
                             QHeaderView, QInputDialog, QMessageBox, QDialog,
                             QPlainTextEdit, QLineEdit)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QColor

import api_request


# 日志窗口
class LogWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("System Log")
        self.resize(512, 384)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setStyleSheet(
            "background-color: #1e1e1e; color: #00FF00; font-family: Consolas; font-size: 10pt;")
        layout = QVBoxLayout()
        layout.addWidget(self.text_edit)
        self.setLayout(layout)

    def log(self, message):
        self.text_edit.append(message)
        self.text_edit.verticalScrollBar().setValue(self.text_edit.verticalScrollBar().maximum())


# 自定义对话框
class LargeInputDialog(QInputDialog):
    def __init__(self, parent=None, title="", label="", text=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setLabelText(label)
        self.setTextValue(text)
        # 启用多行文本模式 (这会使内部生成 QPlainTextEdit)
        self.setOption(QInputDialog.InputDialogOption.UsePlainTextEditForTextInput, True)
        # 设置窗口大小
        self.resize(512, 512)

        self.editor = self.findChild(QPlainTextEdit)
        if self.editor:
            self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
            self.editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.editor.setStyleSheet("""
                QPlainTextEdit {
                    font-family: 'Segoe UI', 'Microsoft YaHei', 'Consolas';
                    font-size: 10pt;
                    padding: 10px;
                    line-height: 150%;
                }
            """)

    def keyPressEvent(self, event):
        # 允许 Esc 退出
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)


# 多线程翻译
class TranslatorWorker(QThread):
    finished = pyqtSignal(int, str, dict)
    log_signal = pyqtSignal(str)

    def __init__(self, data_rows, api_key):
        super().__init__()
        self.data_rows = data_rows
        self.api_key = api_key

    def run(self):
        self.log_signal.emit(">>> Translation Started...")

        for i, row in enumerate(self.data_rows):
            if self.isInterruptionRequested():
                break

            current_trans_str = row['translated_text']
            current_trans_dict = row['translated_plural']
            has_trans = current_trans_str or current_trans_dict

            # 翻译逻辑：New且空，或者 Modified
            should_translate = (row['status'] == 'New' and not has_trans) or (row['status'] == 'Modified')

            if should_translate:
                original_text = row.get('new_ru_text', '')
                if not original_text: original_text = row['msgid']

                trans_str = ""
                trans_dict = {}

                try:
                    raw_result = api_request.translate_with_gemini(original_text, self.api_key)
                    if "Error" in raw_result:
                        ai_result = raw_result
                    else:
                        ai_result = f"[AI] {raw_result}"
                    time.sleep(1.0)

                except Exception as e:
                    ai_result = f"Error: {str(e)}"
                    self.log_signal.emit(f"API Error: {str(e)}")

                # 复数逻辑
                if row['is_plural']:
                    old_text = current_trans_dict.get(0, "")
                    if row['status'] == 'Modified' and old_text:
                        if ai_result not in old_text:
                            final_text = f"{old_text}\n{ai_result}"
                        else:
                            final_text = old_text
                    else:
                        final_text = ai_result
                    trans_dict = {0: final_text}
                    self.log_signal.emit(f"Translation (Plural) [{row['entry_id']}]: Append/Set -> {final_text}")

                # 单数逻辑
                else:
                    old_text = current_trans_str
                    if row['status'] == 'Modified' and old_text:
                        if ai_result not in old_text:
                            final_text = f"{old_text}\n{ai_result}"
                        else:
                            final_text = old_text
                    else:
                        final_text = ai_result
                    trans_str = final_text
                    self.log_signal.emit(f"Translation (Singular) [{row['entry_id']}]: Append/Set -> {trans_str}")

                self.finished.emit(i, trans_str, trans_dict)

        self.log_signal.emit(">>> Translation Completed.")


# 最终确认窗口
class FinalReviewDialog(QDialog):
    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review and Export")
        self.resize(1024, 768)
        self.layout = QVBoxLayout()
        self.data = data

        self.lbl_info = QLabel("Only entries existing in the new version will be exported.")
        self.lbl_info.setStyleSheet("font-weight: bold; color: #333;")

        self.table = QTableWidget()
        self.table.setColumnCount(4)  # 增加一列显示类型
        self.table.setHorizontalHeaderLabels(["ID", "Type", "Source", "Translation"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        self.populate_table()

        self.btn_save = QPushButton("Export")
        self.btn_save.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; padding: 10px;")
        self.btn_save.clicked.connect(self.accept)

        self.layout.addWidget(self.lbl_info)
        self.layout.addWidget(self.table)
        self.layout.addWidget(self.btn_save)
        self.setLayout(self.layout)

    def populate_table(self):
        export_data = [d for d in self.data if d['status'] != 'Deleted']
        self.table.setRowCount(len(export_data))

        for row, item in enumerate(export_data):
            # 处理翻译显示
            if item['is_plural']:
                # 将字典转为字符串显示
                trans_display = str(item['translated_plural'])
                type_str = "Plural"
            else:
                trans_display = item['translated_text']
                type_str = "Singular"

            self.table.setItem(row, 0, QTableWidgetItem(str(item['entry_id'])))
            self.table.setItem(row, 1, QTableWidgetItem(type_str))
            self.table.setItem(row, 2, QTableWidgetItem(item['new_ru_text']))
            self.table.setItem(row, 3, QTableWidgetItem(trans_display))


# 主界面
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Poedit Copilot v0.1.0")

        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))

        self.config_path = os.path.join(base_path, 'PoeditCopilot.ini')

        self.po_entries = []
        self.old_ru_map = {}
        self.old_cn_map = {}

        self.log_window = LogWindow()
        self.log_window.show()

        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        layout = QVBoxLayout()

        # 1. 顶部操作栏
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

        # 2. 功能按钮
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

        # 3. 主表格区域
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左表
        self.left_table = QTableWidget()
        self.left_table.setColumnCount(3)
        self.left_table.setHorizontalHeaderLabels(["ID", "New", "Old"])
        self.left_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.left_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.left_table.itemClicked.connect(self.on_table_click)

        # 右表
        self.right_table = QTableWidget()
        self.right_table.setColumnCount(3)
        self.right_table.setHorizontalHeaderLabels(["Status", "Translation", "Action"])
        self.right_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.right_table.itemClicked.connect(self.on_table_click)

        splitter.addWidget(self.left_table)
        splitter.addWidget(self.right_table)
        # 获取两个表格的纵向滚动条对象
        left_v_bar = self.left_table.verticalScrollBar()
        right_v_bar = self.right_table.verticalScrollBar()

        left_v_bar.valueChanged.connect(right_v_bar.setValue)
        right_v_bar.valueChanged.connect(left_v_bar.setValue)

        splitter.setSizes([768, 768])

        # 4. 底部编辑栏
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
                return None  # 用户点击取消

            input_key = text.strip()
            if not input_key:
                continue

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

    # 逻辑处理
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
                # 检测是否为复数
                is_plural = bool(entry.msgid_plural)

                if is_plural:
                    # 如果是复数，msgstr 为空，需要从 msgstr_plural 字典获取索引 0
                    new_ru_text = entry.msgstr_plural.get(0, "")
                else:
                    # 单数直接取 msgstr
                    new_ru_text = entry.msgstr

                self.po_entries.append({
                    'entry_id': idx + 1,
                    'msgid': entry.msgid,
                    'is_plural': is_plural,
                    'msgid_plural': entry.msgid_plural if is_plural else '',
                    'new_ru_text': new_ru_text,
                    'old_ru_text': '',
                    'status': 'New',
                    'translated_text': '',
                    'translated_plural': {}
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
            # 建立旧版映射，映射整个 Entry 对象以检查复数ID
            old_map = {e.msgid: e for e in old_mo}

            new_ids = set()

            for item in self.po_entries:
                mid = item['msgid']
                new_ids.add(mid)

                if mid in old_map:
                    old_entry = old_map[mid]
                    if item['is_plural']:
                        item['old_ru_text'] = old_entry.msgstr_plural.get(0, "")
                    else:
                        item['old_ru_text'] = old_entry.msgstr

                    # 检查 msgid_plural 是否变更
                    plural_changed = False
                    if item['is_plural']:
                        if old_entry.msgid_plural != item['msgid_plural']:
                            plural_changed = True

                    # 检查 msgstr 是否变更
                    text_changed = (item['new_ru_text'] != item['old_ru_text'])

                    if text_changed or plural_changed:
                        item['status'] = 'Modified'
                    else:
                        item['status'] = 'Normal'
                else:
                    item['status'] = 'New'

            # 处理删除
            for entry in old_mo:
                if entry.msgid not in new_ids:
                    self.po_entries.append({
                        'entry_id': -1,
                        'msgid': entry.msgid,
                        'is_plural': bool(entry.msgid_plural),
                        'msgid_plural': entry.msgid_plural,
                        'new_ru_text': '',
                        'old_ru_text': entry.msgstr,
                        'status': 'Deleted',
                        'translated_text': '',
                        'translated_plural': {}
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
            # 建立映射 msgid -> Entry对象
            cn_map = {e.msgid: e for e in cn_mo}

            count = 0
            for item in self.po_entries:
                if item['msgid'] in cn_map:
                    target_entry = cn_map[item['msgid']]

                    if item['is_plural']:
                        # 如果当前是复数，尝试获取目标文件的复数翻译
                        if target_entry.msgstr_plural:
                            item['translated_plural'] = target_entry.msgstr_plural.copy()
                        # 兼容性处理
                        elif target_entry.msgstr:
                            item['translated_plural'] = {0: target_entry.msgstr}
                    else:
                        # 单数
                        item['translated_text'] = target_entry.msgstr

                    count += 1

            self.log(f"Translation Loaded. {count} Paired.")
            self.refresh_ui()

        except Exception as e:
            self.log(f"Error: {e}")

    def refresh_ui(self):
        self.left_table.setRowCount(0)
        self.right_table.setRowCount(0)

        display_list = []
        for idx, item in enumerate(self.po_entries):
            if item['status'] == 'Normal': continue
            display_list.append((idx, item))

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

            # 左表
            # ID，标记复数
            id_str = str(item['entry_id']) if item['entry_id'] != -1 else "DEL"
            if item['is_plural']:
                id_str += " (PL)"

            self._set_item(self.left_table, row, 0, id_str, color, real_idx)
            self._set_item(self.left_table, row, 1, item['new_ru_text'], color, real_idx)
            self._set_item(self.left_table, row, 2, item['old_ru_text'], color, real_idx)

            # 右表
            self._set_item(self.right_table, row, 0, st, color, real_idx)

            # 翻译列，如果是复数，显示字典摘要
            if item['is_plural']:
                trans_txt = "; ".join([f"[{k}]{v}" for k, v in item['translated_plural'].items()])
            else:
                trans_txt = item['translated_text']

            self._set_item(self.right_table, row, 1, trans_txt, color, real_idx)

            act_txt = "TBD" if st in ['New', 'Modified'] else ""
            self._set_item(self.right_table, row, 2, act_txt, color, real_idx)

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
        if entry['is_plural']:
            source_show = f"[Plural ID] {entry['msgid_plural']}\n[Singular Source] {entry['new_ru_text']}"
        else:
            source_show = entry['new_ru_text']

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
            # 如果字典为空，默认提供中文索引0
            if not current_dict:
                edit_text = "[0]: "
            else:
                lines = []
                for k, v in sorted(current_dict.items()):
                    lines.append(f"[{k}]: {v}")
                edit_text = "\n".join(lines)

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
                        idx = int(match.group(1))
                        content = match.group(2)
                        new_dict[idx] = content
                    else:
                        new_dict[0] = line

                entry['translated_plural'] = new_dict
                entry['status'] = 'Saved'
                self.refresh_ui()
        else:
            dlg = LargeInputDialog(self, "Edit Translation", "Content:", entry['translated_text'])
            if dlg.exec():
                text = dlg.textValue()
                entry['translated_text'] = text
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
                    # 复数条目创建
                    # 确保字典 key 是 int
                    clean_plural_dict = {int(k): str(v) for k, v in item['translated_plural'].items()}

                    entry = polib.POEntry(
                        msgid=item['msgid'],
                        msgid_plural=item['msgid_plural'],
                        msgstr_plural=clean_plural_dict
                    )
                else:
                    # 单数条目创建
                    entry = polib.POEntry(
                        msgid=item['msgid'],
                        msgstr=item['translated_text']
                    )

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
        QApplication.quit()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.showMaximized()
    app.lastWindowClosed.connect(app.quit)
    sys.exit(app.exec())
