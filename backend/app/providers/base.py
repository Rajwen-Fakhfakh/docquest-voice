from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Protocol

from app.core.models import Message

if TYPE_CHECKING:
    from app.core.voice import SearchTool, VoiceSession


class ChatProvider(Protocol):
    """Contrat d'un fournisseur de LLM texte. Lève `ProviderError` en cas d'échec."""

    async def generate(self, system_prompt: str, messages: list[Message]) -> str: ...

    def stream(self, system_prompt: str, messages: list[Message]) -> AsyncIterator[str]:
        """Produit la réponse par morceaux de texte non vides."""
        ...


class VoiceProvider(Protocol):
    """Contrat d'un fournisseur de conversation vocale temps réel."""

    def connect(
        self, system_prompt: str, search: "SearchTool | None" = None
    ) -> AbstractAsyncContextManager["VoiceSession"]:
        """Ouvre une session. Lève `ProviderError` si la connexion échoue.

        Si `search` est fourni, le modèle peut l'appeler (outil `search_deu`) pour interroger
        le DEU.
        """
        ...
