# atguigu/task/handler.py

from atguigu.domain.messages import BotMessage
from atguigu.domain.state import DialogueState
from atguigu.task.command.models import Command
from atguigu.task.flow.flows import FlowsList


class TaskHandler:

    def __init__(self, flows:FlowsList):
        self.flows = flows

    async def handle(self, commands: list[Command], state: DialogueState) -> list[BotMessage]:
        return [BotMessage(text="任务已经处理")]