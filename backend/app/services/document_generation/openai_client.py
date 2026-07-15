"""OpenAI API client: single responsibility to call chat completion."""

from openai import BadRequestError, OpenAI

from app.core.config import get_settings

_settings = get_settings()
if not _settings.OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is required")

_client = OpenAI(api_key=_settings.OPENAI_API_KEY)


def complete(system: str, user: str, *, temperature: float = 0.3) -> str:
    """Call OpenAI chat completion. Returns assistant message content.

    Some models (e.g. gpt-5 family) only support the default temperature (1)
    and reject any other value; retry without it if the API rejects ours.
    """
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    try:
        response = _client.chat.completions.create(
            model=_settings.OPENAI_MODEL,
            messages=messages,
            temperature=temperature,
        )
    except BadRequestError as e:
        if "temperature" not in str(e).lower():
            raise
        response = _client.chat.completions.create(
            model=_settings.OPENAI_MODEL,
            messages=messages,
        )
    return (response.choices[0].message.content or "").strip()
