# atguigu/infrastructure/llm.py
# uv add langchain
# uv add langchain-openai

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from atguigu.conf.config import settings

"""
如果没有 BaseChatModel，你可能需要：
为每个 AI 厂商写不同的代码（OpenAI 一套、百度一套、阿里一套...）
处理各种复杂的 API 调用细节
有了它之后：
统一标准：不管换哪个 AI 模型，代码写法都一样
简化操作：只需要关心"问什么"，不用关心"怎么问"
"""
llm: BaseChatModel = init_chat_model(
    model=settings.llm_model,
    model_provider="openai",
    api_key=settings.llm_api_key,
    base_url=settings.llm_base_url,
    temperature=0
)

if __name__ == '__main__':
    print(llm.invoke("你好,你是什么模型").content)