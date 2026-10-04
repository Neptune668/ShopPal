# atguigu/task/flow/loader.py

from pathlib import Path
from typing import List, Dict, Any

import yaml

from atguigu.task.flow.flows import FlowsList, Flow, FlowSlot
from atguigu.task.flow.steps import FlowStep, CollectFlowStep

"""
yaml --->dict---->数据模型
"""


class FlowLoader:
    """
    流程加载器（加载两个yaml文件）
    """
    def load_many(self, paths: List[Path]) -> FlowsList:
        flows: List[Flow] = []
        slots: Dict[str, FlowSlot] = {}
        for path in paths:
            # 1. 加载单个yaml文件的flow_list
            single_flows_list = self.load(path)
            # 2. 获取单个yaml的flows
            flows.extend(single_flows_list.flows)
            # 3. 检测重复槽位
            duplicate_slot_name = set(slots).intersection(single_flows_list.slots)
            if duplicate_slot_name:  # 去重可选(建议做去重)
                duplicates = ", ".join(sorted(duplicate_slot_name))
                raise ValueError(
                    f"flow定义中存在重复的槽位名称: {duplicates}."
                )
            # 4. 更新
            slots.update(single_flows_list.slots)
        return FlowsList(flows=flows, slots=slots)

    def load(self, path: Path) -> FlowsList:
        """
        加载单个yaml文件
        :param path:
        :return:
        """
        # 1. 读 YAML → dict
        with  open(path, 'r', encoding="utf-8") as f:
            data: Dict[str, Any] = yaml.safe_load(f)

        # 2. 加载slots部分
        slots: Dict[str, FlowSlot] = self._load_slots(data.get('slots', {}))

        # 3. 加载flows部分
        flows = self._load_flows(data.get('flows', {}), slots)

        return FlowsList(slots=slots, flows=flows)

    def _load_slots(self, yaml_slots_data: Dict[str, Any]) -> Dict[str, FlowSlot]:
        """
        加载槽位
        :param yaml_slots_data:
        :return:
        """
        slots = {}
        for slot_name, slot_dict in yaml_slots_data.items():
            slots[slot_name] = FlowSlot(
                name=slot_name,
                **slot_dict
            )

        return slots

    def _load_flows(self, yaml_flows_data: Dict[str, Any], slots_definition: Dict[str, FlowSlot]) -> List[Flow]:
        """
        加载流程
        :param yaml_flows_data:
        :param slots_definition:
        :return:
        """
        flows: List[Flow] = []
        for flow_id, flow_dict in yaml_flows_data.items():
            steps = [FlowStep.from_dict(step) for step in flow_dict.get('steps', [])]
            flows.append(
                Flow(
                    id=flow_id,
                    description=flow_dict.get('description', ''),
                    name=flow_dict.get('name'),
                    steps=steps,
                    slots=self._collect_flow_slots(slots_definition, steps)
                )
            )

        return flows

    def _collect_flow_slots(self, slots_definition: Dict[str, FlowSlot],
                            steps: List[FlowStep]) -> List[FlowSlot]:
        """
        收集流程中的槽位
        :param slots_definition:  业务的所有流程用到的所有槽位定义
        :param steps: 当前流程的所有步骤
        :return: 当前流程要用到的槽位定义
        """
        seen = set()
        flow_slots = []
        for step in steps:

            # 只看收集步骤
            if not isinstance(step, CollectFlowStep):
                continue

            # 去重
            # 流程中可能会在不同的step中有重复的槽位名字
            # (LLM看流程使用的槽位：在同一个流程下 没有必要给LLM两份一样的槽位名字)
            step_slot_name = step.slot_name
            if step_slot_name in seen:
                # 流程中有重复的槽位名字不添加
                continue
            seen.add(step_slot_name)

            # 用 get,查不到不报错
            slot_definition = slots_definition.get(step_slot_name)
            if slot_definition is not None:  # 流程中有的槽位名字对应的槽位定义有
                flow_slots.append(slot_definition)

        return flow_slots


if __name__ == '__main__':
    base_path = Path(__file__).parents[3]
    user_flow_path = base_path / 'flow_config' / 'user_flows.yml'
    system_flow_path = base_path / 'flow_config' / 'system_flows.yml'
    loader = FlowLoader()
    flows_list = loader.load_many([user_flow_path, system_flow_path])
    print(flows_list)
