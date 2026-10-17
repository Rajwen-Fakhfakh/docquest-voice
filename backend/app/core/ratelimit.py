"""Limites de débit en mémoire, pour protéger le quota Gemini d'une démo publique.

Deux garde-fous : une limite par minute et par IP (un visiteur trop insistant), et un plafond
global par jour (filet de sécurité si plusieurs IP s'y mettent). L'état vit dans le processus :
il repart de zéro au redémarrage, ce qui suffit pour une seule instance.
"""

import time
from collections import deque
from collections.abc import Callable

from fastapi import Request, WebSocket

from app.core.errors import RateLimitError

MINUTE = 60.0
DAY = 24 * 3600.0


class RateLimiter:
    """Fenêtre glissante : au plus `limit` appels par `window` s et par clé (0 = illimité)."""

    def __init__(self, limit: int, window: float, clock: Callable[[], float] = time.monotonic):
        self._limit = limit
        self._window = window
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def hit(self, key: str) -> float | None:
        """Enregistre un appel. Renvoie `None` s'il est accepté, sinon les secondes à attendre."""
        if self._limit <= 0:
            return None
        now = self._clock()
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= self._window:
            hits.popleft()
        if len(hits) >= self._limit:
            return hits[0] + self._window - now
        hits.append(now)
        if len(self._hits) > 10_000:  # évite que le dict grossisse indéfiniment
            self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] < self._window}
        return None


class RequestGuard:
    """Limite par IP puis plafond journalier global ; lève `RateLimitError` si dépassé."""

    def __init__(
        self, per_minute: int, daily_cap: int, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._per_ip = RateLimiter(per_minute, MINUTE, clock)
        self._daily = RateLimiter(daily_cap, DAY, clock)

    def check(self, ip: str) -> None:
        wait = self._per_ip.hit(ip)
        if wait is not None:
            raise RateLimitError("Trop de requêtes, réessayez dans un instant.", wait)
        wait = self._daily.hit("global")
        if wait is not None:
            raise RateLimitError("La démo a atteint son quota du jour, revenez demain.", wait)


def client_ip(conn: Request | WebSocket) -> str:
    """IP du visiteur. Derrière un proxy (Render, Vercel), la première valeur de X-Forwarded-For."""
    forwarded = conn.headers.get("x-forwarded-for", "")
    first = forwarded.split(",")[0].strip()
    if first:
        return first
    return conn.client.host if conn.client else "unknown"
