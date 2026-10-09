from contextlib import asynccontextmanager

from fastapi.testclient import TestClient

from app.api.deps import get_voice_service
from app.core.errors import ProviderError
from app.core.voice import (
    AudioEvent,
    InterruptedEvent,
    TranscriptEvent,
    TurnCompleteEvent,
    VoiceService,
)
from app.main import create_app


class FakeSession:
    def __init__(self, events) -> None:
        self.received: list[bytes] = []
        self._events = events

    async def send_audio(self, pcm: bytes) -> None:
        self.received.append(pcm)

    async def events(self):
        for event in self._events:
            yield event
        # La session reste ouverte tant que le client ne se déconnecte pas.
        import asyncio

        await asyncio.Event().wait()


class FakeVoiceProvider:
    def __init__(self, events=(), error: Exception | None = None) -> None:
        self.session = FakeSession(events)
        self.error = error
        self.system_prompts: list[str] = []

    @asynccontextmanager
    async def connect(self, system_prompt: str):
        self.system_prompts.append(system_prompt)
        if self.error:
            raise self.error
        yield self.session


def make_client(service: VoiceService | None) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_voice_service] = lambda: service
    return TestClient(app)


def test_voice_relays_events_to_client():
    provider = FakeVoiceProvider(
        [
            TranscriptEvent("user", "Bonjour"),
            AudioEvent(b"\x01\x02"),
            TranscriptEvent("assistant", "Salut"),
            InterruptedEvent(),
            TurnCompleteEvent(),
        ]
    )
    client = make_client(VoiceService(provider))
    with client.websocket_connect("/ws/voice") as ws:
        assert ws.receive_json() == {"type": "transcript", "role": "user", "text": "Bonjour"}
        assert ws.receive_bytes() == b"\x01\x02"
        assert ws.receive_json() == {"type": "transcript", "role": "assistant", "text": "Salut"}
        assert ws.receive_json() == {"type": "interrupted"}
        assert ws.receive_json() == {"type": "turn_complete"}
    assert "DocQuest" in provider.system_prompts[0]


def test_voice_forwards_microphone_audio_to_provider():
    provider = FakeVoiceProvider([TurnCompleteEvent()])
    client = make_client(VoiceService(provider))
    with client.websocket_connect("/ws/voice") as ws:
        ws.send_bytes(b"\x00\x01")
        ws.send_bytes(b"\x02\x03")
        assert ws.receive_json() == {"type": "turn_complete"}
    assert provider.session.received == [b"\x00\x01", b"\x02\x03"]


def test_voice_reports_provider_error():
    client = make_client(VoiceService(FakeVoiceProvider(error=ProviderError("boom"))))
    with client.websocket_connect("/ws/voice") as ws:
        assert ws.receive_json() == {"type": "error", "message": "boom"}


def test_voice_reports_missing_api_key():
    client = make_client(None)
    with client.websocket_connect("/ws/voice") as ws:
        message = ws.receive_json()
    assert message["type"] == "error"
    assert "GEMINI_API_KEY" in message["message"]
