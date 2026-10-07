# atguigu/api/dependencies.py

from fastapi import Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from atguigu.plan.turn_planner import TurnPlanner
from atguigu.service.dialogue_service import DialogueService
from atguigu.repository.dialogue_state_repository import DialogueStateRepository
from atguigu.engine.dialogue_engine import DialogueEngine

# 注意：必须通过这种方式引入database，需要的时候再获取： database.async_session()
from atguigu.infrastructure import database

# 不要通过这种方式引入async_session，会是一个NoneType
from atguigu.infrastructure.database import async_session
from atguigu.task.flow.loader import FlowLoader
from atguigu.task.handler import TaskHandler


async def get_session():
    """
    实际流程：
        进入 async with → 打开 session
        yield session → 把 session 交给repository函数使用
        路由函数执行完毕 → 回到 yield 之后
        退出 async with → 自动关闭 session ✅
    :return:
    """
    async with database.async_session() as session:  # 异步方式获取session  获取session要网络传输（耗时的）
        yield session


async def get_dialogue_state_repository(session: AsyncSession = Depends(get_session)):
    """
    创建 DialogueStateRepository 实例

    依赖链执行顺序：
       1. get_session() 打开 session 并 yield
       2. 这里拿到 session，创建 Repository
       3. Repository 被Service使用，Service被路由函数使用
       4. 路由函数返回后，get_session() 继续执行，自动关闭 session
    :param session:
    :return:
    """
    return DialogueStateRepository(session=session)
    # 3. 函数返回后，FastAPI 继续执行 get_session() y


# 4. 创建 DialogueEngine 实例
async def get_engine():
    base_path = Path(__file__).parents[3]
    user_flow_path = base_path / "flow_config" / "user_flows.yml"
    system_flow_path = base_path / "flow_config" / "system_flows.yml"

    loader = FlowLoader()
    flow_list = loader.load_many([user_flow_path, system_flow_path])

    return DialogueEngine(turn_planner=TurnPlanner(), task_handler=TaskHandler(flows=flow_list))

# 5. 创建 DialogueService 实例
async def get_dialogue_service(
        dialogue_state_repository: DialogueStateRepository = Depends(get_dialogue_state_repository),
        dialogue_engine: DialogueEngine = Depends(get_engine)
) -> DialogueService:
    return DialogueService(dialogue_state_repository=dialogue_state_repository, dialogue_engine=dialogue_engine)
