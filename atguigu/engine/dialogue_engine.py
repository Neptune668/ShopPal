# atguigu/engine/dialogue_engine.py
import time

from atguigu.domain.state import DialogueState
from atguigu.domain.messages import UserMessage, ProcessResult, BotMessage, MessageType
from atguigu.plan.turn_planner import TurnPlanner
from atguigu.task.handler import TaskHandler


class DialogueEngine:
    def __init__(
            self,
            turn_planner: TurnPlanner,
            task_handler: TaskHandler,
            knowledge_handler: KnowledgeHandler,
            # chitchat_handler: ChitchatHandler,
            # clarify_responder: ClarifyResponder,
            turn_plan_validator: TurnPlanValidator
    ) -> None:
        self.turn_planner = turn_planner
        self.task_handler = task_handler
        self.knowledge_handler = knowledge_handler
        # self.chitchat_handler = chitchat_handler
        # self.clarify_responder = clarify_responder
        self.turn_plan_validator = turn_plan_validator

    async def process_message(self, dialogue_state: DialogueState,
                              user_message: UserMessage) -> ProcessResult:

        # 1. 准备会话
        self._prepare_session(dialogue_state)

        # 2. 开启本轮turn
        self._begin_turn(dialogue_state, user_message)

        # 3. 按消息类型分流
        if user_message.type is MessageType.TEXT:
            messages = await self._handle_text_message(dialogue_state)
        else:
            # 对象消息(本节不实现,后面讲)
            # TODO
            pass

        # 4. 把本轮回复写入turn
        dialogue_state.pending_turn.bot_messages.extend(messages)
        # 提交:turn 进入 session 历史
        dialogue_state.commit_turn()

        # 5. 组装返回结果
        return ProcessResult(
            sender_id=user_message.sender_id,
            message_id=user_message.message_id,
            messages=messages,
        )

    def _prepare_session(self, dialogue_state: DialogueState) -> None:
        """
        准备会话
        :param dialogue_state:
        :return:
        """

        # 1. 获取当前会话
        session = dialogue_state.current_session()

        # 2. 如果当前会话不存在，则创建一个会话
        if session is None:
            dialogue_state.start_session()
            return

        # 3. 判断会话是否超时
        now = time.time()
        if now - session.last_activity_at > 60 * 60:  # 1小时
            # 关闭会话
            dialogue_state.close_current_session()
            # 重置运行时状态
            dialogue_state.reset_runtime_state_for_new_session()
            # 创建会话
            dialogue_state.start_session()
        else:
            # 更新会话（会话续期）
            session.last_activity_at = now

    def _begin_turn(self, dialogue_state: DialogueState, user_message: UserMessage) -> None:
        """
        开始一个turn
        :param dialogue_state:
        :param user_message:
        :return:
        """
        dialogue_state.begin_turn(user_message)

    async def _handle_text_message(self, dialogue_state: DialogueState) -> list[BotMessage]:

        # 1. 调 LLM 生成本轮计划（确定任务轨道）
        turn_plan = await self.turn_planner.predict(dialogue_state, self.task_handler.flows)

        # 2. 防幻觉校验(本节不实现,后面讲)
        # TODO

        # 3. 按轨道分发
        if turn_plan.task is not None:
            return await self.task_handler.handle(
                commands=turn_plan.task.commands,
                state=dialogue_state,
            )
        elif turn_plan.knowledge is not None:
            # TODO(本节不实现,后面讲)
            return None
        else:
            # TODO(本节不实现,后面讲)
            return None