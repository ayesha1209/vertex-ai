"""OpenAI API client: single responsibility to call chat completion."""

from openai import OpenAI

from app.core.config import get_settings

_settings = get_settings()
if not _settings.OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is required")

_client = OpenAI(api_key=_settings.OPENAI_API_KEY)


def complete(system: str, user: str, *, temperature: float = 0.3) -> str:
    """Call OpenAI chat completion. Returns assistant message content."""
    response = _client.chat.completions.create(
        model=_settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
    )
    return (response.choices[0].message.content or "").strip()
