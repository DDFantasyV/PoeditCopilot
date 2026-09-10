import threading

import httpx


_openai_clients = {}
_openai_clients_lock = threading.Lock()


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


def normalize_timeout_seconds(value, default=45.0):
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return default
    return max(1.0, timeout)


def normalize_base_url(value):
    return str(value or "").strip().rstrip("/")


def build_chat_completions_url(base_url):
    base_url = normalize_base_url(base_url)
    if not base_url:
        return ""
    if base_url.lower().endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions"


def build_headers(api_key):
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def build_payload(model, prompt, settings):
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


def extract_response_text(response_data):
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


def get_client(timeout_seconds=None):
    timeout_seconds = normalize_timeout_seconds(timeout_seconds)
    with _openai_clients_lock:
        client = _openai_clients.get(timeout_seconds)
        if client is None:
            client = httpx.Client(timeout=timeout_seconds)
            _openai_clients[timeout_seconds] = client
        return client


def close_clients():
    """Close the shared httpx clients. Safe to call more than once."""
    with _openai_clients_lock:
        clients = list(_openai_clients.values())
        _openai_clients.clear()
    for client in clients:
        try:
            client.close()
        except Exception:
            pass


def request_chat_completion(api_key, base_url, model, prompt, settings):
    url = build_chat_completions_url(base_url)
    if not url:
        raise ValueError("Base URL cannot be empty")
    payload = build_payload(model, prompt, settings)
    client = get_client(settings.get("request_timeout", 45.0))
    response = client.post(url, headers=build_headers(api_key), json=payload)
    if response.status_code >= 400:
        raise ValueError(f"HTTP {response.status_code}: {describe_http_error(response)}")
    try:
        data = response.json()
    except Exception as e:
        raise ValueError(f"Invalid API response: {str(e)}") from e
    if not isinstance(data, dict):
        raise ValueError(f"Invalid API response: {str(data)[:500]}")
    return extract_response_text(data)


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


def validate_api_settings(settings):
    api_key = settings.get("api_key", "")
    base_url = settings.get("base_url", "")
    model = settings.get("model", "")
    source_lang = settings.get("source_lang", "")
    target_lang = settings.get("target_lang", "")
    prompt_template = settings.get("prompt_template", "")

    if not api_key or not api_key.strip():
        return False, "API Key cannot be empty", ["api_key"]
    if not base_url or not base_url.strip():
        return False, "Base URL cannot be empty", ["base_url"]
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
    except ValueError as e:
        return False, str(e), ["prompt_template"]

    try:
        result_text = request_chat_completion(api_key, base_url, model, prompt, settings)
    except (ValueError, httpx.HTTPError) as e:
        return False, f"Verify Error: {str(e)}", ["base_url", "api_key", "model"]
    except Exception as e:
        return False, f"Verify Error: {str(e)}", ["api_key", "model"]

    if result_text:
        return True, "AI translate settings are valid", []
    return False, "The API returned an empty response", ["api_key", "model"]


def translate_text(text, settings, context_examples=None):
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
        result_text = request_chat_completion(
            settings["api_key"],
            settings.get("base_url", ""),
            settings.get("model", ""),
            prompt,
            settings,
        )
    except Exception as e:
        return f"[Translation Error] {str(e)}"

    if result_text:
        return result_text
    return "[API Error] Empty response"
