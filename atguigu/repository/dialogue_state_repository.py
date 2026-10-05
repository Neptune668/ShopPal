# atguigu/repository/dialogue_state_repository.py

import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert
from atguigu.domain.state import DialogueState
from atguigu.models.dialogue_state import DialogueStateRecord


class DialogueStateRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def load_state(self, sender_id: str) -> DialogueState:
        """
        读操作
        :return:
        """

        # 1. 定义sql
        sql = select(DialogueStateRecord).where(DialogueStateRecord.sender_id == sender_id)

        # 2. 执行sql
        result = await self.session.execute(sql)

        # 3. 获取结果
        sate = result.scalar_one_or_none()

        if sate:
            # 将 state.state_json 反序列化成一个 DialogueState 对象
            state_dict = json.loads(sate.state_json)
            return DialogueState.model_validate(state_dict)

        return DialogueState(sender_id=sender_id)

    async def save_state(self, dialogue_state: DialogueState):
        """
        写操作(插入、修改)
        传统：插入之前先查询该条件（sender_id）对应的记录是否存在，如果不存在 则插入，反之修改
        进阶：负责将插入sql直接升级为修改sql(主键重复机制判断)
        :return:
        """

        # 1. 得到DialogueState的json字符串
        state_json: str = json.dumps(dialogue_state.model_dump(mode="json"))

        # 2. 定义插入的sql语句
        # 注意这里的依赖是：sqlalchemy.dialects.mysql.insert  而不是  sqlalchemy.insert
        insert_stmt = insert(DialogueStateRecord).values(
            sender_id=dialogue_state.sender_id, state_json=state_json
        )

        # 3. 升级update语句的sql
        update_stmt = insert_stmt.on_duplicate_key_update(
            state_json=insert_stmt.inserted.state_json
        )

        # 4. 执行sql
        await  self.session.execute(update_stmt)

        # 5. 提交
        await self.session.commit()