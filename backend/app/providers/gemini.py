from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.errors import ProviderError
from app.core.models import Message
from app.core.observability import runnable_config


def _to_langchain(system_prompt: str, messages: list[Message]) -> list[BaseMessage]:
    converted: list[BaseMessage] = [SystemMessage(content=system_prompt)]
    for message in messages:
        cls = HumanMessage if message.role == "user" else AIMessage
        converted.append(cls(content=message.content))
    return converted


def _extract_text(content: str | list) -> str:
    """Le contenu d'un message LangChain est soit une str, soit une liste de blocs."""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts)


class GeminiChatProvider:
    def __init__(self, api_key: str, model: str) -> None:
        self._llm = ChatGoogleGenerativeAI(model=model, google_api_key=api_key)

    async def generate(self, system_prompt: str, messages: list[Message]) -> str:
        try:
            result = await self._llm.ainvoke(
                _to_langchain(system_prompt, messages), config=runnable_config()
            )
        except Exception as exc:  # le SDK lève des types variés (réseau, quota, auth…)
            raise ProviderError("Échec de l'appel à Gemini") from exc
        text = _extract_text(result.content).strip()
        if not text:
            raise ProviderError("Gemini a renvoyé une réponse vide")
        return text
