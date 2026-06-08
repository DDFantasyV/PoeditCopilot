from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTextEdit, QInputDialog,
                             QPlainTextEdit, QDialog, QLabel, QLineEdit,
                             QCheckBox, QPushButton, QHBoxLayout, QGridLayout,
                             QMessageBox, QComboBox, QDoubleSpinBox, QSpinBox,
                             QGroupBox)
from PyQt6.QtCore import Qt, QThread


PROMPT_PRESETS = {
    "Game Localization": (
        "You are a professional game localization translator.\n"
        "Translate the following {source_lang} text into {target_lang}.\n"
        "Rules:\n"
        "1. Keep technical variables like %(points)s, %s, and {{0}} unchanged.\n"
        "2. Maintain the gaming context and tone.\n"
        "3. Output only the translated text, with no explanations or extra quotes.\n"
        "4. If the text is an ID or code, keep it unchanged.\n\n"
        "Text: {text}"
    ),
    "Literal Translation": (
        "Translate the following {source_lang} text into {target_lang}.\n"
        "Keep placeholders, tags, and line breaks unchanged.\n"
        "Output only the translated text.\n\n"
        "Text: {text}"
    ),
    "Concise UI Text": (
        "Translate this {source_lang} UI text into concise {target_lang}.\n"
        "Keep placeholders and formatting tokens unchanged.\n"
        "Prefer short labels that fit game interface buttons and menus.\n\n"
        "Text: {text}"
    ),
}


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

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            event.ignore()
        else:
            super().keyPressEvent(event)

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
            event.ignore()
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

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            event.ignore()
        else:
            super().keyPressEvent(event)

class LanguageDialog(QDialog):
    def __init__(self, parent=None, origin="", target=""):
        super().__init__(parent)
        self.setWindowTitle("Language Settings")
        self.resize(300, 100)
        layout = QVBoxLayout(self)

        grid = QGridLayout()
        self.lbl_origin = QLabel("Origin Language:")
        self.txt_origin = QLineEdit(origin)
        self.lbl_target = QLabel("Target Language:")
        self.txt_target = QLineEdit(target)

        grid.addWidget(self.lbl_origin, 0, 0)
        grid.addWidget(self.txt_origin, 0, 1)
        grid.addWidget(self.lbl_target, 1, 0)
        grid.addWidget(self.txt_target, 1, 1)
        layout.addLayout(grid)

        btn_layout = QHBoxLayout()
        self.btn_ok = QPushButton("OK")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_ok.clicked.connect(self.validate_and_accept)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_ok)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

    def validate_and_accept(self):
        if not self.txt_origin.text().strip() or not self.txt_target.text().strip():
            QMessageBox.warning(self, "Error", "Origin and Target languages cannot be empty!")
            return
        self.accept()


class SettingsValidationWorker(QThread):
    def __init__(self, validate_callback, settings):
        super().__init__()
        self.validate_callback = validate_callback
        self.settings = settings
        self.result = (False, "Validation did not complete.", ["api_key", "model"])

    def run(self):
        try:
            if self.validate_callback:
                is_valid, message, invalid_fields = self.validate_callback(self.settings)
            else:
                is_valid, message, invalid_fields = True, "", []
        except Exception as e:
            is_valid, message, invalid_fields = False, f"Verify Error: {str(e)}", ["api_key", "model"]
        self.result = (is_valid, message, invalid_fields)


