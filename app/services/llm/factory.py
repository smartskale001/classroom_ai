from typing import Literal

from app.core.config import Settings, get_settings
from app.services.llm.ollama_provider import OllamaProvider
from app.services.llm.openai_provider import OpenAIProvider
from app.services.llm.protocol import LLMProvider


def get_llm_provider(
    *,
    vision: bool = False,
    settings: Settings | None = None,
    provider: Literal["openai", "ollama"] | None = None,
) -> LLMProvider:
    """Build the requested LLM provider using app settings and the desired mode."""
    s = settings or get_settings()
    selected = provider or s.llm_provider
    if selected == "openai":
        if not s.openai_api_key or not s.openai_api_key.strip():
            raise ValueError(
                "OPENAI_API_KEY is missing. Add it to .env file or switch to 'opensource' stack."
            )
        return OpenAIProvider(s)
    return OllamaProvider(s, vision=vision)
