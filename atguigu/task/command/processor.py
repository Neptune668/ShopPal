# atguigu/task/command/processor.py
from atguigu.domain.contexts import InterruptedSystemContext, StartedSystemContext, ResumedSystemContext, \
    CanceledSystemContext, TaskContext
from atguigu.domain.state import DialogueState
from atguigu.task.command.models import Command, StartFlowCommand, SetSlotsCommand, CancelFlowCommand, ResumeFlowCommand
from atguigu.task.flow.flows import FlowsList


class CommandProcessor:
    """
    命令处理器
    """

    def run(
            self,
            commands: list[Command],
            state: DialogueState,
            flows: FlowsList,
    ) -> None:
        """
        把命令应用到 state
        :param commands:
        :param state:
        :param flows:
        :return:
        """
        for command in commands:
            self._apply(command, state, flows)

    def _apply(
            self,
            command: Command,
            state: DialogueState,
            flows: FlowsList,
    ) -> None:
        """
        处理命令
        :param command:
        :param state:
        :param flows:
        :return:
        """
        if isinstance(command, StartFlowCommand):
            self._handle_start_flow(command, state, flows)
        elif isinstance(command, SetSlotsCommand):
            self._handle_set_slots(command, state)
        elif isinstance(command, CancelFlowCommand):
            self._handle_cancel_flow(state, flows)
        elif isinstance(command, ResumeFlowCommand):
            self._handle_resume_flow(command, state, flows)

    @staticmethod
    def _readable_flow_name(flow_id: str, flows: FlowsList) -> str:
        flow = flows.get_flow_by_id(flow_id)
        return flow.name if flow else flow_id

    @staticmethod
    def _activate_started_system_flow(state: DialogueState, flows: FlowsList, started_flow_id: str,
                                      started_flow_name: str):
        flow = flows.get_flow_by_id("system_task_started")
        state.start_active_system_task(StartedSystemContext(
            # flow_id=flow.id,
            step_id=flow.start_step().id,
            started_flow_id=started_flow_id,
            started_flow_name=started_flow_name,
        ))

    @staticmethod
    def _activate_interrupted_system_flow(
            state: DialogueState, flows: FlowsList, interrupted_flow_id: str, interrupted_flow_name: str,
            started_flow_id: str, started_flow_name: str):

        flow = flows.get_flow_by_id("system_task_interrupted")
        state.start_active_system_task(InterruptedSystemContext(
            # flow_id=flow.id,
            step_id=flow.start_step().id,
            interrupted_flow_id=interrupted_flow_id,
            interrupted_flow_name=interrupted_flow_name,
            started_flow_id=started_flow_id,
            started_flow_name=started_flow_name
        ))

    @staticmethod
    def _activate_resumed_system_flow(
            state: DialogueState, flows: FlowsList,
            resumed_flow_id: str, resumed_flow_name: str):

        flow = flows.get_flow_by_id("system_task_resumed")
        state.start_active_system_task(ResumedSystemContext(
            # flow_id=flow.id,
            step_id=flow.start_step().id,
            resumed_flow_id=resumed_flow_id,
            resumed_flow_name=resumed_flow_name
        ))

    @staticmethod
    def _activate_canceled_system_flow(
            state: DialogueState,
            flows: FlowsList,
            canceled_flow_id: str,
            canceled_flow_name: str
    ):
        """"
        激活取消流程的过场白
        """
        flow = flows.get_flow_by_id("system_task_canceled")
        state.start_active_system_task(CanceledSystemContext(
            # flow_id=flow.id,
            step_id=flow.start_step().id,
            canceled_flow_id=canceled_flow_id,
            canceled_flow_name=canceled_flow_name
        ))

    def _handle_start_flow(self, command: StartFlowCommand, state: DialogueState, flows: FlowsList) -> None:
        """
        开启业务任务
        :param command:
        :param state:
        :param flows:
        :return:
        """

        # 清除当前系统流程
        state.end_active_system_task()

        # 防御:不允许直接启动 system_ 开头的内部流程
        if command.flow.startswith("system_"):
            raise ValueError(f"不能直接启动系统流程：'{command.flow}'")

        # 校验:流程必须存在
        target_flow = flows.get_flow_by_id(command.flow)
        if target_flow is None:
            raise ValueError(f"未知流程：'{command.flow}'.")

        # 校验:流程必须有起点
        start_step = target_flow.start_step()
        if start_step is None:
            raise ValueError(f"流程 '{command.flow}' 没有开始步骤")

        active_task = state.active_task

        # ===== 情况一:当前有活跃任务 =====
        if active_task is not None:

            # 同一个流程：不重复启动
            if active_task.flow_id == command.flow:
                return

            # 不是同一个流程：把当前任务放进暂停栈
            state.interrupted_active_task()

            # 试着从暂停栈恢复要开的流程
            resumed = state.resumed_active_task(command.flow)
            if not resumed:
                # 要开的流程不在暂停栈 → 新建
                state.start_active_task(TaskContext(flow_id=command.flow, step_id=start_step.id))

            # 激活"打断"过场
            interrupted_flow_id = active_task.flow_id
            interrupted_flow_name = self._readable_flow_name(active_task.flow_id, flows)
            started_flow_id = command.flow
            started_flow_name = self._readable_flow_name(command.flow, flows)
            self._activate_interrupted_system_flow(
                state, flows, interrupted_flow_id, interrupted_flow_name,
                started_flow_id, started_flow_name)

            return

        # ===== 情况二:当前没有活跃任务 =====
        # 试着恢复同名任务
        resumed = state.resumed_active_task(command.flow)
        if resumed:
            # 要开的流程在暂停栈 → 激活"恢复"过场
            self._activate_resumed_system_flow(
                state, flows, command.flow, self._readable_flow_name(command.flow, flows)
            )
            return

        # 要开的流程从没做过 → 新建
        state.start_active_task(TaskContext(flow_id=command.flow, step_id=start_step.id))
        self._activate_started_system_flow(
            state, flows, command.flow, self._readable_flow_name(command.flow, flows)
        )

    def _handle_set_slots(self, command: SetSlotsCommand, state: DialogueState):
        if state.active_task:
            state.set_slots(command.slots)

    def _handle_cancel_flow(self, state: DialogueState, flows: FlowsList):

        # 获取当前流程
        active_task = state.active_task

        # 取消当前流程
        state.cancel_active_task()

        # 激活系统流程：“取消”过场
        canceled_flow_id = active_task.flow_id,
        canceled_flow_name = self._readable_flow_name(canceled_flow_id, flows)
        self._activate_canceled_system_flow(
            state, flows, canceled_flow_id, canceled_flow_name
        )

    def _handle_resume_flow(self, command: ResumeFlowCommand, state: DialogueState, flows: FlowsList):
        # ===== 第一步:确定要恢复哪个流程 =====
        if command.flow is not None:
            # 指名恢复:用户明确说了恢复哪个
            target_flow = flows.get_flow_by_id(command.flow)
            if target_flow is None:
                raise ValueError(f"未知流程 '{command.flow}'.")
            target_flow_id = target_flow.id
            target_flow_name = target_flow.name
        else:
            # 不指名恢复:用户只说"继续刚才的" → 取暂停栈栈顶(最近挂起的)
            if not state.paused_tasks:
                return
            top_paused = state.paused_tasks[-1]
            target_flow_id = top_paused.flow_id
            target_flow_name = self._readable_flow_name(target_flow_id, flows)

        # ===== 第二步:按"当前有没有活跃任务"恢复 =====
        active_task = state.active_task
        if active_task is not None:
            if active_task.flow_id == target_flow_id:
                return  # 已经在办它,不重复
            interrupted_flow_id = active_task.flow_id
            interrupted_flow_name = self._readable_flow_name(active_task.flow_id, flows)
            state.interrupted_active_task()
            if not state.resumed_active_task(target_flow_id):
                state.resumed_active_task()  # 恢复失败,回退（将state.interrupted_active_task()压入栈顶的任务出栈）
                return
            self._activate_interrupted_system_flow(  # ③打断当前+恢复目标
                state, flows, interrupted_flow_id, interrupted_flow_name,
                target_flow_id, target_flow_name)
        else:
            if not state.resumed_active_task(command.flow):  # ④没任务,直接恢复
                return

            resumed = state.active_task
            self._activate_resumed_system_flow(
                state, flows, resumed.flow_id, self._readable_flow_name(resumed.flow_id, flows))
