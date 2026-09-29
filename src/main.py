import os
import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from main_window import MainWindow


def resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    else:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


if __name__ == '__main__':
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('PoeditCopilot')

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(resource_path('PoeditCopilot.png')))
    window = MainWindow()
    window.showMaximized()
    app.lastWindowClosed.connect(app.quit)
    sys.exit(app.exec())
