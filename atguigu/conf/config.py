# atguigu/conf/config.py
# uv add pydantic-settings

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Path(__file__) — 当前文件的绝对路径（atguigu/conf/config.py）
# .parents[2] — 向上两级目录，到达项目根目录（cusomer_service_demo/）
# 最终指向 项目根目录下的 .env 文件
ENV_FILE = Path(__file__).parents[2] / ".env"


class Settings(BaseSettings):
    # LLM
    llm_model: str
    llm_base_url: str
    llm_api_key: str

    # 商城 API
    commerce_api_base_url: str

    # 数据库
    database_url: str
    database_url_sync: str

    # 服务器
    app_host: str
    app_port: int

    # 从.env文件中读取配置信息
    # 如果读取真实环境变量，则不写这句话
    # extra="ignore" 表示忽略.env中有，这里没有的配置项，不会报错
    # env_file_encoding：如果遇到乱码问题则添加这个属性解决
    # 注意这里对象名必须叫model_config ，而且必须定义，否则配置会被回收
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore", env_file_encoding="utf-8")


@lru_cache
def get_settings():
    print("get_settings")
    return Settings()


# @lru_cache 会修改它所装饰的函数，
# 使其返回第一次返回的相同值，而不是每次都重新计算并执行函数代码。
settings = get_settings()

if __name__ == '__main__':
    # 第一次访问
    print(settings.llm_base_url)
    # 再次访问
    print(settings.llm_base_url)
