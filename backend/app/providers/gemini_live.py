import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

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


class GeminiVoiceSession:
    def __init__(self, session) -> None:
        self._session = session

    async def send_audio(self, pcm: bytes) -> None:
        try:
            await self._session.send_realtime_input(
                audio=types.Blob(data=pcm, mime_type=f"audio/pcm;rate={INPUT_SAMPLE_RATE}")
            )
        except Exception as exc:
            raise ProviderError("Échec d'envoi de l'audio à Gemini Live") from exc

    async def events(self) -> AsyncIterator[VoiceEvent]:
        try:
            # `receive()` s'arrête à chaque fin de tour : on la relance pour toute la session.
            while True:
                async for message in self._session.receive():
                    for event in _convert(message):
                        yield event
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise ProviderError("Connexion à Gemini Live interrompue") from exc


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
        try:
            async with self._client.aio.live.connect(model=self._model, config=config) as session:
                yield GeminiVoiceSession(session)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("Échec de la connexion à Gemini Live") from exc
