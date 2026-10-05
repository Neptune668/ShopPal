from fastapi import APIRouter, Depends

from atguigu.api.routers.dependencies import get_dialogue_service
from atguigu.api.schemas import ChatRequest, ChatResponse, ChatBotMessage, ChatObject
from atguigu.domain.messages import ProcessResult
from atguigu.service.dialogue_service import DialogueService

router = APIRouter()


# 定义路由接口

@router.post("/api/chat")
async def chat_endpoint(
        chat_request: ChatRequest,
        dialogue_service: DialogueService = Depends(get_dialogue_service)
) -> ChatResponse:
    # 1. 处理输入接口模型
    user_message = _build_user_message(chat_request)
    # 2. 业务处理
    process_result: ProcessResult = await dialogue_service.process_message(user_message)
    # 3. 处理输出接口模型
    return _build_chat_response(process_result)