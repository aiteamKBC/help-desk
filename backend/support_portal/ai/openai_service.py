from __future__ import annotations

from functools import lru_cache
from typing import Any

from django.conf import settings

CHAT_MODEL = "gpt-5.4-mini"
EMBEDDING_MODEL = "text-embedding-3-small"


@lru_cache(maxsize=1)
def get_openai_client():
    from openai import OpenAI

    return OpenAI(api_key=getattr(settings, "OPENAI_API_KEY", "") or None, timeout=20.0, max_retries=1)


def create_embedding(text: str) -> list[float]:
    response = get_openai_client().embeddings.create(model=EMBEDDING_MODEL, input=text[:8000])
    return list(response.data[0].embedding)


def generate_reply(*, instructions: str, input_messages: list[dict[str, Any]]) -> str:
    response = get_openai_client().responses.create(
        model=CHAT_MODEL,
        instructions=instructions,
        input=input_messages,
        reasoning={"effort": "low"},
        max_output_tokens=700,
    )
    return str(getattr(response, "output_text", "") or "").strip()
