import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from google import genai
from google.genai import types

from app.core.errors import ProviderError
from app.core.voice import (
    INPUT_SAMPLE_RATE,
    AudioEvent,
    InterruptedEvent,
    TranscriptEvent,
    TurnCompleteEvent,
    VoiceEvent,
)

logger = logging.getLogger(__name__)


class GeminiVoiceSession:
    def __init__(self, session) -> None:
        self._session = session

    async def send_audio(self, pcm: bytes) -> None:
        try:
            await self._session.send_realtime_input(
                audio=types.Blob(data=pcm, mime_type=f"audio/pcm;rate={INPUT_SAMPLE_RATE}")
            )
        except Exception as exc:
            logger.error("Gemini Live : envoi audio impossible", exc_info=exc)
            raise ProviderError("Échec d'envoi de l'audio à Gemini Live") from exc

    async def events(self) -> AsyncIterator[VoiceEvent]:
        first_audio_logged = False
        try:
            # `receive()` s'arrête à chaque fin de tour : on la relance pour toute la session.
            while True:
                async for message in self._session.receive():
                    for event in _convert(message):
                        if isinstance(event, AudioEvent):
                            if not first_audio_logged:
                                logger.info("Gemini Live : premier audio reçu")
                                first_audio_logged = True
                        else:
                            _log_event(event)
                        yield event
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Gemini Live : flux de réception interrompu", exc_info=exc)
            raise ProviderError("Connexion à Gemini Live interrompue") from exc


def _log_event(event: VoiceEvent) -> None:
    # Pas de texte dans les logs (propos de l'utilisateur) : seulement le type et la taille.
    if isinstance(event, TranscriptEvent):
        logger.info("Gemini Live : transcription %s (%d car.)", event.role, len(event.text))
    elif isinstance(event, TurnCompleteEvent):
        logger.info("Gemini Live : fin de tour")
    elif isinstance(event, InterruptedEvent):
        logger.info("Gemini Live : interruption")


def _convert(message) -> list[VoiceEvent]:
    events: list[VoiceEvent] = []
    content = message.server_content
    if content is None:
        return events
    if content.interrupted:
        events.append(InterruptedEvent())
    if content.model_turn:
        for part in content.model_turn.parts or []:
            if part.inline_data and part.inline_data.data:
                events.append(AudioEvent(part.inline_data.data))
    if content.input_transcription and content.input_transcription.text:
        events.append(TranscriptEvent("user", content.input_transcription.text))
    if content.output_transcription and content.output_transcription.text:
        events.append(TranscriptEvent("assistant", content.output_transcription.text))
    if content.turn_complete:
        events.append(TurnCompleteEvent())
    return events


class GeminiVoiceProvider:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    @asynccontextmanager
    async def connect(self, system_prompt: str):
        config = types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            system_instruction=system_prompt,
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
        )
        # Seule l'ouverture de la session est convertie en ProviderError : une exception
        # levée dans le corps du `async with` (ex. déconnexion du navigateur) doit la
        # traverser telle quelle, sinon elle est faussement signalée comme un échec de connexion.
        async with AsyncExitStack() as stack:
            try:
                session = await stack.enter_async_context(
                    self._client.aio.live.connect(model=self._model, config=config)
                )
            except Exception as exc:
                logger.error(
                    "Gemini Live : connexion refusée (modèle %s)", self._model, exc_info=exc
                )
                raise ProviderError("Échec de la connexion à Gemini Live") from exc
            logger.info("Gemini Live : session ouverte (modèle %s)", self._model)
            yield GeminiVoiceSession(session)
