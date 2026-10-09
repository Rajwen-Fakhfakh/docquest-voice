from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.core.chat import ChatService
from app.core.config import Settings, get_settings
from app.core.errors import ConfigurationError
from app.core.voice import VoiceService
from app.providers.gemini import GeminiChatProvider
from app.providers.gemini_live import GeminiVoiceProvider


@lru_cache
def _build_chat_service(api_key: str, model: str) -> ChatService:
    return ChatService(GeminiChatProvider(api_key=api_key, model=model))


def get_chat_service(settings: Annotated[Settings, Depends(get_settings)]) -> ChatService:
    if not settings.gemini_api_key:
        raise ConfigurationError("GEMINI_API_KEY n'est pas configurée")
    return _build_chat_service(settings.gemini_api_key, settings.gemini_chat_model)


@lru_cache
def _build_voice_service(api_key: str, model: str) -> VoiceService:
    return VoiceService(GeminiVoiceProvider(api_key=api_key, model=model))


def get_voice_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> VoiceService | None:
    """`None` quand la clé manque : la route WebSocket signale l'erreur au client."""
    if not settings.gemini_api_key:
        return None
    return _build_voice_service(settings.gemini_api_key, settings.gemini_live_model)
