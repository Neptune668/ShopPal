# atguigu/domain/messages.py

"""
消息类型：两种
UserMessage(用户)
BotMessage(机器人)
"""
from enum import Enum
from pydantic import BaseModel

class FocusedObject(BaseModel):
    """
    聚焦对象
    """
    id: str  # 对象的唯一标识（如order_id、product_id）
    type: str  # 对象类型（如 "order", "product"）
    title: str | None = None  # 对象的标题（如 “纯棉T恤”）
    attributes: dict = {} # 其他额外信息

class MessageType(Enum):
    TEXT = "text"  # 文本类型
    OBJECT = "object"  # 对象类型

class UserMessage(BaseModel):
    sender_id: str  # 用户ID(必填字段)
    message_id: str  # 消息ID(必填字段)
    type: MessageType  # 消息类型（text or object）必填字段
    text: str | None = None  # 文本消息
    object: FocusedObject | None = None  # 对象类型的消息

class BotMessage(BaseModel):
    text: str | None = None
    object: FocusedObject | None = None

if __name__ == '__main__':
    fo = FocusedObject(id="1", type="2")

    # 把 Python 对象变成字典
    data = fo.model_dump(mode='json')
    # 把字典还原成 Python 对象
    obj = FocusedObject.model_validate(data)

    print(type(fo)) #FocusedObject对象
    print(type(data)) #dict字典
    print(type(obj)) #FocusedObject对象
