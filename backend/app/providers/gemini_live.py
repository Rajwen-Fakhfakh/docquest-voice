import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from google import genai
from google.genai import types

from app.core.errors import ProviderError
from app.core.voice import (
    INPUT_SAMPLE_RATE,
    SEARCH_TOOL_NAME,
    AudioEvent,
    InterruptedEvent,
    SearchTool,
    TranscriptEvent,
    TurnCompleteEvent,
    VoiceEvent,
)

logger = logging.getLogger(__name__)


SEARCH_DECLARATION = types.FunctionDeclaration(
    name=SEARCH_TOOL_NAME,
    description=(
        "Cherche dans le Document d'Enregistrement Universel (DEU) 2025 de TotalEnergies les "
        "extraits utiles pour répondre à la question."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "question": types.Schema(
                type=types.Type.STRING,
                description="La question de l'utilisateur, reformulée de façon autonome.",
            )
        },
        required=["question"],
    ),
)


class GeminiVoiceSession:
    def __init__(self, session, search: SearchTool | None = None) -> None:
        self._session = session
        self._search = search

    async def _answer_tool_call(self, tool_call) -> None:
        """Exécute les appels à `search_deu` demandés par le modèle et lui renvoie les extraits."""
        responses = []
        for call in tool_call.function_calls or []:
            if call.name != SEARCH_TOOL_NAME or self._search is None:
                output = f"Outil inconnu : {call.name}"
            else:
                try:
                    output = await self._search((call.args or {}).get("question", ""))
                except Exception:
                    # Une panne du RAG ne doit pas couper la conversation : le modèle l'annonce.
                    logger.exception("Recherche DEU impossible")
                    output = "La recherche dans le DEU est indisponible."
            responses.append(
                types.FunctionResponse(id=call.id, name=call.name, response={"output": output})
            )
        await self._session.send_tool_response(function_responses=responses)

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
                    if message.tool_call:
                        await self._answer_tool_call(message.tool_call)
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
    async def connect(self, system_prompt: str, search: SearchTool | None = None):
        config = types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            system_instruction=system_prompt,
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            tools=[types.Tool(function_declarations=[SEARCH_DECLARATION])] if search else None,
        )
        try:
            async with self._client.aio.live.connect(model=self._model, config=config) as session:
                yield GeminiVoiceSession(session, search)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("Échec de la connexion à Gemini Live") from exc
