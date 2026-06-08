import time
from difflib import SequenceMatcher
from PyQt6.QtCore import QThread, pyqtSignal
import api_request


class TranslatorWorker(QThread):
    finished = pyqtSignal(int, str, dict)
    log_signal = pyqtSignal(str)

    def __init__(self, data_rows, ai_settings):
        super().__init__()
        self.data_rows = data_rows
        self.ai_settings = ai_settings
        self.context_cache = {}

    def clean_cached_translation(self, text):
        text = str(text or "").strip()
        if text.startswith("[AI]"):
            text = text[4:].strip()
        return text

    def get_row_translation(self, row):
        if row.get('is_plural'):
            values = row.get('translated_plural', {}).values()
            for value in values:
                cleaned = self.clean_cached_translation(value)
                if cleaned:
                    return cleaned
            return ""
        return self.clean_cached_translation(row.get('translated_text', ''))

    def get_cache_source(self, row):
        if row.get('status') == 'Modified' and row.get('old_ru_text'):
            return row.get('old_ru_text', '')
        return row.get('new_ru_text', '') or row.get('msgid', '')

    def build_context_cache(self):
        if not self.ai_settings.get("use_context_cache", False):
            return {}

        cache = {}
        for row in self.data_rows:
            source = str(self.get_cache_source(row)).strip()
            translation = self.get_row_translation(row)
            if source and translation and source not in cache:
                cache[source] = translation
        return cache

    def pick_context_examples(self, source_text):
        limit = int(self.ai_settings.get("context_cache_limit", 20))
        if limit <= 0 or not self.context_cache:
            return []

        ranked = []
        source_text = str(source_text or "")
        for source, translation in self.context_cache.items():
            if source == source_text:
                continue
            score = SequenceMatcher(None, source_text, source).ratio()
            ranked.append((score, source, translation))

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [
            {"source": source, "translation": translation}
            for _, source, translation in ranked[:limit]
        ]

    def add_context_cache_entry(self, source_text, translation):
        if not self.ai_settings.get("use_context_cache", False):
            return
        source = str(source_text or "").strip()
        cleaned = self.clean_cached_translation(translation)
        if source and cleaned and source not in self.context_cache:
            self.context_cache[source] = cleaned

    def run(self):
        self.log_signal.emit(">>> Translation Started...")
        self.context_cache = self.build_context_cache()
        if self.ai_settings.get("use_context_cache", False):
            self.log_signal.emit(f">>> Context cache loaded: {len(self.context_cache)} entries.")

        for i, row in enumerate(self.data_rows):
            if self.isInterruptionRequested():
                break

            current_trans_str = row['translated_text']
            current_trans_dict = row['translated_plural']
            has_trans = current_trans_str or current_trans_dict

            should_translate = (row['status'] == 'New' and not has_trans) or (row['status'] == 'Modified')

            if should_translate:
                original_text = row.get('new_ru_text', '') or row['msgid']
                trans_str = ""
                trans_dict = {}

                try:
                    cached_translation = self.context_cache.get(str(original_text).strip())
                    if self.ai_settings.get("use_context_cache", False) and cached_translation:
                        raw_result = cached_translation
                        self.log_signal.emit(f"Context cache hit [{row['entry_id']}].")
                    else:
                        context_examples = self.pick_context_examples(original_text)
                        raw_result = api_request.translate_with_gemini(
                            original_text,
                            self.ai_settings,
                            context_examples,
                        )
                        time.sleep(self.ai_settings.get("request_delay", 1.0))
                    ai_result = raw_result if "Error" in raw_result else f"[AI] {raw_result}"
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
                    self.add_context_cache_entry(original_text, final_text)
                    self.log_signal.emit(f"Translation (Plural) [{row['entry_id']}]: Append/Set -> {final_text}")
                else:
                    old_text = current_trans_str
                    if row['status'] == 'Modified' and old_text:
                        final_text = f"{old_text}\n{ai_result}" if ai_result not in old_text else old_text
                    else:
                        final_text = ai_result
                    trans_str = final_text
                    self.add_context_cache_entry(original_text, final_text)
                    self.log_signal.emit(f"Translation (Singular) [{row['entry_id']}]: Append/Set -> {trans_str}")

                self.finished.emit(i, trans_str, trans_dict)

        self.log_signal.emit(">>> Translation Process Finished.")
