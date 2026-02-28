import time
from PyQt6.QtCore import QThread, pyqtSignal
import api_request


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

            should_translate = (row['status'] == 'New' and not has_trans) or (row['status'] == 'Modified')

            if should_translate:
                original_text = row.get('new_ru_text', '')
                if not original_text:
                    original_text = row['msgid']

                trans_str = ""
                trans_dict = {}

                try:
                    raw_result = api_request.translate_with_gemini(original_text, self.api_key)
                    if "Error" in raw_result:
                        ai_result = raw_result
                    else:
                        ai_result = f"[AI] {raw_result}"
                    time.sleep(1.0) # 保持休眠防止触发API速率限制
                except Exception as e:
                    ai_result = f"Error: {str(e)}"
                    self.log_signal.emit(f"API Error: {str(e)}")

                if row['is_plural']:
                    old_text = current_trans_dict.get(0, "")
                    if row['status'] == 'Modified' and old_text:
                        final_text = f"{old_text}\n{ai_result}" if ai_result not in old_text else old_text
                    else:
                        final_text = ai_result
                    trans_dict = {0: final_text}
                    self.log_signal.emit(f"Translation (Plural) [{row['entry_id']}]: Append/Set -> {final_text}")
                else:
                    old_text = current_trans_str
                    if row['status'] == 'Modified' and old_text:
                        final_text = f"{old_text}\n{ai_result}" if ai_result not in old_text else old_text
                    else:
                        final_text = ai_result
                    trans_str = final_text
                    self.log_signal.emit(f"Translation (Singular) [{row['entry_id']}]: Append/Set -> {trans_str}")

                self.finished.emit(i, trans_str, trans_dict)

        self.log_signal.emit(">>> Translation Completed.")