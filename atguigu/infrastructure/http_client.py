# atguigu/infrastructure/http_client.py
# uv add httpx

import asyncio
import httpx

# 全局变量
http_client: httpx.AsyncClient | None = None


# 初始化http客户端
def init_http_client():
    global http_client
    http_client = httpx.AsyncClient(timeout=10.0)


# 关闭资源
async def close_http_client():
    if http_client is not None:
        await http_client.aclose()


#   异步方式
# async def main():
#     async with httpx.AsyncClient() as client:
#         response = await client.get('http://localhost:18081/users/u1001/orders')
#         print(response.json())
#
# asyncio.run(main())

# 同步方式访问
# get_result = httpx.get('http://localhost:18081/users/u1001/orders')
# print(get_result.json())

if __name__ == '__main__':
    # 异步方式访问
    async def test():
        init_http_client()
        result = await http_client.get('http://localhost:18081/users/u1001/orders')
        print(result.json())

        await close_http_client()


    asyncio.run(test())