class AITranslateDialog(QDialog):
    def __init__(self, parent=None, settings=None, validate_callback=None):
        super().__init__(parent)
        self.settings = settings or {}
        self.validate_callback = validate_callback
        self.field_widgets = {}
        self.normal_styles = {}
        self.validation_worker = None

        self.setWindowTitle("AI Translate")
        self.resize(720, 700)
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)

        api_group = QGroupBox("Connection")
        api_grid = QGridLayout(api_group)
        self.txt_api_key = QLineEdit()
        self.txt_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_model = QLineEdit()
        self.txt_source_lang = QLineEdit()
        self.txt_target_lang = QLineEdit()

        api_grid.addWidget(QLabel("API Key:"), 0, 0)
        api_grid.addWidget(self.txt_api_key, 0, 1)
        api_grid.addWidget(QLabel("Model:"), 1, 0)
        api_grid.addWidget(self.txt_model, 1, 1)
        api_grid.addWidget(QLabel("Source Language:"), 2, 0)
        api_grid.addWidget(self.txt_source_lang, 2, 1)
        api_grid.addWidget(QLabel("Target Language:"), 3, 0)
        api_grid.addWidget(self.txt_target_lang, 3, 1)
        layout.addWidget(api_group)

        prompt_group = QGroupBox("Prompt")
        prompt_layout = QVBoxLayout(prompt_group)
        preset_layout = QHBoxLayout()
        self.cmb_preset = QComboBox()
        self.cmb_preset.addItems(list(PROMPT_PRESETS.keys()) + ["Custom"])
        self.cmb_preset.currentTextChanged.connect(self.on_preset_changed)
        preset_layout.addWidget(QLabel("Preset:"))
        preset_layout.addWidget(self.cmb_preset, 1)
        prompt_layout.addLayout(preset_layout)

        self.txt_prompt = QPlainTextEdit()
        self.txt_prompt.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.txt_prompt.setPlaceholderText("Use {source_lang}, {target_lang}, and {text} as placeholders.")
        prompt_layout.addWidget(self.txt_prompt, 1)
        layout.addWidget(prompt_group, 1)

        cache_group = QGroupBox("Context Cache")
        cache_grid = QGridLayout(cache_group)
        self.chk_use_context_cache = QCheckBox("Use existing translations as context")
        self.spin_context_cache_limit = QSpinBox()
        self.spin_context_cache_limit.setRange(1, 100)
        cache_grid.addWidget(self.chk_use_context_cache, 0, 0, 1, 2)
        cache_grid.addWidget(QLabel("Reference Examples:"), 1, 0)
        cache_grid.addWidget(self.spin_context_cache_limit, 1, 1)
        layout.addWidget(cache_group)

        advanced_group = QGroupBox("Optional API Parameters")
        advanced_grid = QGridLayout(advanced_group)
        self.chk_use_advanced = QCheckBox("Use optional generation parameters")
        self.spin_temperature = QDoubleSpinBox()
        self.spin_temperature.setRange(0.0, 2.0)
        self.spin_temperature.setSingleStep(0.05)
        self.spin_temperature.setDecimals(2)
        self.spin_top_p = QDoubleSpinBox()
        self.spin_top_p.setRange(0.0, 1.0)
        self.spin_top_p.setSingleStep(0.05)
        self.spin_top_p.setDecimals(2)
        self.spin_top_k = QSpinBox()
        self.spin_top_k.setRange(1, 200)
        self.spin_max_output_tokens = QSpinBox()
        self.spin_max_output_tokens.setRange(1, 65536)
        self.spin_request_delay = QDoubleSpinBox()
        self.spin_request_delay.setRange(0.0, 60.0)
        self.spin_request_delay.setSingleStep(0.25)
        self.spin_request_delay.setDecimals(2)
        self.spin_request_timeout = QDoubleSpinBox()
        self.spin_request_timeout.setRange(1.0, 300.0)
        self.spin_request_timeout.setSingleStep(5.0)
        self.spin_request_timeout.setDecimals(1)
        self.spin_max_concurrent = QSpinBox()
        self.spin_max_concurrent.setRange(1, 10)

        advanced_grid.addWidget(self.chk_use_advanced, 0, 0, 1, 2)
        advanced_grid.addWidget(QLabel("Temperature:"), 1, 0)
        advanced_grid.addWidget(self.spin_temperature, 1, 1)
        advanced_grid.addWidget(QLabel("Top P:"), 2, 0)
        advanced_grid.addWidget(self.spin_top_p, 2, 1)
        advanced_grid.addWidget(QLabel("Top K:"), 3, 0)
        advanced_grid.addWidget(self.spin_top_k, 3, 1)
        advanced_grid.addWidget(QLabel("Max Output Tokens:"), 4, 0)
        advanced_grid.addWidget(self.spin_max_output_tokens, 4, 1)
        advanced_grid.addWidget(QLabel("Request Delay Seconds:"), 5, 0)
        advanced_grid.addWidget(self.spin_request_delay, 5, 1)
        advanced_grid.addWidget(QLabel("Request Timeout Seconds:"), 6, 0)
        advanced_grid.addWidget(self.spin_request_timeout, 6, 1)
        advanced_grid.addWidget(QLabel("Max Concurrent Requests:"), 7, 0)
        advanced_grid.addWidget(self.spin_max_concurrent, 7, 1)
        layout.addWidget(advanced_group)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

        btn_layout = QHBoxLayout()
        self.btn_ok = QPushButton("OK")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_ok.clicked.connect(self.validate_and_accept)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_ok)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        self.field_widgets = {
            "api_key": self.txt_api_key,
            "model": self.txt_model,
            "source_lang": self.txt_source_lang,
            "target_lang": self.txt_target_lang,
            "prompt_template": self.txt_prompt,
            "context_cache_limit": self.spin_context_cache_limit,
            "temperature": self.spin_temperature,
            "top_p": self.spin_top_p,
            "top_k": self.spin_top_k,
            "max_output_tokens": self.spin_max_output_tokens,
            "request_delay": self.spin_request_delay,
            "request_timeout": self.spin_request_timeout,
            "max_concurrent_requests": self.spin_max_concurrent,
        }
        self.normal_styles = {name: widget.styleSheet() for name, widget in self.field_widgets.items()}

    def load_settings(self):
        self.txt_api_key.setText(self.settings.get("api_key", ""))
        self.txt_model.setText(self.settings.get("model", "gemini-3.1-flash-lite"))
        self.txt_source_lang.setText(self.settings.get("source_lang", "Russian"))
        self.txt_target_lang.setText(self.settings.get("target_lang", "Simplified Chinese"))
        self.txt_prompt.setPlainText(self.settings.get("prompt_template", PROMPT_PRESETS["Game Localization"]))
        self.cmb_preset.setCurrentText(self.settings.get("prompt_preset", "Game Localization"))
        self.chk_use_context_cache.setChecked(self.settings.get("use_context_cache", False))
        self.spin_context_cache_limit.setValue(int(self.settings.get("context_cache_limit", 20)))
        self.chk_use_advanced.setChecked(self.settings.get("use_advanced_params", False))
        self.spin_temperature.setValue(float(self.settings.get("temperature", 0.7)))
        self.spin_top_p.setValue(float(self.settings.get("top_p", 0.95)))
        self.spin_top_k.setValue(int(self.settings.get("top_k", 40)))
        self.spin_max_output_tokens.setValue(int(self.settings.get("max_output_tokens", 2048)))
        self.spin_request_delay.setValue(float(self.settings.get("request_delay", 0.0)))
        self.spin_request_timeout.setValue(float(self.settings.get("request_timeout", 45.0)))
        self.spin_max_concurrent.setValue(int(self.settings.get("max_concurrent_requests", 3)))

    def on_preset_changed(self, preset_name):
        if preset_name in PROMPT_PRESETS:
            self.txt_prompt.setPlainText(PROMPT_PRESETS[preset_name])

    def get_settings(self):
        return {
            "api_key": self.txt_api_key.text().strip(),
            "model": self.txt_model.text().strip(),
            "source_lang": self.txt_source_lang.text().strip(),
            "target_lang": self.txt_target_lang.text().strip(),
            "prompt_preset": self.cmb_preset.currentText(),
            "prompt_template": self.txt_prompt.toPlainText().strip(),
            "use_context_cache": self.chk_use_context_cache.isChecked(),
            "context_cache_limit": self.spin_context_cache_limit.value(),
            "use_advanced_params": self.chk_use_advanced.isChecked(),
            "temperature": self.spin_temperature.value(),
            "top_p": self.spin_top_p.value(),
            "top_k": self.spin_top_k.value(),
            "max_output_tokens": self.spin_max_output_tokens.value(),
            "request_delay": self.spin_request_delay.value(),
            "request_timeout": self.spin_request_timeout.value(),
            "max_concurrent_requests": self.spin_max_concurrent.value(),
        }

    def mark_invalid_fields(self, field_names):
        invalid_style = "border: 1px solid #d93025; background-color: #fff0f0;"
        for name, widget in self.field_widgets.items():
            widget.setStyleSheet(invalid_style if name in field_names else self.normal_styles[name])

    def reject(self):
        if self.validation_worker and self.validation_worker.isRunning():
            self.lbl_status.setText("Please wait until validation finishes.")
            return
        super().reject()

    def validate_and_accept(self):
        self.mark_invalid_fields([])
        settings = self.get_settings()
        missing_fields = [
            name for name in ("api_key", "model", "source_lang", "target_lang", "prompt_template")
            if not settings[name]
        ]
        if missing_fields:
            self.mark_invalid_fields(missing_fields)
            self.lbl_status.setText("Please fill in all required fields.")
            return

        self.btn_ok.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.lbl_status.setText("Validating AI translate settings...")

        self.validation_worker = SettingsValidationWorker(self.validate_callback, settings)
        self.validation_worker.finished.connect(self.on_validation_finished)
        self.validation_worker.start()

    def on_validation_finished(self):
        worker = self.validation_worker
        if not worker:
            return
        is_valid, message, invalid_fields = worker.result
        worker.deleteLater()
        self.validation_worker = None

        self.btn_ok.setEnabled(True)
        self.btn_cancel.setEnabled(True)
        if is_valid:
            self.lbl_status.setText(message)
            self.accept()
        else:
            self.mark_invalid_fields(invalid_fields)
            self.lbl_status.setText(message)
