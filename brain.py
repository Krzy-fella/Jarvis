"""
brain.py — Multi-LLM routing and tool-calling logic.
"""

import json
import re
import shlex
import time

import config
from privacy import redact


def _system_prompt():
    from actions import installed_tool_names
    return config.SYSTEM_PROMPT + "\nInstalled optional command names: " + ", ".join(installed_tool_names())


class BrainError(Exception):
    """Raised when a provider call fails after retries."""


def _safe_parse_json(raw_text: str) -> dict:
    """
    Extract and parse the JSON object a model returned.
    """
    text = raw_text.strip()

    # Strip ```json ... ``` or ``` ... ``` fences if present.
    fence_match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    if not text.startswith("{"):
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            text = brace_match.group(0)

    try:
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("Expected a JSON object")
        if not isinstance(parsed.get("speak", ""), str):
            raise ValueError("speak must be a string")
        if "speak" not in parsed:
            parsed["speak"] = ""
        if "action" not in parsed or not isinstance(parsed["action"], dict):
            parsed["action"] = {"tool": "none", "args": {}}
        parsed["action"].setdefault("tool", "none")
        parsed["action"].setdefault("args", {})
        if not isinstance(parsed["action"]["tool"], str) or not isinstance(parsed["action"]["args"], dict):
            raise ValueError("Invalid action shape")
        return parsed
    except (ValueError, TypeError):
        return {
            "speak": raw_text.strip() or "I had trouble forming a structured response.",
            "action": {"tool": "none", "args": {}},
        }


def _call_ollama(messages: list) -> str:
    import ollama

    if config.OLLAMA_CLOUD_ONLY and not config.OLLAMA_MODEL.endswith(("-cloud", ":cloud")):
        raise BrainError("Ollama is configured for cloud only. Choose a model ending in -cloud or :cloud; no local model will be downloaded.")
    client = ollama.Client(host=config.OLLAMA_HOST, timeout=config.REQUEST_TIMEOUT)
    try:
        response = client.chat(
            model=config.OLLAMA_MODEL,
            messages=[{"role": "system", "content": _system_prompt()}] + messages,
            options={"temperature": 0.4},
            format="json",
        )
    except ollama.ResponseError as exc:
        if exc.status_code in {401, 403}:
            raise BrainError(f"Ollama cloud authentication is required. Run OLLAMA_HOST={shlex.quote(config.OLLAMA_HOST)} ollama signin and complete the browser sign-in.") from exc
        raise
    except ConnectionError as exc:
        raise BrainError("Ollama is not running. Start it with: systemctl --user start jarvis-ollama") from exc
    return response["message"]["content"]


def _call_openai(messages: list) -> str:
    from openai import OpenAI

    if not config.OPENAI_API_KEY:
        raise BrainError("OPENAI_API_KEY is not set.")

    client = OpenAI(api_key=config.OPENAI_API_KEY, timeout=config.REQUEST_TIMEOUT, max_retries=0)
    response = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=[{"role": "system", "content": _system_prompt()}] + messages,
        temperature=0.4,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content


def _call_anthropic(messages: list) -> str:
    import anthropic

    if not config.ANTHROPIC_API_KEY:
        raise BrainError("ANTHROPIC_API_KEY is not set.")

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=config.REQUEST_TIMEOUT, max_retries=0)
    response = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=1024,
        system=_system_prompt(),
        messages=messages,
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    return text


def _call_gemini(messages: list) -> str:
    """
    Invokes Gemini 3.8 Flash using OpenAI SDK structural cross-compatibility endpoints.
    """
    from openai import OpenAI

    if not config.GEMINI_API_KEY:
        raise BrainError("GEMINI_API_KEY environment variable is not set.")

    # Configure base endpoint structure to cross-route via Google API gateways
    client = OpenAI(
        api_key=config.GEMINI_API_KEY,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        timeout=config.REQUEST_TIMEOUT,
        max_retries=0,
    )
    
    response = client.chat.completions.create(
        model=config.GEMINI_MODEL,
        messages=[{"role": "system", "content": _system_prompt()}] + messages,
        response_format={"type": "json_object"}
    )
    return response.choices[0].message.content


_PROVIDERS = {
    "ollama": _call_ollama,
    "openai": _call_openai,
    "anthropic": _call_anthropic,
    "gemini": _call_gemini,  # Registered dynamic gateway choice
}


def get_response(messages: list, provider: str, retries: int = 2) -> dict:
    """
    Route `messages` to the selected provider and return a parsed dict.
    """
    if provider not in _PROVIDERS:
        raise BrainError(f"Unknown provider '{provider}'. Choose from: {list(_PROVIDERS)}")

    messages = [{**message, "content": redact(message.get("content", ""))} for message in messages]
    last_error = None
    for attempt in range(retries + 1):
        try:
            raw = _PROVIDERS[provider](messages)
            if not isinstance(raw, str) or not raw.strip():
                raise BrainError("The provider returned an empty response.")
            return _safe_parse_json(raw)
        except Exception as exc:
            last_error = exc
            if isinstance(exc, (BrainError, ImportError)) or getattr(exc, "status_code", None) in {400, 401, 403, 404}:
                break
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    detail = redact(last_error)
    for key in (config.GEMINI_API_KEY, config.OPENAI_API_KEY, config.ANTHROPIC_API_KEY):
        if key:
            detail = detail.replace(key, "[REDACTED]")
    raise BrainError(f"{provider} failed after {attempt + 1} attempts: {detail}")
