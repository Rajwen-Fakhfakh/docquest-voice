from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.core.chat import ChatService
from app.core.config import Settings, get_settings
from app.core.errors import ConfigurationError
from app.providers.gemini import GeminiChatProvider


@lru_cache
def _build_chat_service(api_key: str, model: str) -> ChatService:
    return ChatService(GeminiChatProvider(api_key=api_key, model=model))


def get_chat_service(settings: Annotated[Settings, Depends(get_settings)]) -> ChatService:
    if not settings.gemini_api_key:
        raise ConfigurationError("GEMINI_API_KEY n'est pas configurée")
    return _build_chat_service(settings.gemini_api_key, settings.gemini_chat_model)
