import sys
from PyQt6.QtWidgets import QApplication
from main_window import MainWindow


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.showMaximized()
    # 确保主窗口关闭时整个程序安全退出
    app.lastWindowClosed.connect(app.quit)
    sys.exit(app.exec())