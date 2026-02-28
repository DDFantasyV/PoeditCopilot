from google import genai
from functools import lru_cache


@lru_cache(maxsize=1)
def get_gemini_client(api_key):
    return genai.Client(api_key=api_key)

def validate_api_key(api_key):
    if not api_key or not api_key.strip():
        return False, "API Key cannot be empty"

    try:
        client = get_gemini_client(api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Hello"
        )
        if response and response.text:
            return True, "API Key is valid"
        else:
            return False, "API Key is invalid"
    except Exception as e:
        return False, f"Verify Error: {str(e)}"

def translate_with_gemini(text, api_key, source_lang="Russian", target_lang="Simplified Chinese (for Game Localization)"):
    if not text or not text.strip():
        return ""

    try:
        client = get_gemini_client(api_key)
    except Exception as e:
        return f"[Client Init Error] {str(e)}"

    prompt = (
        f"You are a professional game localization translator. "
        f"Translate the following {source_lang} text into {target_lang}. "
        f"Rules:\n"
        f"1. Keep technical variables (like %(points)s, %s, {{0}}) unchanged.\n"
        f"2. Maintain the gaming context and tone.\n"
        f"3. Output ONLY the translated text, no explanations or extra quotes.\n"
        f"4. If the text is an ID or code, keep it as is.\n\n"
        f"Text: {text}"
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        if response.text:
            return response.text.strip()
        else:
            return "[API Error] Empty response"
    except Exception as e:
        return f"[Translation Error] {str(e)}"