from typing import Protocol

from app.core.models import Message


class ChatProvider(Protocol):
    """Contrat d'un fournisseur de LLM texte. Lève `ProviderError` en cas d'échec."""

    async def generate(self, system_prompt: str, messages: list[Message]) -> str: ...
