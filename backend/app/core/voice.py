from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from app.core.chat import SYSTEM_PROMPT
from app.core.models import Role

if TYPE_CHECKING:
    from app.providers.base import VoiceProvider

# Formats audio imposés par l'API Gemini Live.
INPUT_SAMPLE_RATE = 16000  # PCM 16 bits mono, micro → modèle
OUTPUT_SAMPLE_RATE = 24000  # PCM 16 bits mono, modèle → haut-parleur


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

    def __init__(self, provider: "VoiceProvider") -> None:
        self._provider = provider

    def open(self):
        """Context manager asynchrone qui produit une `VoiceSession`."""
        return self._provider.connect(SYSTEM_PROMPT)
