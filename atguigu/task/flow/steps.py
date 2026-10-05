# atguigu/task/flow/steps.py

"""
步骤（节点）设计
"""
from enum import Enum
from typing import List, Dict, Any, Literal, Annotated
from pydantic import BaseModel, Field, TypeAdapter, field_validator
from atguigu.task.flow.links import FlowStepLink, StaticLink, ConditionalLink, FallbackLink


class ResponseDefinition(BaseModel):
    """
    响应的模式:静态模式(static) 改写模式(rephrase)
    """
    model: str = "static"  # 响应模式
    text: str  # 必填字段
    prompt: str | None = None


class FlowStepType(Enum):
    """
    流程的步骤类型
    """
    START = "start"
    END = "end"
    ACTION = "action"
    COLLECT = "collect"


class FlowStep(BaseModel):
    """
    流程模版
    """
    id: str  # 步骤ID
    type: FlowStepType  # 步骤类型
    next: List[FlowStepLink] = []  # 下一步
    description: str = ""  # 步骤描述

    @classmethod
    def from_dict(cls, step_data: dict[str, Any]) -> "FlowStep":
        step_type = step_data['type']
        clz = STEP_TYPE_TO_CLASS[step_type]
        return clz.from_dict(step_data)

    @staticmethod
    def base_fields(base_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        加载各个步骤的基础字段
        :param base_data: 各个步骤的字典数据
        :return:
        """
        return {
            "id": base_data['id'],
            "type": FlowStepType(base_data['type']),
            "description": base_data.get('description', ''),
            "next": FlowStep.build_links(base_data['next'])
        }

    @staticmethod
    def build_links(link_data: str | list[Dict[str, Any]]) -> List[FlowStepLink]:
        # 1. next是字符串
        if isinstance(link_data, str):
            return [StaticLink(target=link_data)]

        # 2. next是列表
        else:
            links = []
            for link_dict in link_data:
                if "if" in link_dict:
                    links.append(ConditionalLink(condition=link_dict['if'], target=link_dict['then']))
                else:
                    links.append(FallbackLink(target=link_dict['else']))
            return links


class StartFlowStep(FlowStep):
    """
    流程步骤：开始
    """
    type: FlowStepType = FlowStepType.START

    @classmethod
    def from_dict(cls, step_data: dict[str, Any]) -> "StartFlowStep":
        return cls(**FlowStep.base_fields(step_data))


class EndFlowStep(FlowStep):
    """
    流程步骤：结束
    """
    type: FlowStepType = FlowStepType.END

    @classmethod
    def from_dict(cls, step_data: dict[str, Any]) -> "EndFlowStep":
        return cls(**FlowStep.base_fields(step_data))


class ActionFlowStep(FlowStep):
    """
    流程步骤：执行某一个动作
    """
    type: FlowStepType = FlowStepType.ACTION

    action: str = ""  # 行动的名字（action_listen:哨兵-等你/action_response:告诉你/action_xxxx:找东西 ）
    args: dict | str = {}  # 动作参数，选填

    @classmethod
    def from_dict(cls, step_data: dict[str, Any]) -> "ActionFlowStep":
        return cls(**FlowStep.base_fields(step_data),
                   action=step_data['action'],
                   args=step_data.get('args', {}))


class CollectFlowStep(FlowStep):
    """
    流程步骤：收集某个槽位信息
    """
    type: FlowStepType = FlowStepType.COLLECT

    slot_name: str  # 必填字段
    response: ResponseDefinition  # 必填字段（填写的槽位）

    @classmethod
    def from_dict(cls, step_data: dict[str, Any]) -> "CollectFlowStep":
        return cls(
            **FlowStep.base_fields(step_data),
            slot_name=step_data['slot_name'],
            response=ResponseDefinition(**step_data['response'])
        )


STEP_TYPE_TO_CLASS = {
    "start": StartFlowStep,
    "action": ActionFlowStep,
    "collect": CollectFlowStep,
    "end": EndFlowStep
}
