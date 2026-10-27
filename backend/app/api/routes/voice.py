"""WebSocket /ws/voice.

Client → serveur : trames binaires PCM 16 bits mono 16 kHz (micro).
Serveur → client :
  - trames binaires PCM 16 bits mono 24 kHz (voix du modèle) ;
  - trames texte JSON : {"type": "transcript", "role", "text"}, {"type": "turn_complete"},
    {"type": "interrupted"}, {"type": "error", "message"}.
"""

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.api.deps import get_guard, get_voice_service
from app.core.errors import ProviderError, RateLimitError
from app.core.ratelimit import RequestGuard, client_ip
from app.core.voice import (
    AudioEvent,
    InterruptedEvent,
    TranscriptEvent,
    TurnCompleteEvent,
    VoiceService,
    VoiceSession,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["voice"])

WS_INTERNAL_ERROR = 1011
WS_POLICY_VIOLATION = 1008


async def _pump_microphone(websocket: WebSocket, session: VoiceSession) -> None:
    while True:
        await session.send_audio(await websocket.receive_bytes())


async def _pump_events(websocket: WebSocket, session: VoiceSession) -> None:
    async for event in session.events():
        match event:
            case AudioEvent(data):
                await websocket.send_bytes(data)
            case TranscriptEvent(role, text):
                await websocket.send_json({"type": "transcript", "role": role, "text": text})
            case TurnCompleteEvent():
                await websocket.send_json({"type": "turn_complete"})
            case InterruptedEvent():
                await websocket.send_json({"type": "interrupted"})


async def _fail(websocket: WebSocket, message: str, code: int = WS_INTERNAL_ERROR) -> None:
    try:
        await websocket.send_json({"type": "error", "message": message})
        await websocket.close(code=code)
    except Exception:  # le navigateur est déjà parti : rien à signaler
        logger.debug("WebSocket déjà fermé, erreur non transmise : %s", message)


@router.websocket("/ws/voice")
async def voice(
    websocket: WebSocket,
    # `None` si GEMINI_API_KEY est absente : un handler HTTP ne couvre pas les WebSocket.
    service: Annotated[VoiceService | None, Depends(get_voice_service)],
    guard: Annotated[RequestGuard, Depends(get_guard)],
) -> None:
    await websocket.accept()
    try:
        guard.check(client_ip(websocket))
    except RateLimitError as exc:  # pas de handler HTTP pour un WebSocket : on prévient le client
        await _fail(websocket, str(exc), WS_POLICY_VIOLATION)
        return
    if service is None:
        await _fail(websocket, "GEMINI_API_KEY n'est pas configurée")
        return
    try:
        async with service.open() as session:
            tasks = [
                asyncio.create_task(_pump_microphone(websocket, session)),
                asyncio.create_task(_pump_events(websocket, session)),
            ]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            for task in done:
                task.result()  # relève l'exception de la tâche terminée
    except WebSocketDisconnect:
        return
    except ProviderError as exc:
        logger.error("Voice error: %s", exc, exc_info=exc)
        await _fail(websocket, str(exc))
