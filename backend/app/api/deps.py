from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from qdrant_client import QdrantClient
from starlette.requests import HTTPConnection

from app.core.chat import ChatService
from app.core.config import Settings, get_settings
from app.core.errors import ConfigurationError
from app.core.rag import Retriever
from app.core.ratelimit import RequestGuard, client_ip
from app.core.voice import VoiceService
from app.providers.gemini import GeminiChatProvider
from app.providers.gemini_live import GeminiVoiceProvider


@lru_cache
def _build_retriever(
    api_key: str,
    embedding_model: str,
    index_path: Path,
    top_k: int,
    qdrant_url: str | None,
    qdrant_api_key: str | None,
    qdrant_collection: str,
) -> Retriever | None:
    """Prépare la recherche RAG : Qdrant si configuré, sinon l'index local, sinon `None`."""
    embeddings = GoogleGenerativeAIEmbeddings(model=embedding_model, google_api_key=api_key)
    if qdrant_url:
        client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
        return Retriever.from_qdrant(client, qdrant_collection, embeddings, top_k)
    if not index_path.exists():  # pas encore généré (scripts/ingest.py)
        return None
    return Retriever.from_file(index_path, embeddings, top_k)


@lru_cache
def _build_chat_service(
    api_key: str,
    model: str,
    embedding_model: str,
    index_path: Path,
    top_k: int,
    qdrant_url: str | None,
    qdrant_api_key: str | None,
    qdrant_collection: str,
) -> ChatService:
    retriever = _build_retriever(
        api_key,
        embedding_model,
        index_path,
        top_k,
        qdrant_url,
        qdrant_api_key,
        qdrant_collection,
    )
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
        settings.qdrant_url,
        settings.qdrant_api_key,
        settings.qdrant_collection,
    )


@lru_cache
def _build_voice_service(
    api_key: str,
    model: str,
    embedding_model: str,
    index_path: Path,
    top_k: int,
    qdrant_url: str | None,
    qdrant_api_key: str | None,
    qdrant_collection: str,
) -> VoiceService:
    # Même retriever (donc même index et mêmes embeddings) que le chat.
    retriever = _build_retriever(
        api_key,
        embedding_model,
        index_path,
        top_k,
        qdrant_url,
        qdrant_api_key,
        qdrant_collection,
    )
    return VoiceService(GeminiVoiceProvider(api_key=api_key, model=model), retriever)


def get_voice_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> VoiceService | None:
    """`None` quand la clé manque : la route WebSocket signale l'erreur au client."""
    if not settings.gemini_api_key:
        return None
    return _build_voice_service(
        settings.gemini_api_key,
        settings.gemini_live_model,
        settings.gemini_embedding_model,
        settings.rag_index_path,
        settings.rag_top_k,
        settings.qdrant_url,
        settings.qdrant_api_key,
        settings.qdrant_collection,
    )


def get_guard(conn: HTTPConnection) -> RequestGuard:
    # HTTPConnection (et non Request) : la même dépendance sert aux routes HTTP et au WebSocket.
    return conn.app.state.guard


def enforce_rate_limit(
    request: Request, guard: Annotated[RequestGuard, Depends(get_guard)]
) -> None:
    """Dépendance des routes HTTP : 429 si l'IP (ou la démo entière) a trop consommé."""
    guard.check(client_ip(request))
