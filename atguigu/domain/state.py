# atguigu/domain/state.py

import time
import uuid
from typing import Dict, Any

from pydantic import BaseModel

from atguigu.domain.contexts import TaskContext, SystemContext
from atguigu.domain.messages import FocusedObject, UserMessage, BotMessage

class Turn(BaseModel):
    """
    本轮对话的对象
    """
    turn_id: str    # 轮次唯一标识，使用 UUID
    user_message: UserMessage   # 这一轮用户说的那一句话
    bot_messages: list[BotMessage]  # 这一轮系统给出的所有回复

class Session(BaseModel):
    """
    会话信息
    """
    session_id: str  # 会话唯一标识，使用 UUID
    started_at: float  # 会话开始的时间戳
    last_activity_at: float  # 最后一次活动的时间戳，用来判断超时
    closed_at: float | None = None  # 会话关闭时间，未关闭时为 `None`
    turns: list[Turn] = []  # 这个会话里的所有轮次

class DialogueState(BaseModel):
    sender_id: str  # 用户id
    active_task: TaskContext | None = None  # 当前执行的业务任务
    paused_tasks: list[TaskContext] = []  # 当期暂停的业务任务（多个）
    active_system_task: SystemContext | None = None  # 当前执行的系统流程
    focused_object: FocusedObject | None = None
    sessions: list[Session] = [] # 当前用户的所有都存储起来
    current_session_id: str | None = None  # 当前用户的session的sessionID
    pending_turn: Turn | None = None  # turn会话的暂存区（变量：内存中缓冲区）

    # --------------任务相关--------------------------
    def start_active_task(self, active_task: TaskContext):
        """
        把传进来的 TaskContext 设为活跃任务。
        调用时机：当 TurnPlanner 判断用户发起了一个新业务任务时。
        :param active_task:
        :return:
        """
        self.active_task = active_task

    def end_active_task(self):
        """
        结束业务任务
        调用时机：当业务任务流程跑到 end 步骤时。
        :return:
        """
        self.active_task = None

    def cancel_active_task(self):
        """
        取消业务任务
        把活跃任务和当前系统过场都清空
        调用时机：用户主动说"算了不退了"这类取消意图时。
        :return:
        """
        self.active_task = None
        self.active_system_task = None

    def interrupted_active_task(self):
        """
        中断活跃任务
        把当前活跃任务 移到挂起列表，再清空活跃任务。
        调用时机：用户在任务 A 中途切到任务 B 时。
        :return:
        """
        self.paused_tasks.append(self.active_task)
        self.active_task = None

    def resumed_active_task(self, flow_id: str | None):
        """
        恢复业务任务:流程ID
        按 flow_id 在挂起列表里找一个任务，恢复为活跃任务，并从挂起列表里移除。
        调用时机：用户说"继续刚才的退款"这类意图时。

        注意：任务被恢复时，step_id 和 slots 都还在，所以可以从挂起前的位置接着跑，不用从头来。
        :return:
        """
        # 1. 恢复最近的任务
        if not flow_id:
            task = self.paused_tasks.pop()
            self.active_task = task
            return

        # 2. 精确恢复某一暂停的业务任务
        for task in self.paused_tasks:
            if task.flow_id == flow_id:
                self.active_task = task
                self.paused_tasks.remove(task)
                return

        # 3. 兜底
        task = self.paused_tasks.pop()
        self.active_task = task

    def start_active_system_task(self, active_system_task: SystemContext):
        """
        开启系统流程
        调用时机：每当系统要插播过场白（任务开始、打断、取消、恢复、收集槽位）时。
        :param active_system_task:
        :return:
        """
        self.active_system_task = active_system_task

    def end_active_system_task(self):
        """
        结束系统流程
        :return:
        """
        self.active_system_task = None

    def current_active_task(self):
        """
        返回当前正在执行的任务（系统流程、业务任务）
        先获取系统流程 如果获取不到 获取业务任务
        - 如果有系统流程，先返回系统流程
        - 否则返回业务任务

        为什么系统流程优先？
        因为系统流程往往是要插播一句过场白，必须先说完，然后才能让位给业务任务继续。
        :return:
        """
        return self.active_system_task or self.active_task

    # --------------槽位相关--------------------------
    def set_slots(self, slots: Dict[str, Any]):
        """
        设置槽位
        :param slots:
        :return:
        """
        self.active_task.slots.update(slots)

    def remove_slot(self, slot_name: str):
        """
        移除槽位
        :param slot_name: 移除的槽位名
        :return:
        """
        self.active_task.slots.pop(slot_name)

    # -------------- session相关 --------------------------
    def current_session(self) -> Session | None:
        """
        获取当前会话对象
        根据 current_session_id 在 sessions 里找出当前会话。
        :return:
        """
        for session in self.sessions:
            if session.session_id == self.current_session_id:
                return session

        return None

    def start_session(self):
        """
        开启新会话
        创建一个新的 Session，加进 sessions 列表，并把它设为当前会话。
        :return:
        """
        if self.current_session() is None:
            now = time.time()
            session_id = str(uuid.uuid4())
            session = Session(
                session_id=session_id,
                started_at=now,
                last_activity_at=now
            )
            self.sessions.append(session)
            self.current_session_id = session_id

    def close_current_session(self):
        """
        关闭当前会话
        给当前会话打上关闭时间戳，再把 current_session_id 置空。
        :return:
        """
        if self.current_session() is not None:
            # 1. 修改session的时间closed_at
            self.current_session().closed_at = time.time()
            # 2. 清空当前的session_id
            self.current_session_id = None

    def reset_runtime_state_for_new_session(self):
        """
        重置会话状态
        session会话超时新会话开始前的"清理工作"。
        注意：
        - 它只清运行时字段：当前任务、挂起任务、系统过场、聚焦对象
        - 它不清 sessions：历史会话需要保留
        :return:
        """
        self.active_task = None
        self.active_system_task = None
        self.paused_tasks = []
        self.focused_object = None
        self.pending_turn = None
        self.current_session_id = None

    # --------------turn相关--------------------------
    def begin_turn(self, message: UserMessage):
        """
        开始一个turn
        收到用户消息后，把它装进一个新的 turn 对象
        先放到 pending_turn，而不是直接进 session。
        :param message:
        :return:
        """
        if self.current_session():
            self.pending_turn = Turn(
                turn_id=str(uuid.uuid4()),
                user_message=message,
                bot_messages=[]
            )

    def commit_turn(self):
        """
        提交一个turn
        本轮处理完成（机器人回复也填好了）后
        把 pending_turn 追加到当前会话的 turns 里，再把 pending_turn 清空。
        :return:
        """
        if self.current_session():
            self.current_session().turns.append(self.pending_turn)
            self.pending_turn = None

    # --------------FocusedObject相关--------------------------
    def set_focused_object(self, focused_object: FocusedObject):
        """
        设置聚焦对象
        调用时机：
        用户发的不是文本而是一条对象消息时,例如前端点了订单卡片
        需要把这个对象设为当前关注的对象。
        :param focused_object:
        """
        self.focused_object = focused_object