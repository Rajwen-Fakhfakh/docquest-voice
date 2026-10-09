from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_chat_service
from app.api.schemas import ChatRequest, ChatResponse
from app.core.chat import ChatService
from app.core.models import Message

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> ChatResponse:
    messages = [Message(role=m.role, content=m.content) for m in request.messages]
    return ChatResponse(answer=await service.reply(messages))
