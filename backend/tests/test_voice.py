from contextlib import asynccontextmanager
from types import SimpleNamespace

from fastapi.testclient import TestClient
from google.genai import types
from langchain_core.documents import Document

from app.api.deps import get_voice_service
from app.core.errors import ProviderError
from app.core.voice import (
    NO_RESULT,
    RAG_INSTRUCTIONS,
    SEARCH_TOOL_NAME,
    AudioEvent,
    InterruptedEvent,
    SearchTool,
    TranscriptEvent,
    TurnCompleteEvent,
    VoiceService,
)
from app.main import create_app
from app.providers.gemini_live import GeminiVoiceSession


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
        self.searches: list[SearchTool | None] = []

    @asynccontextmanager
    async def connect(self, system_prompt: str, search: SearchTool | None = None):
        self.system_prompts.append(system_prompt)
        self.searches.append(search)
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


class FakeRetriever:
    def __init__(self, docs: list[Document]) -> None:
        self.docs = docs
        self.questions: list[str] = []

    async def search(self, question: str) -> list[Document]:
        self.questions.append(question)
        return self.docs


async def test_voice_without_retriever_has_no_search_tool():
    provider = FakeVoiceProvider()
    async with VoiceService(provider).open():
        pass
    assert provider.searches == [None]
    assert RAG_INSTRUCTIONS not in provider.system_prompts[0]


async def test_voice_with_retriever_exposes_search_over_deu():
    retriever = FakeRetriever([Document(page_content="CA : 218 Md$", metadata={"page": 12})])
    provider = FakeVoiceProvider()
    async with VoiceService(provider, retriever).open():
        pass

    assert RAG_INSTRUCTIONS in provider.system_prompts[0]
    search = provider.searches[0]
    assert search is not None
    assert await search("chiffre d'affaires 2024") == "[page 12]\nCA : 218 Md$"
    assert retriever.questions == ["chiffre d'affaires 2024"]


async def test_voice_search_reports_when_nothing_found():
    provider = FakeVoiceProvider()
    async with VoiceService(provider, FakeRetriever([])).open():
        pass
    assert await provider.searches[0]("question hors sujet") == NO_RESULT


class FakeLiveSession:
    def __init__(self) -> None:
        self.responses: list[types.FunctionResponse] = []

    async def send_tool_response(self, function_responses) -> None:
        self.responses.extend(function_responses)


def make_tool_call(name: str = SEARCH_TOOL_NAME, args: dict | None = None):
    call = SimpleNamespace(id="call-1", name=name, args=args or {"question": "dividende"})
    return SimpleNamespace(function_calls=[call])


async def test_gemini_session_answers_tool_call_with_search_result():
    live = FakeLiveSession()

    async def search(question: str) -> str:
        return f"extraits sur {question}"

    await GeminiVoiceSession(live, search)._answer_tool_call(make_tool_call())
    assert live.responses == [
        types.FunctionResponse(
            id="call-1", name=SEARCH_TOOL_NAME, response={"output": "extraits sur dividende"}
        )
    ]


async def test_gemini_session_survives_search_failure():
    live = FakeLiveSession()

    async def search(question: str) -> str:
        raise RuntimeError("Qdrant injoignable")

    await GeminiVoiceSession(live, search)._answer_tool_call(make_tool_call())
    assert "indisponible" in live.responses[0].response["output"]


async def test_gemini_session_rejects_unknown_tool():
    live = FakeLiveSession()
    await GeminiVoiceSession(live, None)._answer_tool_call(make_tool_call(name="autre"))
    assert "inconnu" in live.responses[0].response["output"]
