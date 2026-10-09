import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_chat_service
from app.core.chat import ChatService
from app.core.config import Settings, get_settings
from app.core.errors import ProviderError
from app.core.models import Message
from app.main import create_app


class FakeProvider:
    def __init__(self, answer: str = "Bonjour !", error: Exception | None = None) -> None:
        self.answer = answer
        self.error = error
        self.calls: list[tuple[str, list[Message]]] = []

    async def generate(self, system_prompt: str, messages: list[Message]) -> str:
        self.calls.append((system_prompt, messages))
        if self.error:
            raise self.error
        return self.answer


def make_client(provider: FakeProvider) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_chat_service] = lambda: ChatService(provider)
    return TestClient(app)


def test_health():
    assert TestClient(create_app()).get("/health").json() == {"status": "ok"}


def test_chat_returns_answer_and_forwards_history():
    provider = FakeProvider("Réponse")
    client = make_client(provider)
    body = {
        "messages": [
            {"role": "user", "content": "Salut"},
            {"role": "assistant", "content": "Bonjour"},
            {"role": "user", "content": "Qui es-tu ?"},
        ]
    }
    response = client.post("/chat", json=body)
    assert response.status_code == 200
    assert response.json() == {"answer": "Réponse"}
    assert provider.calls[0][1] == [
        Message("user", "Salut"),
        Message("assistant", "Bonjour"),
        Message("user", "Qui es-tu ?"),
    ]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"messages": []},
        {"messages": [{"role": "user", "content": ""}]},
        {"messages": [{"role": "system", "content": "x"}]},
        {"messages": [{"role": "assistant", "content": "x"}]},
    ],
)
def test_chat_rejects_invalid_payload(body):
    assert make_client(FakeProvider()).post("/chat", json=body).status_code == 422


def test_chat_provider_failure_is_502():
    client = make_client(FakeProvider(error=ProviderError("boom")))
    response = client.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert response.status_code == 502


def test_chat_without_api_key_is_503():
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(gemini_api_key=None, _env_file=None)
    response = TestClient(app).post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert response.status_code == 503


def test_blank_api_key_is_treated_as_missing():
    assert Settings(gemini_api_key="  ", _env_file=None).gemini_api_key is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://localhost:5173", ["http://localhost:5173"]),
        ("http://a.test,http://b.test", ["http://a.test", "http://b.test"]),
        ('["http://a.test"]', ["http://a.test"]),
    ],
)
def test_cors_origins_parsed_from_dotenv_file(tmp_path, raw, expected):
    env_file = tmp_path / ".env"
    env_file.write_text(f"CORS_ORIGINS={raw}\nGEMINI_API_KEY=\n", encoding="utf-8")
    settings = Settings(_env_file=env_file)
    assert settings.cors_origins == expected
    assert settings.gemini_api_key is None


def test_cors_origins_accepts_comma_separated():
    settings = Settings(cors_origins="http://a.test, http://b.test", _env_file=None)
    assert settings.cors_origins == ["http://a.test", "http://b.test"]
