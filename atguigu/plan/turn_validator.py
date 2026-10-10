# atguigu/plan/turn_validator.py

from typing import Dict

from atguigu.domain.state import DialogueState
from atguigu.knowledge.intents import KnowledgeIntent
from atguigu.plan.models import TurnPlan, TurnPlanValidationResult, ClarifyReason
from atguigu.task.command.models import SetSlotsCommand, StartFlowCommand, ResumeFlowCommand, CancelFlowCommand
from atguigu.task.flow.flows import FlowsList


class TurnPlanValidator:

    def validate(
            self,
            state: DialogueState,
            turn_plan: TurnPlan,
            flow_list: FlowsList,
            intents: Dict[str, KnowledgeIntent]
    ) -> TurnPlanValidationResult:
        """
        校验 turn_plan
        :param turn_plan:
        :return:
        """

        active_tracks = self._active_tracks(turn_plan)

        # 1. 是否没有命中轨道
        if not active_tracks:
            return self._reject(ClarifyReason.MISSING_TRACK)

        # 2. 是否命中多条轨道
        if len(active_tracks) > 1:
            return self._reject(ClarifyReason.MULTIPLE_TRACKS)

        # 3. 获取唯一的轨道
        active_track = active_tracks[0]

        # 4. 判断轨道到底是哪一个
        if active_track == "task":
            # 4.1 业务任务轨道
            return self._validate_task(turn_plan, flow_list)

        if active_track == "knowledge":
            # 4.2 信息咨询任务轨道（后面2.7.2小节实现）
            return self._validate_knowledge(state, turn_plan, intents)

        # True：校验通过
        return TurnPlanValidationResult(valid=True)

    @staticmethod
    def _active_tracks(turn_plan: TurnPlan) -> list[str]:
        active_tracks: list[str] = []
        if turn_plan.task is not None:
            active_tracks.append("task")  # 轨道的名字

        if turn_plan.knowledge is not None:
            active_tracks.append("knowledge")  # 轨道的名字

        if turn_plan.chitchat is not None:
            active_tracks.append("chitchat")  # 轨道的名字

        return active_tracks

    def _reject(self, reason: ClarifyReason) -> TurnPlanValidationResult:
        return TurnPlanValidationResult(
            valid=False,
            reason=reason
        )

    def _validate_task(
            self,
            turn_plan: TurnPlan,
            flows: FlowsList,
    ) -> TurnPlanValidationResult:

        task_plan = turn_plan.task

        # 第一重:commands 不能为空
        if task_plan is None or not task_plan.commands:
            return self._reject(ClarifyReason.MISSING_TASK_COMMANDS)

        # 第二重:每个 command 都得是认识的类型
        allowed = (StartFlowCommand, ResumeFlowCommand, CancelFlowCommand, SetSlotsCommand)
        if not all(isinstance(cmd, allowed) for cmd in task_plan.commands):
            return self._reject(ClarifyReason.INVALID_TASK_COMMANDS)

        # 第三重:不能一次开多个流程
        start_commands = [cmd for cmd in task_plan.commands if isinstance(cmd, StartFlowCommand)]
        if len(start_commands) > 1:
            return self._reject(ClarifyReason.MULTIPLE_TASK_FLOWS)

        # 第四重:要开的流程必须真实存在
        if start_commands:
            flow = flows.get_flow_by_id(start_commands[0].flow)
            if flow is None:
                return self._reject(ClarifyReason.UNKNOWN_TASK_FLOW)

        # 校验成功
        return TurnPlanValidationResult(valid=True)
    def _validate_knowledge(
            self,
            state: DialogueState,
            turn_plan: TurnPlan,
            intents: Dict[str, KnowledgeIntent]
    ) -> TurnPlanValidationResult:

        knowledge_plan = turn_plan.knowledge
        if knowledge_plan is None or not knowledge_plan.intents:
            return self._reject(ClarifyReason.MISSING_KNOWLEDGE_INTENT)

        focused_object = state.focused_object
        for intent in knowledge_plan.intents:
            intent_meta = intents[intent]
            required_object = intent_meta.requires_object
            if required_object is not None:
                if focused_object is None or focused_object.type != required_object:
                    return self._reject(ClarifyReason.MISSING_FOCUSED_OBJECT)

        return TurnPlanValidationResult(valid=True)