# atguigu/task/flow/links.py

from pydantic import BaseModel


class FlowStepLink(BaseModel):
    """
    模版边（基类）
    """
    target: str  # 下一步的stepID


class StaticLink(FlowStepLink):
    """
    静态边
    对应 next 的值是字符串
    """
    pass


class ConditionalLink(FlowStepLink):
    """
    对应的是 next:[{if:"xxxxxx",then:step_id}]
    """
    condition: str  # 接收if 中的 xxxxx


class FallbackLink(FlowStepLink):
    """"
      对应的是 next:[{else:step_id}]
    """
    pass
