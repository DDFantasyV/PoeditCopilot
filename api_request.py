from google import genai
from google.genai import types
from functools import lru_cache


@lru_cache(maxsize=1)
def get_gemini_client(api_key):
    return genai.Client(api_key=api_key)


def build_prompt(text, source_lang, target_lang, prompt_template):
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
        client = get_gemini_client(api_key)
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


def translate_with_gemini(text, settings):
    if not text or not text.strip():
        return ""

    try:
        client = get_gemini_client(settings["api_key"])
    except Exception as e:
        return f"[Client Init Error] {str(e)}"

    try:
        prompt = build_prompt(
            text,
            settings.get("source_lang", "Russian"),
            settings.get("target_lang", "Simplified Chinese"),
            settings.get("prompt_template", DEFAULT_PROMPT_TEMPLATE),
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
