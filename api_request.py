import threading

import httpx
from google import genai
from google.genai import types


_thread_clients = threading.local()
_openai_clients = {}
_openai_clients_lock = threading.Lock()


API_FORMAT_GEMINI = "gemini"
API_FORMAT_OPENAI = "openai"
API_FORMAT_CHOICES = (
    (API_FORMAT_GEMINI, "Google Gemini"),
    (API_FORMAT_OPENAI, "OpenAI Compatible"),
)
OPENAI_COMPATIBLE_HOST_HINTS = (
    "api.deepseek.com",
    "api.openai.com",
    "openrouter.ai",
    "api.moonshot.cn",
    "api.siliconflow.cn",
    "api.groq.com",
    "api.together.xyz",
    "api.mistral.ai",
    "dashscope.aliyuncs.com",
)


def normalize_timeout_seconds(value, default=45.0):
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return default
    return max(1.0, timeout)


def normalize_base_url(value):
    return str(value or "").strip().rstrip("/")


def normalize_api_format(value):
    text = str(value or "").strip().lower()
    if text in ("openai", "openai_compatible", "openai-compatible", "compatible"):
        return API_FORMAT_OPENAI
    return API_FORMAT_GEMINI


def infer_api_format_from_base_url(base_url):
    """Guess the API format for legacy configs that predate the format option.

    Only well-known OpenAI compatible endpoints are inferred, so existing Gemini
    proxy setups keep working. Anything unrecognized stays on Gemini.
    """
    normalized = normalize_base_url(base_url).lower()
    if not normalized or "googleapis.com" in normalized:
        return API_FORMAT_GEMINI
    host = ""
    if "://" in normalized:
        host = normalized.split("://", 1)[1].split("/", 1)[0]
    host = host.split(":", 1)[0]
    if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"):
        return API_FORMAT_OPENAI
    for hint in OPENAI_COMPATIBLE_HOST_HINTS:
        if host == hint or host.endswith("." + hint):
            return API_FORMAT_OPENAI
    if normalized.endswith("/v1"):
        return API_FORMAT_OPENAI
    return API_FORMAT_GEMINI


def resolve_api_format(value, base_url=None):
    if str(value or "").strip():
        return normalize_api_format(value)
    return infer_api_format_from_base_url(base_url)


def build_openai_chat_url(base_url):
    base_url = normalize_base_url(base_url)
    if not base_url:
        return ""
    if base_url.lower().endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions"


def build_openai_headers(api_key):
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def build_openai_payload(model, prompt, settings):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if settings.get("use_advanced_params", False):
        param_map = {
            "temperature": "temperature",
            "top_p": "top_p",
            "max_output_tokens": "max_tokens",
        }
        for setting_key, api_key in param_map.items():
            value = settings.get(setting_key)
            if value is not None:
                payload[api_key] = value
    return payload


def extract_openai_text(response_data):
    choices = response_data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts).strip()
    if content is None:
        return ""
    return str(content).strip()


def request_openai_chat(api_key, base_url, model, prompt, settings):
    url = build_openai_chat_url(base_url)
    if not url:
        raise ValueError("Base URL is required for the OpenAI compatible API format")
    payload = build_openai_payload(model, prompt, settings)
    client = get_openai_client(settings.get("request_timeout", 45.0))
    response = client.post(url, headers=build_openai_headers(api_key), json=payload)
    if response.status_code >= 400:
        raise ValueError(f"HTTP {response.status_code}: {describe_http_error(response)}")
    try:
        data = response.json()
    except Exception as e:
        raise ValueError(f"Invalid API response: {str(e)}") from e
    if not isinstance(data, dict):
        raise ValueError(f"Invalid API response: {str(data)[:500]}")
    return extract_openai_text(data)


def get_openai_client(timeout_seconds=None):
    timeout_seconds = normalize_timeout_seconds(timeout_seconds)
    with _openai_clients_lock:
        client = _openai_clients.get(timeout_seconds)
        if client is None:
            client = httpx.Client(timeout=timeout_seconds)
            _openai_clients[timeout_seconds] = client
        return client


def close_openai_clients():
    """Close the shared httpx clients. Safe to call more than once."""
    with _openai_clients_lock:
        clients = list(_openai_clients.values())
        _openai_clients.clear()
    for client in clients:
        try:
            client.close()
        except Exception:
            pass


def describe_http_error(response):
    try:
        data = response.json()
    except Exception:
        text = response.text.strip()
        return text[:500] if text else response.reason_phrase
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or error)
    if error:
        return str(error)
    return str(data)[:500]


def get_gemini_client(api_key, timeout_seconds=None, base_url=None):
    timeout_seconds = normalize_timeout_seconds(timeout_seconds)
    timeout_ms = int(timeout_seconds * 1000)
    base_url = normalize_base_url(base_url)
    cache_key = (api_key, timeout_ms, base_url)
    cache = getattr(_thread_clients, "cache", None)
    if cache is None:
        cache = {}
        _thread_clients.cache = cache
    if cache_key in cache:
        return cache[cache_key]

    options_kwargs = {"timeout": timeout_ms}
    if base_url:
        options_kwargs["base_url"] = base_url

    try:
        http_options = types.HttpOptions(**options_kwargs)
        client = genai.Client(api_key=api_key, http_options=http_options)
    except Exception:
        if base_url:
            raise
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


def is_openai_format(settings):
    return (
        resolve_api_format(settings.get("api_format"), settings.get("base_url"))
        == API_FORMAT_OPENAI
    )


def require_base_url_for_openai(settings):
    if is_openai_format(settings) and not normalize_base_url(settings.get("base_url")):
        return False, "Base URL cannot be empty for the OpenAI compatible API format"
    return True, ""


def generate_text(api_key, model, prompt, settings):
    if is_openai_format(settings):
        return request_openai_chat(api_key, settings.get("base_url"), model, prompt, settings)

    generation_config = build_generation_config(settings)
    client = get_gemini_client(
        api_key,
        settings.get("request_timeout", 45.0),
        settings.get("base_url"),
    )
    kwargs = {"model": model, "contents": prompt}
    if generation_config:
        kwargs["config"] = generation_config
    response = client.models.generate_content(**kwargs)
    if response and response.text:
        return response.text.strip()
    return ""


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
    base_url_ok, base_url_error = require_base_url_for_openai(settings)
    if not base_url_ok:
        return False, base_url_error, ["base_url"]

    try:
        prompt = build_prompt("Hello", source_lang, target_lang, prompt_template)
    except ValueError as e:
        return False, str(e), ["prompt_template"]

    try:
        result_text = generate_text(api_key, model, prompt, settings)
    except (ValueError, httpx.HTTPError) as e:
        return False, f"Verify Error: {str(e)}", ["base_url", "api_key", "model"]
    except Exception as e:
        return False, f"Verify Error: {str(e)}", ["api_key", "model"]

    if result_text:
        return True, "AI translate settings are valid", []
    return False, "The API returned an empty response", ["api_key", "model"]


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
        prompt = build_prompt(
            text,
            settings.get("source_lang", "Russian"),
            settings.get("target_lang", "Simplified Chinese"),
            settings.get("prompt_template", DEFAULT_PROMPT_TEMPLATE),
            context_examples,
        )
    except ValueError as e:
        return f"[Prompt Error] {str(e)}"

    try:
        result_text = generate_text(
            settings["api_key"],
            settings.get("model", "gemini-3.1-flash-lite"),
            prompt,
            settings,
        )
    except Exception as e:
        return f"[Translation Error] {str(e)}"

    if result_text:
        return result_text
    return "[API Error] Empty response"
