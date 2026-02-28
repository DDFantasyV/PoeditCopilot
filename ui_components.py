from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTextEdit, QInputDialog,
                             QPlainTextEdit, QDialog, QLabel, QTableWidget,
                             QTableWidgetItem, QHeaderView, QPushButton)
from PyQt6.QtCore import Qt


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

class LargeInputDialog(QInputDialog):
    def __init__(self, parent=None, title="", label="", text=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setLabelText(label)
        self.setTextValue(text)
        self.setOption(QInputDialog.InputDialogOption.UsePlainTextEditForTextInput, True)
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
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

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
        self.table.setColumnCount(4)
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
            if item['is_plural']:
                trans_display = str(item['translated_plural'])
                type_str = "Plural"
            else:
                trans_display = item['translated_text']
                type_str = "Singular"

            self.table.setItem(row, 0, QTableWidgetItem(str(item['entry_id'])))
            self.table.setItem(row, 1, QTableWidgetItem(type_str))
            self.table.setItem(row, 2, QTableWidgetItem(item['new_ru_text']))
            self.table.setItem(row, 3, QTableWidgetItem(trans_display))