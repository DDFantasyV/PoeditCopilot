from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTextEdit, QInputDialog,
                             QPlainTextEdit)
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