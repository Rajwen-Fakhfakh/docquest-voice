from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from app.core.chat import SYSTEM_PROMPT
from app.core.models import Role
from app.core.rag import Retriever, format_context

if TYPE_CHECKING:
    from app.providers.base import VoiceProvider

# Formats audio imposés par l'API Gemini Live.
INPUT_SAMPLE_RATE = 16000  # PCM 16 bits mono, micro → modèle
OUTPUT_SAMPLE_RATE = 24000  # PCM 16 bits mono, modèle → haut-parleur

# Outil exposé au modèle vocal : la question n'est connue qu'une fois la parole transcrite par
# Gemini Live, donc c'est lui qui déclenche la recherche (contrairement au chat, où le backend
# cherche avant d'appeler le LLM).
SEARCH_TOOL_NAME = "search_deu"
NO_RESULT = "Aucun extrait du DEU ne correspond à cette question."

# Recherche RAG appelée par le fournisseur : question en texte → extraits mis en forme.
SearchTool = Callable[[str], Awaitable[str]]

RAG_INSTRUCTIONS = (
    f"Pour toute question sur TotalEnergies ou son DEU, appelle d'abord l'outil {SEARCH_TOOL_NAME} "
    "avec la question reformulée de façon autonome, puis réponds uniquement à partir des extraits "
    "reçus. Donne les chiffres exacts avec leur unité et leur année. Si plusieurs chiffres "
    "peuvent répondre (ex. résultat net comptable ou ajusté), donne le principal puis précise "
    "l'écart en une phrase. Pour une comparaison entre deux années, donne les deux valeurs puis "
    "l'écart. Annonce les pages à la fin, à l'oral (ex. : « page 12 et page 40 »). Si la réponse "
    "ne figure pas dans les extraits, dis-le en une phrase, sans rien inventer ni citer de page."
)


@dataclass(frozen=True, slots=True)
class AudioEvent:
    data: bytes


@dataclass(frozen=True, slots=True)
class TranscriptEvent:
    role: Role
    text: str


@dataclass(frozen=True, slots=True)
class TurnCompleteEvent:
    pass


@dataclass(frozen=True, slots=True)
class InterruptedEvent:
    """L'utilisateur a pris la parole : le front doit vider sa file de lecture."""


VoiceEvent = AudioEvent | TranscriptEvent | TurnCompleteEvent | InterruptedEvent


class VoiceSession(Protocol):
    """Session vocale bidirectionnelle ouverte auprès du fournisseur."""

    async def send_audio(self, pcm: bytes) -> None: ...

    def events(self) -> AsyncIterator[VoiceEvent]: ...


class VoiceService:
    """Logique métier du mode vocal, indépendante de FastAPI et du fournisseur concret."""

    def __init__(self, provider: "VoiceProvider", retriever: Retriever | None = None) -> None:
        self._provider = provider
        # Sans retriever (index non généré), le mode vocal répond sans RAG, comme le chat.
        self._retriever = retriever

    async def _search(self, question: str) -> str:
        """Extraits du DEU liés à la question, mis en forme pour l'outil `search_deu`."""
        assert self._retriever is not None
        docs = await self._retriever.search(question)
        return format_context(docs) if docs else NO_RESULT

    def open(self):
        """Context manager asynchrone qui produit une `VoiceSession`."""
        if self._retriever is None:
            return self._provider.connect(SYSTEM_PROMPT)
        return self._provider.connect(f"{SYSTEM_PROMPT}\n\n{RAG_INSTRUCTIONS}", self._search)
