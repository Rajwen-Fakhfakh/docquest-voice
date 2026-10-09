from app.core.models import Message
from app.providers.base import ChatProvider

SYSTEM_PROMPT = (
    "Tu es DocQuest, un assistant qui aide à comprendre le Document d'Enregistrement "
    "Universel (DEU) de TotalEnergies. Réponds en français, de façon claire et concise."
)


class ChatService:
    """Logique métier du chat, indépendante de FastAPI et du fournisseur concret."""

    def __init__(self, provider: ChatProvider) -> None:
        self._provider = provider

    async def reply(self, messages: list[Message]) -> str:
        return await self._provider.generate(SYSTEM_PROMPT, messages)
