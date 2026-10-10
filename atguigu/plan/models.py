# atguigu/plan/models.py
import json

from atguigu.task.command.models import Command
from pydantic import BaseModel


class TaskTurnPlan(BaseModel):
    commands: list[Command] = []  # 命令

    @classmethod
    def from_dict(cls, data: dict) -> "TaskTurnPlan":
        return cls(commands=[Command.from_dict(command) for command in data["commands"]])


class KnowledgeTurnPlan(BaseModel):
    intents: list[str] = []  # 意图

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeTurnPlan":
        return cls(intents=data["intents"])


class ChitchatTurnPlan(BaseModel):
    pass


class TurnPlan(BaseModel):
    """
    本轮对话的规划结果
    """
    task: TaskTurnPlan | None = None  # 业务任务的轨道
    knowledge: KnowledgeTurnPlan | None = None  # 信息咨询业务轨道
    chitchat: ChitchatTurnPlan | None = None  # 闲聊业务轨道

    @classmethod
    def from_dict(cls, data: dict) -> "TurnPlan":
        return cls(
            task=TaskTurnPlan.from_dict(data["task"]) if data.get("task") is not None else None,
            knowledge=KnowledgeTurnPlan.from_dict(data["knowledge"]) if data.get("knowledge") is not None else None,

            # 注意此处直接创建ChitchatTurnPlan对象即可，不需要做反序列化
            chitchat=ChitchatTurnPlan() if data.get("chitchat") is not None else None,
        )


class ClarifyReason(str, Enum):
    MISSING_TRACK = "missing_track"
    MULTIPLE_TRACKS = "multiple_tracks"
    MISSING_TASK_COMMANDS = "missing_task_commands"
    MISSING_KNOWLEDGE_INTENT = "missing_knowledge_intent"
    MISSING_FOCUSED_OBJECT = "missing_focused_object"
    OBJECT_REQUIRES_INTENT = "object_requires_intent"
    INVALID_TASK_COMMANDS = "invalid_task_commands"
    MULTIPLE_TASK_FLOWS = "multiple_task_flows"
    UNKNOWN_TASK_FLOW = "unknown_task_flow"


class TurnPlanValidationResult(BaseModel):
    valid: bool  # 是否有效
    reason: ClarifyReason | None = None  # 无效时的原因


if __name__ == '__main__':
    json_str1 = """
    {
      "task": {
        "commands": [
          {"command": "start_flow", "flow": "refund_request"}
        ]
      },
      "knowledge": null,
      "chitchat": null
    }
    """

    # 转成dict
    turn_plan1 = TurnPlan.from_dict(json.loads(json_str1))
    print(turn_plan1)

    json_str2 = """
    {
      "task": {
        "commands": [
          {"command": "set_slots", "slots": {"order_number": "A001"}}
        ]
      },
      "knowledge": null,
      "chitchat": null
    }
    """
    # 转成dict
    turn_plan2 = TurnPlan.from_dict(json.loads(json_str2))
    print(turn_plan2)
