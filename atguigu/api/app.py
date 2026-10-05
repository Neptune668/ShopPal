# atguigu/api/app.py

"""
定义fastapi实例

"""
from contextlib import asynccontextmanager
from fastapi import FastAPI

from atguigu.api.routers.chat_router import router
from atguigu.infrastructure.database import init_db_engine, close_db_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理：
        - 启动时：执行 yield 前的代码（初始化数据库引擎）
        - 运行中：yield 让出控制权，FastAPI 处理请求
        - 关闭时：执行 yield 后的代码（关闭数据库引擎）

    注意：
        - app 参数必须指定，类型为 FastAPI
        - 可通过 app.state 存储全局共享资源（当前未使用）
    """
    # 1. 应用启动
    print("启动服务器...")
    app.state.abc = "abc"  # 测试通过 app.state 存储全局共享资源

    init_db_engine()  # ← 执行这里，创建数据库连接池

    # 2. 进入 yield
    yield  # ← FastAPI 开始接收请求
    #    用户访问 API...
    #    用户访问 API...

    # 3. 应用关闭（Ctrl+C 或部署平台停止）
    await close_db_engine()  # ← 执行这里，关闭连接池
    print("服务器已关闭")


app = FastAPI(description="电商小二智能客服应用", lifespan=lifespan)

app.include_router(router)