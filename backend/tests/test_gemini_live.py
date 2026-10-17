from types import SimpleNamespace

import pytest

from app.core.errors import ProviderError
from app.core.voice import AudioEvent, InterruptedEvent, TranscriptEvent, TurnCompleteEvent
from app.providers.gemini_live import GeminiVoiceProvider, _convert


class FakeConnection:
    def __init__(self, fail: bool) -> None:
        self.fail = fail
        self.closed = False

    async def __aenter__(self):
        if self.fail:
            raise RuntimeError("modèle introuvable")
        return object()

    async def __aexit__(self, *exc_info) -> bool:
        self.closed = True
        return False


def make_provider(connection: FakeConnection) -> GeminiVoiceProvider:
    provider = GeminiVoiceProvider.__new__(GeminiVoiceProvider)
    provider._model = "fake-model"
    provider._client = SimpleNamespace(
        aio=SimpleNamespace(live=SimpleNamespace(connect=lambda **_: connection))
    )
    return provider


async def test_connect_failure_becomes_provider_error():
    provider = make_provider(FakeConnection(fail=True))
    with pytest.raises(ProviderError, match="connexion"):
        async with provider.connect("prompt"):
            pass


async def test_error_in_body_is_not_reported_as_connection_failure():
    # Une déconnexion du navigateur lève dans le corps du `async with` : elle ne doit pas
    # être transformée en « Échec de la connexion à Gemini Live ».
    connection = FakeConnection(fail=False)
    provider = make_provider(connection)
    with pytest.raises(KeyError):
        async with provider.connect("prompt"):
            raise KeyError("client parti")
    assert connection.closed


def message(**content):
    defaults = dict(
        interrupted=False,
        model_turn=None,
        input_transcription=None,
        output_transcription=None,
        turn_complete=False,
    )
    return SimpleNamespace(server_content=SimpleNamespace(**{**defaults, **content}))


def test_convert_extracts_transcripts_audio_and_turn_markers():
    part = SimpleNamespace(inline_data=SimpleNamespace(data=b"\x01\x02"))
    events = _convert(
        message(
            interrupted=True,
            model_turn=SimpleNamespace(parts=[part]),
            input_transcription=SimpleNamespace(text="Bonjour"),
            output_transcription=SimpleNamespace(text="Salut"),
            turn_complete=True,
        )
    )
    assert events == [
        InterruptedEvent(),
        AudioEvent(b"\x01\x02"),
        TranscriptEvent("user", "Bonjour"),
        TranscriptEvent("assistant", "Salut"),
        TurnCompleteEvent(),
    ]


def test_convert_ignores_messages_without_server_content():
    assert _convert(SimpleNamespace(server_content=None)) == []
