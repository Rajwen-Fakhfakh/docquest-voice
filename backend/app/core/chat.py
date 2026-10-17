from collections.abc import AsyncIterator

from app.core.models import Message
from app.core.rag import Retriever, format_context
from app.providers.base import ChatProvider

SYSTEM_PROMPT = (
    "Tu es DocQuest, l'assistant du Document d'Enregistrement Universel (DEU) 2025 de "
    "TotalEnergies. Réponds en français, de façon directe et professionnelle : la réponse "
    "d'abord, puis le détail utile, en phrases courtes. Pas de salutation ni de présentation "
    "de toi-même, sauf si l'utilisateur te salue ou te demande qui tu es. Reste factuel, sans "
    "spéculer. Si la question sort du périmètre du DEU, dis-le en une phrase."
)


# En dessous, la question est jugée trop courte pour être comprise seule (« Et en 2024 ? »).
SHORT_QUESTION_CHARS = 60


def _search_query(messages: list[Message]) -> str:
    """Texte à chercher dans le DEU : la dernière question, complétée par la précédente si brève."""
    last = messages[-1].content
    if len(last) >= SHORT_QUESTION_CHARS:
        return last
    previous = [m.content for m in messages[:-1] if m.role == "user"]
    return f"{previous[-1]} {last}" if previous else last


class ChatService:
    """Logique métier du chat, indépendante de FastAPI et du fournisseur concret."""

    def __init__(self, provider: ChatProvider, retriever: Retriever | None = None) -> None:
        self._provider = provider
        # Sans retriever (index non généré), le chat fonctionne comme en V1 (sans RAG).
        self._retriever = retriever

    async def _build_system_prompt(self, messages: list[Message]) -> str:
        """Ajoute au prompt les extraits du DEU liés à la dernière question (étape RAG)."""
        if self._retriever is None:
            return SYSTEM_PROMPT
        docs = await self._retriever.search(_search_query(messages))
        if not docs:
            return SYSTEM_PROMPT
        return (
            f"{SYSTEM_PROMPT}\n\n"
            "Réponds uniquement à partir des extraits du DEU ci-dessous. Donne les chiffres exacts "
            "avec leur unité et leur année. Si plusieurs chiffres peuvent répondre (ex. résultat "
            "net comptable ou ajusté), donne le principal puis précise l'écart en une phrase. "
            "Cite les pages à la fin, en ordre croissant, entre parenthèses (ex. : (p. 12, 40)). "
            "Pour une comparaison entre deux années, donne les deux valeurs puis l'écart. "
            "Si la réponse ne figure pas dans les extraits, dis-le en une phrase, sans rien "
            "inventer ni citer de page.\n\n"
            f"EXTRAITS :\n{format_context(docs)}"
        )

    async def reply(self, messages: list[Message]) -> str:
        return await self._provider.generate(await self._build_system_prompt(messages), messages)

    async def stream_reply(self, messages: list[Message]) -> AsyncIterator[str]:
        system_prompt = await self._build_system_prompt(messages)
        async for chunk in self._provider.stream(system_prompt, messages):
            yield chunk
