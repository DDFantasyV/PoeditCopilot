from google import genai
import time


def validate_api_key(api_key):
    """
    验证 API Key 是否有效
    :return: (bool, str) -> (是否成功, 错误信息/成功信息)
    """
    if not api_key or not api_key.strip():
        return False, "API Key cannot be empty"

    try:
        # 实例化客户端
        client = genai.Client(api_key=api_key)

        # 发送一个极简的测试请求
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


def translate_with_gemini(text, api_key, source_lang="Russian",
                          target_lang="Simplified Chinese (for Game Localization)"):
    """
    调用 Google Genai (新版 SDK) 进行翻译
    :param text: 待翻译文本
    :param api_key: 用户的 API Key (动态传入)
    :param source_lang: 源语言
    :param target_lang: 目标语言
    :return: 翻译后的文本字符串
    """
    if not text or not text.strip():
        return ""

    try:
        # 使用传入的 api_key 实例化
        client = genai.Client(api_key=api_key)
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
        return f"[API Error] {str(e)}"
