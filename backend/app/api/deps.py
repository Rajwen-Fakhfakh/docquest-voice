from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.core.chat import ChatService
from app.core.config import Settings, get_settings
from app.core.errors import ConfigurationError
from app.core.rag import Retriever
from app.core.voice import VoiceService
from app.providers.gemini import GeminiChatProvider
from app.providers.gemini_live import GeminiVoiceProvider


@lru_cache
def _build_retriever(
    api_key: str, embedding_model: str, index_path: Path, top_k: int
) -> Retriever | None:
    """Charge l'index RAG une fois ; `None` s'il n'a pas encore été généré (scripts/ingest.py)."""
    if not index_path.exists():
        return None
    embeddings = GoogleGenerativeAIEmbeddings(model=embedding_model, google_api_key=api_key)
    return Retriever.from_file(index_path, embeddings, top_k)


@lru_cache
def _build_chat_service(
    api_key: str, model: str, embedding_model: str, index_path: Path, top_k: int
) -> ChatService:
    retriever = _build_retriever(api_key, embedding_model, index_path, top_k)
    return ChatService(GeminiChatProvider(api_key=api_key, model=model), retriever)


def get_chat_service(settings: Annotated[Settings, Depends(get_settings)]) -> ChatService:
    if not settings.gemini_api_key:
        raise ConfigurationError("GEMINI_API_KEY n'est pas configurée")
    return _build_chat_service(
        settings.gemini_api_key,
        settings.gemini_chat_model,
        settings.gemini_embedding_model,
        settings.rag_index_path,
        settings.rag_top_k,
    )


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
