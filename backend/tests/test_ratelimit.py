import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_voice_service
from app.core.errors import RateLimitError
from app.core.ratelimit import RateLimiter, RequestGuard
from tests.test_chat import FakeProvider, make_client

BODY = {"messages": [{"role": "user", "content": "Bonjour"}]}


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_limiter_blocks_after_limit_then_recovers_when_window_passes():
    clock = Clock()
    limiter = RateLimiter(2, 60, clock)
    assert limiter.hit("a") is None
    assert limiter.hit("a") is None
    assert limiter.hit("a") == 60  # 3e appel : il faut attendre la fin de la fenêtre
    assert limiter.hit("b") is None  # une autre clé n'est pas touchée
    clock.now = 61
    assert limiter.hit("a") is None


def test_limiter_with_zero_limit_is_disabled():
    limiter = RateLimiter(0, 60)
    assert all(limiter.hit("a") is None for _ in range(100))


def test_guard_daily_cap_applies_across_ips():
    guard = RequestGuard(per_minute=10, daily_cap=2, clock=Clock())
    guard.check("1.1.1.1")
    guard.check("2.2.2.2")
    with pytest.raises(RateLimitError, match="quota du jour"):
        guard.check("3.3.3.3")


def test_chat_returns_429_with_retry_after_when_ip_exceeds_limit():
    client = make_client(FakeProvider("ok"))
    client.app.state.guard = RequestGuard(per_minute=2, daily_cap=0)
    assert client.post("/chat", json=BODY).status_code == 200
    assert client.post("/chat/stream", json=BODY).status_code == 200
    blocked = client.post("/chat", json=BODY)
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert "Trop de requêtes" in blocked.json()["detail"]


def test_limit_is_per_ip_using_forwarded_header():
    client = make_client(FakeProvider("ok"))
    client.app.state.guard = RequestGuard(per_minute=1, daily_cap=0)

    def post(ip: str) -> int:
        return client.post("/chat", json=BODY, headers={"X-Forwarded-For": ip}).status_code

    assert post("1.1.1.1") == 200
    assert post("1.1.1.1") == 429
    assert post("2.2.2.2, 10.0.0.1") == 200  # seule la première adresse (le visiteur) compte


def test_health_is_not_limited():
    client = TestClient(make_client(FakeProvider()).app)
    client.app.state.guard = RequestGuard(per_minute=1, daily_cap=1)
    assert all(client.get("/health").status_code == 200 for _ in range(5))


def test_voice_tells_client_when_rate_limited():
    client = make_client(FakeProvider())
    client.app.dependency_overrides[get_voice_service] = lambda: None
    client.app.state.guard = RequestGuard(per_minute=1, daily_cap=0)
    with client.websocket_connect("/ws/voice") as ws:  # 1re connexion : acceptée (puis erreur clé)
        assert "GEMINI_API_KEY" in ws.receive_json()["message"]
    with client.websocket_connect("/ws/voice") as ws:
        message = ws.receive_json()
        assert message["type"] == "error"
        assert "Trop de requêtes" in message["message"]
