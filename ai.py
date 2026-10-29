"""Local AI connection for ORBIT, using Ollama's chat API."""

import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen2.5:3b"  # Change this if you downloaded another model.
SYSTEM_PROMPT = (
    "You are ORBIT, a helpful desktop AI assistant. "
    "Be friendly, accurate, and clear. Prefer concise answers. "
    "If you are unsure, say so rather than inventing facts."
)


def ask_ai(conversation, timeout=180, language="English"):
    """Send conversation messages to local Ollama and return the assistant text.

    conversation should be a list like:
    [{"role": "user", "content": "Hello"}]
    """
    language = str(language).strip().title()
    if language == "Bangla":
        language_rule = (
            "STRICT LANGUAGE MODE: Write every part of your answer in natural Bengali using Bengali script. "
            "Do not answer in English or Banglish unless the user explicitly requests translation into English. "
            "Keep code, commands, and technical identifiers as needed."
        )
    else:
        language_rule = (
            "STRICT LANGUAGE MODE: Write every part of your answer in clear English. "
            "Do not use Bengali or Banglish unless the user explicitly requests translation into Bengali."
        )
    messages = [{"role": "system", "content": SYSTEM_PROMPT + "\\n\\n" + language_rule}]
    messages.extend(conversation)

    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.7},
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        answer = data.get("message", {}).get("content", "").strip()
        if not answer:
            return "I received an empty response. Please try again."
        return answer
    except requests.exceptions.ConnectionError:
        return (
            "I can't connect to Ollama. Please open Ollama and check that it is running. "
            "Then run `ollama list` in your terminal."
        )
    except requests.exceptions.Timeout:
        return "The model is taking too long to respond. Try again or use a smaller model."
    except requests.exceptions.HTTPError as exc:
        if response.status_code == 404:
            return (
                f"Model '{MODEL_NAME}' was not found. Run `ollama pull {MODEL_NAME}` "
                "in the VS Code terminal, then try again."
            )
        return f"Ollama returned an HTTP error: {exc}"
    except (ValueError, KeyError) as exc:
        return f"Could not read Ollama's response: {exc}"
    except requests.exceptions.RequestException as exc:
        return f"AI connection error: {exc}"
