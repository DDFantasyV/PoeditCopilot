from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTextEdit, QInputDialog,
                             QPlainTextEdit, QDialog, QLabel, QLineEdit,
                             QCheckBox, QPushButton, QHBoxLayout, QGridLayout)
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

class FindReplaceDialog(QDialog):
    def __init__(self, parent=None, is_replace=False):
        super().__init__(parent)
        self.setWindowTitle("Replace" if is_replace else "Find")
        self.is_replace = is_replace
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        grid = QGridLayout()
        self.lbl_find = QLabel("Find:")
        self.txt_find = QLineEdit()
        grid.addWidget(self.lbl_find, 0, 0)
        grid.addWidget(self.txt_find, 0, 1)

        if self.is_replace:
            self.lbl_replace = QLabel("Replaced by:")
            self.txt_replace = QLineEdit()
            grid.addWidget(self.lbl_replace, 1, 0)
            grid.addWidget(self.txt_replace, 1, 1)

        layout.addLayout(grid)

        self.chk_ignore_case = QCheckBox("Ignore Caps")
        self.chk_exact_match = QCheckBox("Exact Match")
        self.chk_whole_word = QCheckBox("Whole String Only")
        self.chk_ignore_case.setChecked(True)

        opts_layout = QVBoxLayout()
        opts_layout.addWidget(self.chk_ignore_case)
        opts_layout.addWidget(self.chk_exact_match)
        opts_layout.addWidget(self.chk_whole_word)
        layout.addLayout(opts_layout)

        btn_layout = QHBoxLayout()
        self.btn_find_prev = QPushButton("Previous")
        self.btn_find = QPushButton("Next")
        btn_layout.addWidget(self.btn_find_prev)
        btn_layout.addWidget(self.btn_find)

        if self.is_replace:
            self.btn_replace = QPushButton("Replace")
            self.btn_replace_all = QPushButton("Replace All")
            btn_layout.addWidget(self.btn_replace)
            btn_layout.addWidget(self.btn_replace_all)

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)
        self.setLayout(layout)