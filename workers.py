import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from difflib import SequenceMatcher
from PyQt6.QtCore import QThread, pyqtSignal
import api_request


class TranslatorWorker(QThread):
    finished = pyqtSignal(int, str, dict)
    process_finished = pyqtSignal()
    log_signal = pyqtSignal(str)

    def __init__(self, data_rows, ai_settings):
        super().__init__()
        self.data_rows = data_rows
        self.ai_settings = ai_settings
        self.context_cache = {}

    def get_int_setting(self, key, default, minimum, maximum):
        try:
            value = int(self.ai_settings.get(key, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    def get_float_setting(self, key, default, minimum, maximum):
        try:
            value = float(self.ai_settings.get(key, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

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
        source_len = len(source_text)
        for source, translation in self.context_cache.items():
            if source == source_text:
                continue
            if source_len:
                length_ratio = min(source_len, len(source)) / max(source_len, len(source), 1)
                if length_ratio < 0.35:
                    continue
            quick_score = SequenceMatcher(None, source_text, source).quick_ratio()
            if quick_score < 0.25:
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

    def should_translate_row(self, row):
        current_trans_str = row['translated_text']
        current_trans_dict = row['translated_plural']
        has_trans = current_trans_str or current_trans_dict
        return (row['status'] == 'New' and not has_trans) or (row['status'] == 'Modified')

    def build_ai_result(self, row, raw_result):
        ai_result = raw_result if "Error" in raw_result else f"[AI] {raw_result}"
        trans_str = ""
        trans_dict = {}

        if row['is_plural']:
            old_text = row['translated_plural'].get(0, "")
            if row['status'] == 'Modified' and old_text:
                final_text = f"{old_text}\n{ai_result}" if ai_result not in old_text else old_text
            else:
                final_text = ai_result
            trans_dict = {0: final_text}
            log_message = f"Translation (Plural) [{row['entry_id']}]: Append/Set -> {final_text}"
        else:
            old_text = row['translated_text']
            if row['status'] == 'Modified' and old_text:
                final_text = f"{old_text}\n{ai_result}" if ai_result not in old_text else old_text
            else:
                final_text = ai_result
            trans_str = final_text
            log_message = f"Translation (Singular) [{row['entry_id']}]: Append/Set -> {trans_str}"

        return trans_str, trans_dict, log_message

    def translate_row(self, index, row, original_text, context_examples):
        try:
            raw_result = api_request.translate_with_gemini(
                original_text,
                self.ai_settings,
                context_examples,
            )
            request_delay = self.get_float_setting("request_delay", 0.0, 0.0, 60.0)
            if request_delay:
                time.sleep(request_delay)
            trans_str, trans_dict, log_message = self.build_ai_result(row, raw_result)
            return index, original_text, trans_str, trans_dict, log_message
        except Exception as e:
            error_result = f"Error: {str(e)}"
            trans_str, trans_dict, log_message = self.build_ai_result(row, error_result)
            return index, original_text, trans_str, trans_dict, f"API Error: {str(e)}\n{log_message}"

    def emit_result(self, index, original_text, trans_str, trans_dict, log_message):
        self.add_context_cache_entry(original_text, trans_str or next(iter(trans_dict.values()), ""))
        self.log_signal.emit(log_message)
        self.finished.emit(index, trans_str, trans_dict)

    def run(self):
        self.log_signal.emit(">>> Translation Started...")
        self.context_cache = self.build_context_cache()
        if self.ai_settings.get("use_context_cache", False):
            self.log_signal.emit(f">>> Context cache loaded: {len(self.context_cache)} entries.")

        max_workers = self.get_int_setting("max_concurrent_requests", 3, 1, 10)
        max_pending = max_workers * 2
        executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ai-translate")
        pending = {}

        try:
            for i, row in enumerate(self.data_rows):
                if self.isInterruptionRequested():
                    break
                if not self.should_translate_row(row):
                    continue

                original_text = row.get('new_ru_text', '') or row['msgid']
                cached_translation = self.context_cache.get(str(original_text).strip())
                if self.ai_settings.get("use_context_cache", False) and cached_translation:
                    trans_str, trans_dict, log_message = self.build_ai_result(row, cached_translation)
                    self.log_signal.emit(f"Context cache hit [{row['entry_id']}].")
                    self.emit_result(i, original_text, trans_str, trans_dict, log_message)
                    continue

                while len(pending) >= max_pending and not self.isInterruptionRequested():
                    self.collect_finished_tasks(pending)

                if self.isInterruptionRequested():
                    break

                context_examples = self.pick_context_examples(original_text)
                future = executor.submit(self.translate_row, i, row.copy(), original_text, context_examples)
                pending[future] = i

            while pending and not self.isInterruptionRequested():
                self.collect_finished_tasks(pending)
        finally:
            cancel_pending = self.isInterruptionRequested()
            for future in pending:
                future.cancel()
            executor.shutdown(wait=not cancel_pending, cancel_futures=True)

        self.process_finished.emit()
        self.log_signal.emit(">>> Translation Process Finished.")

    def collect_finished_tasks(self, pending):
        done, _ = wait(pending.keys(), timeout=0.2, return_when=FIRST_COMPLETED)
        for future in done:
            pending.pop(future, None)
            try:
                self.emit_result(*future.result())
            except Exception as e:
                self.log_signal.emit(f"API Error: {str(e)}")
