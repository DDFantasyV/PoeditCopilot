from google import genai
from google.genai import types
import threading


_thread_clients = threading.local()


def normalize_timeout_seconds(value, default=45.0):
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return default
    return max(1.0, timeout)


def get_gemini_client(api_key, timeout_seconds=None):
    timeout_seconds = normalize_timeout_seconds(timeout_seconds)
    timeout_ms = int(timeout_seconds * 1000)
    cache_key = (api_key, timeout_ms)
    cache = getattr(_thread_clients, "cache", None)
    if cache is None:
        cache = {}
        _thread_clients.cache = cache
    if cache_key in cache:
        return cache[cache_key]

    try:
        http_options = types.HttpOptions(timeout=timeout_ms)
        client = genai.Client(api_key=api_key, http_options=http_options)
    except Exception:
        client = genai.Client(api_key=api_key)
    cache[cache_key] = client
    return client


def build_context_block(context_examples):
    if not context_examples:
        return ""

    lines = [
        "Reference translations from the current project:",
        "Use these examples to keep terminology, tone, and style consistent.",
        "If the source text is exactly the same as a reference source, reuse the reference translation unless it is clearly wrong.",
    ]
    for index, example in enumerate(context_examples, start=1):
        source = str(example.get("source", "")).strip()
        translation = str(example.get("translation", "")).strip()
        if not source or not translation:
            continue
        lines.append(f"{index}. Source: {source}")
        lines.append(f"   Translation: {translation}")

    return "\n".join(lines)


def build_prompt(text, source_lang, target_lang, prompt_template, context_examples=None):
    if not prompt_template or not prompt_template.strip():
        prompt_template = DEFAULT_PROMPT_TEMPLATE

    values = {
        "source_lang": source_lang,
        "target_lang": target_lang,
        "text": text,
    }

    try:
        prompt = prompt_template.format(**values)
    except KeyError as e:
        missing_key = str(e).strip("'")
        raise ValueError(f"Unknown prompt placeholder: {missing_key}") from e
    except (IndexError, ValueError) as e:
        raise ValueError(f"Invalid prompt template: {str(e)}") from e

    if "{text}" not in prompt_template:
        prompt = f"{prompt.rstrip()}\n\nText: {text}"
    context_block = build_context_block(context_examples)
    if context_block:
        prompt = f"{context_block}\n\n{prompt}"
    return prompt


def build_generation_config(settings):
    if not settings.get("use_advanced_params", False):
        return None

    config_values = {}
    param_map = {
        "temperature": "temperature",
        "top_p": "top_p",
        "top_k": "top_k",
        "max_output_tokens": "max_output_tokens",
    }
    for setting_key, api_key in param_map.items():
        value = settings.get(setting_key)
        if value is not None:
            config_values[api_key] = value

    if not config_values:
        return None
    return types.GenerateContentConfig(**config_values)


DEFAULT_PROMPT_TEMPLATE = (
    "You are a professional game localization translator.\n"
    "Translate the following {source_lang} text into {target_lang}.\n"
    "Rules:\n"
    "1. Keep technical variables like %(points)s, %s, and {{0}} unchanged.\n"
    "2. Maintain the gaming context and tone.\n"
    "3. Output only the translated text, with no explanations or extra quotes.\n"
    "4. If the text is an ID or code, keep it unchanged.\n\n"
    "Text: {text}"
)


def validate_api_settings(settings):
    api_key = settings.get("api_key", "")
    model = settings.get("model", "")
    source_lang = settings.get("source_lang", "")
    target_lang = settings.get("target_lang", "")
    prompt_template = settings.get("prompt_template", "")

    if not api_key or not api_key.strip():
        return False, "API Key cannot be empty", ["api_key"]
    if not model or not model.strip():
        return False, "Model cannot be empty", ["model"]
    if not source_lang or not source_lang.strip():
        return False, "Source language cannot be empty", ["source_lang"]
    if not target_lang or not target_lang.strip():
        return False, "Target language cannot be empty", ["target_lang"]
    if not prompt_template or not prompt_template.strip():
        return False, "Prompt template cannot be empty", ["prompt_template"]

    try:
        prompt = build_prompt("Hello", source_lang, target_lang, prompt_template)
        generation_config = build_generation_config(settings)
        client = get_gemini_client(api_key, settings.get("request_timeout", 45.0))
        kwargs = {"model": model, "contents": prompt}
        if generation_config:
            kwargs["config"] = generation_config
        response = client.models.generate_content(**kwargs)
        if response and response.text:
            return True, "AI translate settings are valid", []
        else:
            return False, "The API returned an empty response", ["api_key", "model"]
    except ValueError as e:
        return False, str(e), ["prompt_template"]
    except Exception as e:
        return False, f"Verify Error: {str(e)}", ["api_key", "model"]


def validate_api_key(api_key):
    settings = {
        "api_key": api_key,
        "model": "gemini-3.1-flash-lite",
        "source_lang": "Russian",
        "target_lang": "Simplified Chinese",
        "prompt_template": DEFAULT_PROMPT_TEMPLATE,
        "use_advanced_params": False,
    }
    is_valid, message, _ = validate_api_settings(settings)
    return is_valid, message


def translate_with_gemini(text, settings, context_examples=None):
    if not text or not text.strip():
        return ""

    try:
        client = get_gemini_client(settings["api_key"], settings.get("request_timeout", 45.0))
    except Exception as e:
        return f"[Client Init Error] {str(e)}"

    try:
        prompt = build_prompt(
            text,
            settings.get("source_lang", "Russian"),
            settings.get("target_lang", "Simplified Chinese"),
            settings.get("prompt_template", DEFAULT_PROMPT_TEMPLATE),
            context_examples,
        )
        generation_config = build_generation_config(settings)
        kwargs = {"model": settings.get("model", "gemini-3.1-flash-lite"), "contents": prompt}
        if generation_config:
            kwargs["config"] = generation_config
        response = client.models.generate_content(**kwargs)
        if response.text:
            return response.text.strip()
        else:
            return "[API Error] Empty response"
    except ValueError as e:
        return f"[Prompt Error] {str(e)}"
    except Exception as e:
        return f"[Translation Error] {str(e)}"
