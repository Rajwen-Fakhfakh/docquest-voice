from dataclasses import dataclass
from typing import Literal

Role = Literal["user", "assistant"]


@dataclass(frozen=True, slots=True)
class Message:
    """Un tour de conversation, indépendant de l'API HTTP et du fournisseur LLM."""

    role: Role
    content: str
