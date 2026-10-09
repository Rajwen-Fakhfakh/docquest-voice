from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import get_chat_service
from app.api.schemas import ChatRequest, ChatResponse
from app.core.chat import ChatService
from app.core.errors import ProviderError
from app.core.models import Message

router = APIRouter(tags=["chat"])


def _to_messages(request: ChatRequest) -> list[Message]:
    return [Message(role=m.role, content=m.content) for m in request.messages]


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> ChatResponse:
    return ChatResponse(answer=await service.reply(_to_messages(request)))


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> StreamingResponse:
    chunks = service.stream_reply(_to_messages(request)).__aiter__()
    # On attend le premier morceau avant de répondre : une panne du fournisseur au
    # démarrage reste ainsi un vrai 502 plutôt qu'un flux 200 tronqué.
    try:
        first = await anext(chunks)
    except StopAsyncIteration:
        raise ProviderError("Le fournisseur a renvoyé une réponse vide") from None

    async def body() -> AsyncIterator[str]:
        yield first
        async for chunk in chunks:
            yield chunk

    return StreamingResponse(
        body(), media_type="text/plain; charset=utf-8", headers={"Cache-Control": "no-store"}
    )
