# atguigu/infrastructure/database.py

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession, create_async_engine, AsyncEngine

from atguigu.conf.config import settings

# 声明全局变量
# engine            ：异步数据库引擎，负责管理连接池和与数据库的通信
# session_factory   ：异步会话工厂，用于创建数据库会话（事务单元）
engine: AsyncEngine | None = None
async_session: async_sessionmaker[AsyncSession] | None = None

# 初始化
def init_db_engine() -> None:
    global engine, async_session

    # 1. 创建异步引擎
    # echo=False            ：SQL 语句日志输出，开发环境可设为True，生产环境设置为False
    # pool_pre_ping=True    ：每次从连接池取出连接前发送心跳查询（SELECT 1）检测连接是否存活，
    #                         若连接已断开则自动丢弃并创建新连接，避免"连接已失效"错误
    engine = create_async_engine(settings.database_url, echo=True, pool_pre_ping=True)

    # 2. 创建异步session工厂
    async_session = async_sessionmaker(engine, expire_on_commit=False)

# 关闭资源
async def close_db_engine():
    if engine is not None:
        await engine.dispose()


if __name__ == '__main__':

    async def test():

        # 初始化引擎
        init_db_engine()

        # 创建session
        async with async_session() as session:

            # text()：把 Python字符串 转换成 可执行SQL对象。
            result = await session.execute(text("SELECT 1"))

            # data = result.fetchall()
            data = result.fetchone()
            print(data)
            print(type(data))
            await session.commit()  # 显式提交，就不会再自动 ROLLBACK 了

        # 关闭引擎
        await close_db_engine()


    asyncio.run(test())