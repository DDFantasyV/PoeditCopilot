import re


class SearchEngine:
    @staticmethod
    def get_compiled_pattern(search_text, ignore_case, whole_word):
        flags = re.IGNORECASE if ignore_case else 0
        pattern_str = re.escape(search_text)
        if whole_word:
            pattern_str = r'\b' + pattern_str + r'\b'
        try:
            return re.compile(pattern_str, flags)
        except Exception:
            return None

    @staticmethod
    def match_text(search_text, target_text, ignore_case, exact_match, compiled_pattern):
        if not target_text:
            return False
        if exact_match:
            return search_text.lower() == target_text.lower() if ignore_case else search_text == target_text

        if compiled_pattern:
            return bool(compiled_pattern.search(target_text))
        return False

    @staticmethod
    def replace_in_text(target_text, search_text, replace_text, ignore_case, exact_match, compiled_pattern):
        if not target_text:
            return target_text
        if exact_match:
            if ignore_case and search_text.lower() == target_text.lower():
                return replace_text
            elif not ignore_case and search_text == target_text:
                return replace_text
            return target_text

        if compiled_pattern:
            try:
                return compiled_pattern.sub(replace_text, target_text)
            except Exception:
                return target_text
        return target_text