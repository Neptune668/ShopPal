#读取文件测试
# atguigu/test/yaml/load_yml.py
from pathlib import Path

import yaml

path = Path(__file__).parents[1]/"flow_config"/"user_flows.yml"
print(path)
with open(path, "r", encoding="utf-8") as f:
    data = yaml.safe_load(f)
# print(path)
print(data)