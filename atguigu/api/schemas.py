# atguigu/api/schemas.py

from pydantic import BaseModel


class ChatObject(BaseModel):
    """
    聚焦对象：
    对应前端点击订单/商品卡片时带的数据
    """
    type: str # 聚焦对象的类型 order、product
    id: str # 对象 id
    title: str | None = None # 对象标题
    attributes: dict = {} # 扩展属性，默认空字典


class ChatRequest(BaseModel):
    """
    请求对象（用户问题）
    `POST /api/chat` 的请求体
    注意：
    text 和 object 都是可选的，但实际使用中至少要传一个
    文本消息传 text，对象消息传 object
    """
    sender_id: str # 用户唯一标识
    message_id: str | None = None # 客户端消息 id，不传则服务端生成
    text: str | None = None # 文本消息内容
    object: ChatObject | None = None # 对象消息内容


class ChatBotMessage(BaseModel):
    """
    机器人消息
    """
    text: str | None = None
    object: ChatObject | None = None


class ChatResponse(BaseModel):
    """
    响应对象（机器人回复）
    """
    sender_id: str
    message_id: str
    messages: list[ChatBotMessage]


class HistoryMessage(BaseModel):
    """
    历史消息
    """
    role: str  # user or bot
    text: str | None = None
    object: ChatObject | None = None

class HistoryResponse(BaseModel):
    """
    历史消息列表
    `GET /api/chat/history` 的返回体。
    """
    sender_id: str
    messages: list[HistoryMessage]