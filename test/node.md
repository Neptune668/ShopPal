## 笔记01 自测题

1. 为什么三条轨道要设计成**互斥**的？分类这件事为什么不交给规则、而交给 LLM？
2. Knowledge 轨道为什么坚持"先检索再生成"，而不是让模型直接回答？
3. `expire_on_commit` 在同步和异步下的行为差异是什么？为什么异步必须为 `False`？
4. 对象消息（OBJECT）为什么可以跳过 `TurnPlanner` 的意图判断？

> 作业超官方文档搞清楚Q3

### Q1. 为什么三条轨道要互斥？分类为什么不交给规则？

**互斥的原因**，根本在于三条轨道的**执行机制完全不同**：

| 轨道      | 执行特征                                   |
| --------- | ------------------------------------------ |
| Task      | 多轮、有状态（要收集槽位、记住走到哪一步） |
| Knowledge | 一轮定稿（检索完就生成）                   |
| Chitchat  | 一轮定稿（无检索）                         |

如果一条输入能同时进两条，状态就打架了——Task 有"槽位收集到一半"的中间态，Knowledge 没有。互斥保证了**处理路径唯一**，结果可预期、可复现、可调试。代码上也干净：一个分支路口、三个 handler，职责不重叠。

**为什么不交给规则**，三个理由：

1. 用户表达是**开放自然语言**。"我那个快递到哪了"、"帮我看看上次买的那件衣服"、"算了不退了"——关键词要穷举到崩溃。
2. **规则维护成本随表达多样性指数增长。** 更致命的是它容易误判：`支持退货吗` 是 Knowledge，`我要退货` 是 Task，只差一个字，语义却是"问政策"和"要办事"。
3. **语义理解本就是 LLM 的强项**，交给它正好落在系统分工上——LLM 负责"理解"，代码负责"执行"。

再补一句：分类这种任务用 `temperature=0` 让输出尽量稳定，并且后面还有**确认 + 澄清 + 防幻觉校验**兜底。不是"信 LLM"，而是"用 LLM 理解，再用工程手段把不确定性收窄"。

### Q2. Knowledge 轨道为什么坚持"先检索再生成"？

一句话：**防幻觉。**

让模型自由回答"退款政策是怎样的"，它会用极其自信的语气编一套政策出来——这不是模型坏了，是它在做它被训练去做的事（预测下一个词）。检索的作用是把**可信文本**塞进上下文，把模型的任务从"回忆事实"降级为"组织语言"。

三类问题对应三种可信源，边界很清楚：

| 问题               | 可信源           | 模型负责             |
| ------------------ | ---------------- | -------------------- |
| 商品/订单信息      | 业务 API（实时） | 把结构化数据说成人话 |
| 退款/退货/配送政策 | FAQ              | 挑选 + 润色          |
| 平台规则/通用问题  | 知识库 RAG       | 归纳 + 表达          |

**数据负责"对不对"，模型负责"顺不顺"。** 这和 Task 轨道是同一个命题的两副面孔。

### Q3. `expire_on_commit` 在同步和异步下有什么差异？

`True`（默认）的语义是：**事务一提交，内存里的实体对象就被标记为"过期"**；之后再访问它的属性，会**隐式触发一次 SQL** 去数据库重新拉最新数据。

这本身是个有用的特性——你能拿到别人刚提交的值。但那个隐式查询是**同步阻塞**的，异步会话里不允许这种隐式 IO，所以会直接报错。
再补两个常见误解：

- **`False` 不等于"不刷新"**，只是"不自动刷新"——对象保持提交那一刻的快照。
- 如果异步下你**确实**需要最新数据，不能靠 `expire_on_commit`，而要**手写一条 SQL 主动查**。笔记里也是这么说的。

### Q4. 对象消息为什么可以跳过 `TurnPlanner`？

因为**意图已经确定了，没有不确定性需要推断**。

`TurnPlanner` 的职责是"从自然语言里推断用户想干什么 + 决定进哪条轨道"。而对象消息是前端在用户点击订单/商品卡片时发出的，它本身就携带了 `order_id` / `product_id`——系统**已经知道**用户在说哪个对象。

所以它走的是确定性路径，绕开规划：

```
对象消息 → 解析对象上下文 → 触发澄清并尝试补槽 → 直接进 Task 轨道
```

三个好处：

1. **省一次 LLM 调用**——更快、更省 token。
2. **结果更准**——不会误判（比如把"查这个订单"理解成闲聊）。
3. **能直接补槽**——对象自带的 `order_id` 刚好能填上 Task 轨道正在等的 `order_number`，用户点一下卡片就免掉了打字。

这恰好是整套系统的一条隐含原则：**能确定性解决的事，绝不交给 LLM。**

---

## 笔记02 自测题

1. TaskContext 里 flow_id 和 step_id 分别解决什么问题？为什么恢复任务时不需要从头开始？
2. 为什么 InterruptedSystemContext 要同时存 interrupted_* 和 started_* 两组字段？
3. 取消一个挂起的任务时，active_task 和 paused_tasks 分别发生什么变化？
4. Literal["system_task_started"] 在 Discriminated Union 里起到了什么作用？没有它会怎样？
5. 为什么说 pending_turn 是"纯粹的请求内瞬态"？它什么时候会被丢弃？

---

### Q1. `flow_id` 和 `step_id` 各解决什么问题？为什么恢复时不用从头开始？

三个字段各管一件事，不重叠：

| 字段      | 回答的问题                                     | 变化频率                   |
| --------- | ---------------------------------------------- | -------------------------- |
| `flow_id` | 用户在做**哪件事**（`refund_request`）         | 任务开始时定一次，之后不变 |
| `step_id` | 这件事**做到哪一步**了（`ask_order_number`）   | 每一轮都推进               |
| `slots`   | **已经拿到什么**（`{"order_number": "A001"}`） | 每收集到一个就更新         |

`flow_id` 决定去加载**哪一份 YAML 流程定义**，`step_id` 决定这份定义里**从哪个节点继续**。

**恢复时不用从头开始**，是因为整个 `TaskContext` 对象（含这三个字段）被**原封不动**压进了 `paused_tasks`。恢复只是把它从 `paused_tasks` 挪回 `active_task`——`step_id` 和 `slots` 一直躺在对象里，所以能从中断的那一步接着跑。

这也反过来解释了：**为什么 `TaskContext` 必须存 `step_id`、而不能只存 `flow_id`。** 只存 `flow_id` 就变成"从流程开头重来"，用户会被重复问一遍订单号。

### Q2. 为什么 `InterruptedSystemContext` 要存两组字段？

因为它要说的那句话里**同时出现了两个任务名**：

```yaml
text: "好的，我们先把{{ context.interrupted_flow_name }}放一放，先处理{{ context.started_flow_name }}。"
```

- `interrupted_*` → 被放下的那个（旧任务）
- `started_*` → 新起来的那个（新任务）

一个 `action_response` 要渲染两个名字，所以两组都得带上。对比看其他四个子类，就这一个特殊：

| 子类                           | 携带的名称字段                    |
| ------------------------------ | --------------------------------- |
| `StartedSystemContext`         | `started_*`                       |
| `ResumedSystemContext`         | `resumed_*`                       |
| `CanceledSystemContext`        | `canceled_*`                      |
| **`InterruptedSystemContext`** | **`interrupted_*` + `started_*`** |
| `CollectedSystemContext`       | `slot_name` + `response`          |

还有个细节：`interrupted_*` 只记录**最近这一次**被打断的任务，不是全部历史。因为系统只关心"刚刚被放下的那件事"，不需要念一长串履历。

### Q3. 取消一个**挂起**任务时，两者分别怎么变？

关键在于：**取消的对象不同，`cancel_active_task()` 的表现就不同。**
所以你的答案应该是：

- **取消挂起任务**：`active_task` **不变**（活跃任务继续做），`paused_tasks` **变短**（移除被点名的那一个）。
- **取消活跃任务**：`active_task` 清空，`paused_tasks` 不变。

再补一个容易漏的细节：**取消活跃任务时，`active_system_task` 也会一起清空**，而 `interrupted_active_task()` 只动 `active_task` 和 `paused_tasks`。这个差异是有意的——**取消意味着"这事不做了"，那句过场白也就没必要再播**；而打断只是"先放一放"，过场要说完。

### Q4. `Literal["system_task_started"]` 起什么作用？没有它会怎样？

**两个作用，缺一不可：**

1. **锁定取值。** 把 `flow_id` 从普通 `str` 收紧成"只能是这一个值"。写错拼写直接报错，而不是运行时静默出错。
2. **充当鉴别字段（discriminator）。** 配合 `Field(discriminator="flow_id")`，Pydantic 读字典里的 `flow_id` 值，去联合类型里找**哪个成员声明了这个 Literal**，然后直接实例化对应子类。

**没有它会怎样？** 如果五个子类都写 `flow_id: str`，它们在类型上完全一样，Pydantic 无法从类型层面区分——联合匹配会退化成"按顺序试着塞进去"，很可能匹配到第一个能装下的类，**子类特有字段被悄悄丢掉**，还原出一个语义错误的对象。

那你就只能手写映射表兜底：

```python
MAP = {
    "system_task_started": StartedSystemContext,
    "system_task_interrupted": InterruptedSystemContext,
    # ... 每加一个子类都要记得加一行
}
cls = MAP[data["flow_id"]]
obj = cls.model_validate(data)
```

能跑，但代码更长，而且**新增子类时极易忘记同步这张表**。

所以 `Literal + discriminator` 的真正价值是：**用类型声明替代手写的分发逻辑。**

````
这段是在解释 `contexts.py` 里 `StartedSystemContext` 那行代码为什么要这么写：

```32:32:atguigu/domain/contexts.py
    flow_id: Literal["system_task_started"] = "system_task_started"
```

## 它在问什么

**问题**：`flow_id` 明明可以直接写 `flow_id: str`，为什么非要用 `Literal["system_task_started"]` 把它锁死成一个固定值？不用会怎样？

**背景**：`contexts.py` 有 5 个 `SystemContext` 子类（开始/中断/取消/恢复/收集），它们被合并成一个联合类型：

```69:78:atguigu/domain/contexts.py
SystemContextUnion = Annotated[
    StartedSystemContext |
    ...
    Field(discriminator="flow_id")
]
```

当一段 JSON（比如从数据库还原的状态快照）进来时，程序必须判断：这段数据该还原成 5 个子类里的哪一个？`flow_id` 就是用来做这个判断的标签。

## 它在答什么

`Literal` 在这里干两件事：

1. **锁定取值**——告诉 Pydantic：`flow_id` 只能是 `"system_task_started"`，写错拼写直接报错。
2. **当"鉴别标签"（discriminator）**——每个子类都用 `Literal` 声明了自己专属的 `flow_id`。Pydantic 拿到数据后看 `flow_id` 是哪个值，就知道该实例化哪个子类。

## 为什么缺了它不行（核心）

如果 5 个子类都写 `flow_id: str`，那它们在**类型层面长得一模一样**，Pydantic 分不清谁是谁。

打个比方——**快递分拣**：
- `flow_id` = 包裹上的标签
- 5 个子类 = 5 个格子
- `Literal` = 规定"每个格子只收贴特定标签的包裹"
- `discriminator` = 分拣员，看标签直接扔进对应格子

如果标签随便写（`str`），分拣员认不出，只能**挨个格子试**：哪个格子能装下就塞哪个。结果就是——包裹里多出来的东西（子类特有字段，如 `started_flow_id`）**被悄悄丢掉**，还原出一个"半残"的错误对象，还不报错。

这也是 `contexts.py` 的 `__main__` 演示的坑：用父类 `SystemContext.model_validate(data)` 时，**子类特有字段就丢了**（注释里那句"用父类的序列化方法没办法将子类的字段序列化出来"）。

## 一句话总结

这段 Q&A 说的是：**用 `Literal + discriminator`，把"根据 flow_id 手动判断该 new 哪个类"这段分发逻辑，直接写进类型声明里让 Pydantic 自动完成**——省掉一张要手动维护、新增子类极易忘改的映射表。

需要的话，我可以跑一下 `contexts.py` 的 `__main__`，把"父类还原 vs 适配器还原"的字段差异实际打印出来给你看。
````

### Q4.5 反序列化做了那几步操作？

###### 步骤1：在每个子类中添加 Literal 类型的 flow_id 字段

   - 作用：作为"身份标签"，唯一标识每个子类

   - 原理：Pydantic 通过读取这个字段的值来判断应该创建哪个子类的实例

在`contexts.py`中的`SystemContext` 的所有子类中添加`flow_id`：

```python
class StartedSystemContext(SystemContext):
    ...
    # 使用 Literal 类型固定 flow_id 值，作为 Discriminated Union 的区分字段
    flow_id: Literal["system_task_started"] = "system_task_started"

class InterruptedSystemContext(SystemContext):
    ...
    flow_id: Literal["system_task_interrupted"] = "system_task_interrupted"

class CanceledSystemContext(SystemContext):
    ...
    flow_id: Literal["system_task_canceled"] = "system_task_canceled"

class ResumedSystemContext(SystemContext):
    ...
    flow_id: Literal["system_task_resumed"] = "system_task_resumed"

class CollectedSystemContext(SystemContext):
    ...
    flow_id: Literal["system_collect_information"] = "system_collect_information"
```

###### 步骤2：定义联合类型 SystemContextUnion

   - 使用 Annotated 将所有子类组合成一个联合类型
   - 通过 `Field(discriminator="flow_id")` 指定 flow_id 为区分字段
   - Pydantic 会根据 flow_id 的值自动选择正确的子类进行反序列化

在`contexts.py`中添加如下定义：

```python
# 定义系统流程的联合类型
SystemContextUnion = Annotated[
    StartedSystemContext |
    InterruptedSystemContext |
    CanceledSystemContext |
    ResumedSystemContext |
    CollectedSystemContext,
    Field(discriminator="flow_id")
]
```

###### 步骤3：创建 TypeAdapter 适配器实例

   - TypeAdapter 是 Pydantic V2 提供的工具，用于处理非 BaseModel 类型
   - 提供 validate_python() 方法替代 model_validate()

在`contexts.py`中添加如下定义：

```python
# 创建适配器实例
system_context_adapter = TypeAdapter(SystemContextUnion)
```

###### 步骤4：使用适配器进行类型转换

   - 反序列化：system_context_adapter.validate_python(data)
   - 优势：无需手动维护映射字典，代码更简洁、类型更安全

测试序列化，在`contexts.py`中添加如下测试代码：

```python
# 使用适配器的 validate_python()：替代 model_validate()
obj = system_context_adapter.validate_python(data)

print(type(obj))
print(obj)
```

### Q5. 为什么说 `pending_turn` 是"纯粹的请求内瞬态"？什么时候被丢弃？

"请求内瞬态"的意思是：**它的生命周期只覆盖一次消息处理，从不参与持久化。**

生命周期是这样的：

| 阶段            | 发生什么                                          |
| --------------- | ------------------------------------------------- |
| `begin_turn()`  | 把 `user_message` 放进 `pending_turn`             |
| 引擎处理中      | 不断往 `pending_turn.bot_messages` 追加回复       |
| `commit_turn()` | 才把它 append 进 `session.turns`                  |
| 落库            | 只序列化 `sessions`，**`pending_turn` 不进 JSON** |

**被丢弃的三种情况：**

1. **处理中途抛异常** —— 没走到 `commit`，`pending_turn` 随请求结束消失，`session.turns` 保持干净。
2. **判定为非法/重复消息，决定不入库** —— 直接不调 `commit` 就行，不需要写任何"回滚"逻辑。
3. **进程崩溃** —— 因为从未落库，磁盘上不会留下脏数据。

换句话说：**用一点点暂存成本，换取"`session.turns` 永远只包含完整的、已成功处理的一问一答"。**

你之前学到的 `expire_on_commit` 是数据库层面的事务控制，而 `pending_turn` 是**业务对象层面**的同类思想——都是在解决"别留下半成品"。

---

### 一句话回顾

这五道题其实都在讲同一个主题：**对象要承载足够的信息，才能在正确的时机被正确地还原。**

- `TaskContext` 存全三个字段 → 恢复时能**从中断处**接着跑（Q1）。
- `InterruptedSystemContext` 存两组名字 → 一句话里能同时**念出**两个任务（Q2）。
- `paused_tasks` 和 `active_task` 各管一段 → 取消才可能区分两种语义（Q3）。
- `Literal` 给子类一个身份标签 → 反序列化能**自动**还原成正确类型（Q4）。
- `pending_turn` 暂存后才提交 → 历史对象**永远完整**（Q5）。

要不要接着上 **笔记04（三层架构）**？它是把 01 的分层、02 的状态对象、03 的流程定义三者真正接起来跑起来的一篇——学完它，你就能完整地在脑子里跑通一条消息了。

## 笔记03 自测题

1. collect 相比手写 action_response + action_listen，省掉的到底是什么？
2. args: context.response 里的 context.response 是从哪来的？
3. StaticLink 和 FallbackLink 字段完全一样，为什么还要分成两个类？
4. 为什么加载器要在 load_many 阶段就检查槽位重名？
5. flow.slots 和 FlowsList.slots 有什么区别？

### Q1. `collect` 相比手写 `action_response + action_listen`，省掉的是什么？

省掉的是**"问 + 等"这一组重复的交互细节**。

对比一下成本：收集 5 个字段，基础写法要写 **10 个 step**（5 组"问+等"）；用 `collect` 只要 **5 个 step**，每个只声明"我要哪个槽位、问的话是哪句"。

|            | 基础版本                               | collect 版本                             |
| ---------- | -------------------------------------- | ---------------------------------------- |
| 每个 slot  | 写 `action_response` + `action_listen` | 只写一个 `collect`                       |
| 等待逻辑   | 每个 slot 各写一遍                     | 由 `system_collect_information` 统一处理 |
| 配置关注点 | 交互细节（怎么问、怎么等）             | 业务需要什么信息                         |

本质是把**业务意图**和**交互实现**解耦了。

### Q2. `args: context.response` 里的 `context.response` 从哪来？

来自**业务 flow 里那个 `collect` step 的 `response:` 块**。

执行器进入 `system_collect_information` 之前，会把 collect step 的 `response` 放进系统上下文；于是 `context.response` 就等于：

```yaml
text: "请告诉我你的订单号。"
```

而 `args: context.response` 的意思是"`action_response` 的参数**整体**取自 `context.response`"，所以它等价于把这个 `response` 块直接当作 args 用。

这就是 collect 能复用的关键：**系统 flow 只定义"怎么问怎么等"的骨架，具体问什么由调用方通过 context 注入。**

### Q3. `StaticLink` 和 `FallbackLink` 字段一样，为什么还要分成两个类？

字段确实一样（都只有 `target`），差别**纯粹是语义**：

| 类             | 语义                   | 对应 YAML             |
| -------------- | ---------------------- | --------------------- |
| `StaticLink`   | 无条件必走             | `next: step_id`       |
| `FallbackLink` | 前面条件全不成立时才走 | `next: [{else: ...}]` |

分开是为了让**执行器能直接按类型处理**：静态边可以直接跳；条件边要先求值 `condition`；兜底边只在前面全不匹配时生效。

如果合成一个类，就得额外加个标志位去判断——**这是"用类型表达语义"**：让类型系统替你讲清不变量，比注释和布尔标志位都可靠。

### Q4. 为什么要在 `load_many` 阶段就检查槽位重名？

**fail fast。**

不做检测的话，`slots.update(...)` 会让后加载的文件**悄悄覆盖**同名槽位。等到用户对话到一半，才发现"退款原因"字段的值莫名其妙变成了别的东西——这类问题定位成本极高。

所以做法是：加载时求交集，非空就立刻抛错，并把冲突的槽位名直接列出来。

```python
duplicate = set(slots).intersection(single_flows_list.slots)
if duplicate:
    raise ValueError(f"flow定义中存在重复的槽位名称: {', '.join(sorted(duplicate))}.")
```

这是配置系统的通用原则：**配置错误要在加载期死掉，绝不能带到运行期。**

### Q5. `flow.slots` 和 `FlowsList.slots` 有什么区别？

一个是**总目录**，一个是**领料单**。
|      | `FlowsList.slots`                            | `flow.slots`                                |
| ---- | -------------------------------------------- | ------------------------------------------- |
| 类型 | `Dict[str, FlowSlot]`                        | `List[FlowSlot]`                            |
| 来源 | YAML 的 `slots:` 块                          | `_collect_flow_slots` 从全局表里挑          |
| 范围 | 所有流程共享的全部槽位                       | 单个流程实际用到的子集                      |
| 谁用 | **加载期校验**：collect 引用的 slot 是否存在 | **运行时**：告诉 LLM "这个流程关心哪些字段" |

注意右图里 `order_status` 和 `product_id` 被过滤掉了——因为 `refund_request` 的步骤里没有 `collect` 它们。**"这个流程关心什么"的答案，完全由它自己的 collect step 决定。**

---

### 一句话回顾

这九道题其实在反复讲同一件事的四个侧面：

- **分工**（01-Q1/Q2、03-Q1）：能交代码做的，绝不交给 LLM。
- **确定性**（01-Q4）：信息已经明确时，不要再推理。
- **尽早失败**（03-Q4）：配置问题在加载期死，不要带到运行期。
- **用类型和结构表达语义**（03-Q3/Q5）：让不变量被代码强制，而不是靠注释约定。

要不要接着开 **笔记02（领域模型 domain）**？它是 01 里那句"Domain 层：消息、上下文、对话状态等领域模型"的具体展开，也是理解 04 三层架构的前置。



## 笔记04 自测题

1. 为什么这一节要给引擎写"占位实现"而不是等它写完？这依赖了什么编程原则？
2. schema 和 domain 两套模型分开，具体避免了什么问题？
3. `load_state` 对新用户为什么返回空对象而不是 `None`？这样做给上层省掉了什么？
4. `save_state` 为什么用 upsert 而不是"先查再决定 insert/update"？
5. 为什么 `from ...database import async_session` 会拿到 `None`，而 `import database` 不会？

-----

### Q1. 为什么先写"占位引擎"？依赖什么原则？

**理由**：引擎要搞 LLM 路由、流程推进、知识检索，写完它周期很长。先用一句固定回复的假引擎，能让整条链路（HTTP → Service → Repository → DB → 原路返回）**当场跑通、当场验证**。等真引擎写好，把占位一换，上下游一行都不用改。

**依赖的原则**：**面向接口编程 / 契约优先**。只要方法签名不变——

python

```python
process_message(self, dialogue_state, user_message) -> ProcessResult
```

实现可以随意替换。**占位实现也是合法实现，它满足了同样的契约。**

这也是一条通用开发节奏：**先用假实现打通骨架，再逐个替换成真实现。**

### Q2. schema 和 domain 分开，避免了什么问题？

混在一起会丢掉两样东西：

添加到对话

| 混用的问题                                                   | 分开后的好处                                             |
| :----------------------------------------------------------- | :------------------------------------------------------- |
| 对外契约和业务模型被**绑死**——前端加字段污染 domain，domain 重构破坏接口 | **职责清晰**：schema 是给前端的契约，domain 是给业务用的 |
| 内部重构与对外契约**互相牵制**                               | **内外解耦**：一方改动不波及另一方                       |

举个具体差异：domain 里用 `MessageType` 枚举显式表达消息形态，而 schema 里用"`text` 和 `object` 哪个非空"隐式表达——**两者按各自的需要设计，不必将就对方**。而且 Web 层多出一个明确的"翻译点"，出问题时能一眼判断是契约问题还是业务问题。

### Q3. `load_state` 对新人为什么返回空对象而不是 `None`？

因为**上层就永远不用区分老用户和新用户了**。

python

```python
if sate:
    return DialogueState.model_validate(json.loads(sate.state_json))
return DialogueState(sender_id=sender_id)     # ← 新用户：给一个干净的空状态
```

如果返回 `None`，上层每次都要写 `if state is None: state = DialogueState(...)`——逻辑分散、容易漏。这是典型的"**把边界情况在内部消化掉**"的接口设计：让调用方少想一件事。

而且空对象语义上是**正确**的：新用户的对话状态本来就是"什么都没有"，拿它去跑第一轮完全成立。

### Q4. 为什么用 upsert 而不是"先查再决定"？

因为它要同时处理两种情况：新用户该 `INSERT`，老用户该 `UPDATE`。

添加到对话

| 做法                                 | 数据库往返 | 并发风险                                                  |
| :----------------------------------- | :--------- | :-------------------------------------------------------- |
| 先 SELECT 判断，再 INSERT 或 UPDATE  | **两次**   | ⚠️ 有竞态：两个请求同时判断"不存在"，都去 INSERT，一个失败 |
| `INSERT ... ON DUPLICATE KEY UPDATE` | **一次**   | ✅ 冲突交给数据库处理，无竞态                              |

关键依赖细节：必须用 MySQL 方言的 `from sqlalchemy.dialects.mysql import insert`，标准 `sqlalchemy.insert` 没有 `on_duplicate_key_update`。

### Q5. 为什么 `from ...database import async_session` 会拿到 `None`？

这是 Python 导入语义的差异：

添加到对话

| 写法              | 拿到的是         | 结果                                                         |
| :---------------- | :--------------- | :----------------------------------------------------------- |
| `from X import y` | **值快照**       | 导入那一刻 `async_session` 还是 `None`，名字就被绑定成 `None`，之后模块里再赋值也不同步 |
| `import X`        | **模块对象引用** | 每次访问 `X.y` 都读当前属性，能拿到后来赋的真值              |

时间线是关键：**模块导入阶段（uvicorn 启动瞬间）远早于 `lifespan` 执行阶段（服务启动）。**

## 笔记05 自测题

1. 为什么要给 LLM 提供 `available_flows`？不提供会出现什么问题？
2. `StartFlowCommand` 带 `flow`、`CancelFlowCommand` 不带任何字段——这个差异背后遵循的是什么原则？
3. `ResumeFlowCommand.flow` 为什么是 `str | None`？对应了哪两种用户说法？
4. 提示词里为什么必须包含 `active_task`？缺了它，LLM 会犯什么错？
5. `prompt | llm | JsonOutputParser` 这三个环节各自把数据变成了什么形态？

笔记05 的五道题：

---

### Q1. 为什么要提供 `available_flows`？不提供会怎样？

`available_flows` 是给 LLM 的**"可选范围"围栏**——一份业务说明书，列出系统支持哪些流程（`refund_request` / `logistics_tracking` / `order_status`…）以及它们各自的 `name` / `description`。

**不提供的后果：瞎编 flow id。**

LLM 会根据自己的想象生成 `refund`、`apply_refund`、`退款` 这类**不存在的 id**。`StartFlowCommand(flow="refund")` 到了 TaskHandler 里就查不到对应流程 → 运行时报错，或者流程根本起不来。

这背后是一条设计哲学：**约束优于校验。** 与其等 LLM 犯错后再去纠正，不如一开始就把可选范围摆明，让它**很难犯错**。`available_flows` 和 `knowledge_intents` 就是两道这样的围栏。

另外别忘了那个优化细节——`available_flows` **特意去掉了 `steps`**：

> 只告诉 LLM "有哪些流程"，不告诉它"流程内部怎么走"。既省 token，又防止它被内部细节干扰。

### Q2. `StartFlowCommand` 带 `flow`、`CancelFlowCommand` 不带字段，背后是什么原则？

原则是：**命令的字段由"执行这个动作所必需的信息"决定，不多不少。**

| 命令          | 需要额外信息吗 | 为什么                                       |
| ------------- | -------------- | -------------------------------------------- |
| `start_flow`  | ✅ 需要 `flow`  | 系统有多个流程，必须知道"开哪个"             |
| `cancel_flow` | ❌ 不需要       | 取消的是**当前活跃的**那个，系统自己知道是谁 |

如果给 `CancelFlowCommand` 也硬塞一个 `flow` 字段，LLM 就**被迫编一个值**——本来不需要信息的地方，反而制造了新的出错面。

这是**接口最小化**：能让系统自己知道的，就不要问用户（也不要问 LLM）。

### Q3. `ResumeFlowCommand.flow` 为什么是 `str | None`？

因为"继续"在真实对话里有**两种说法**：

| 用户说法                                | `flow` 的值        | 系统行为                 |
| --------------------------------------- | ------------------ | ------------------------ |
| "继续刚才的" / "接着刚才那个"           | `None`             | **弹栈顶**（LIFO）       |
| "继续刚才的退款" / "把物流查询接着做完" | `"refund_request"` | **精确匹配**，可跨过栈顶 |

这正好对应笔记02 里 `resumed_active_task(flow_id=None)` 的两个分支：

```python
if not flow_id:                                # 不指名 → 弹栈顶
    self.active_task = self.paused_tasks.pop()

for i, task in enumerate(self.paused_tasks):   # 指名 → 精确匹配，能拿到中间层
    if task.flow_id == flow_id: ...
```

如果强制必填，用户说"继续刚才的"时 LLM 就只能瞎猜一个 flow；如果强制不填，用户指名时又表达不出来。**`None` 本身也是一种有意义的输入**——"我不指定，你按最近的那个来"。

### Q4. 提示词里为什么必须有 `active_task`？缺了会怎样？

它提供的是**"上下文坐标"**。缺了它，LLM 会**分不清"回答当前流程"还是"开新业务"**。

场景：用户正在退款流程里，系统刚问了"请告诉我你的订单号"，用户回 `A20240315001`。
还有一种反向的错法：用户说"我要退款"时，如果 LLM 不知道**当前已经在退款流程里**（`active_task = refund_request`），它可能又发一条 `start_flow`，导致**重复开启同一个流程**。

所以 `active_task` 的作用可以概括成：**没有它，每一句话都变成孤立的一句话。**

### Q5. `prompt | llm | JsonOutputParser` 三个环节各把数据变成什么形态？

| 环节               | 输入                             | 输出       | 形态变化                                  |
| ------------------ | -------------------------------- | ---------- | ----------------------------------------- |
| `prompt_template`  | `inputs_prompt` 字典（7 个字段） | 最终提示词 | **dict → str**                            |
| `llm`              | 提示词文本                       | 模型回复   | **str → str**（内容是 JSON 格式的字符串） |
| `JsonOutputParser` | JSON 字符串                      | 字典       | **str → dict**                            |

最后再加一步 `TurnPlan.from_dict(dict)` → **对象**。

串起来就是：

```
dict  →  str  →  str(JSON)  →  dict  →  TurnPlan 对象
```

两个补充点：

- **`prompt_template` 这一步是 jinja2 在干活**。必须写 `template_format="jinja2"`——LangChain 默认是 f-string 风格，不声明的话模板里的 `{{ }}` 渲染不出来。
- **`JsonOutputParser` 能工作，前提是提示词里明确要求 LLM 输出 JSON**。如果模型回的是"好的我明白了，你要退款"这种自然语言，解析当场就炸。

反过来看，这正是为什么整个系统要坚持**结构化输出**：**没有结构化输出，就没有可靠的自动化。** `Command` 把自由文本收敛成四类原子指令、`available_flows` 把"能选什么"框死、`JsonOutputParser` 把结果变成程序能读的对象——三道措施都在做同一件事：**把 LLM 的概率性输出，转成代码确定性可执行的输入。**

-----

这五道题其实在讲同一个主题的两个方向：

**向外——把范围框死**（Q1、Q2）：
给 LLM 划定"能选什么"（`available_flows`），让命令字段"按需最小"（取消不带参数）。**约束在前，比纠错在后便宜得多。**

**向内——把上下文给足**（Q3、Q4）：
`active_task` 让 LLM 知道"现在在哪一步"，`interrupted_tasks` 让它知道"还搁着哪些事"；`ResumeFlowCommand.flow` 的 `None` 也是有效输入。**LLM 判断得准不准，直接取决于你喂给它什么。**

而 Q5 是收口：**这些努力最终都要收敛成结构化数据，否则代码没法执行。**

---

## 笔记06 自测题

1. 为什么校验器只返回原因码、不直接生成回复话术？这样拆有什么好处？
2. task 的第二重校验（命令类型合法）里，`Command.from_dict` 已经会报错了，为什么还要再查一遍？
3. 场景 A 和场景 C 都是"流程进行中用户点了订单"，为什么处理方式完全不同？判定靠的是哪个方法的哪一步？
4. 对象消息能填槽时为什么不直接改 `state`，而要绕一圈构造 `SetSlotsCommand`？
5. 澄清回复为什么坚持"先写死基础话术、再让 LLM 润色"？如果只用 LLM 生成会怎样？



笔记06 的五道题：

---

### Q1. 为什么校验器只返回原因码、不生成话术？

因为这两件事**变化频率完全不同，而且会被不同的地方用到**。

| 好处           | 说明                                                         |
| -------------- | ------------------------------------------------------------ |
| **单一职责**   | validator 只关心"对不对"，responder 只关心"怎么跟用户说"     |
| **解耦变化点** | 原因码是稳定的（9 种固定），话术是易变的（调语气、多语言、A/B 测试）。分开后改话术不动校验逻辑 |
| **可复用**     | 同一个 reason 会被**多处**触发——文本校验失败会用到，对象消息的场景 B 也会用到 `OBJECT_REQUIRES_INTENT`。话术写在校验器里，对象消息那条线就用不上了 |
| **可测试**     | 校验器是纯判断，返回一个枚举值，测试极易写，不用 mock LLM    |

还有一层容易被忽略：**校验器本身不应该依赖 LLM**（它是确定性的防线），而生成话术要调 LLM。混在一起，会让"确定性的校验"被"不确定的 LLM"污染。

### Q2. `Command.from_dict` 已经会报错了，为什么还要再查一遍类型？

因为**"抛异常"和"返回可处理结果"是两件完全不同的事**。

|      | `Command.from_dict` 报错                 | 校验器返回 `INVALID_TASK_COMMANDS`                        |
| ---- | ---------------------------------------- | --------------------------------------------------------- |
| 后果 | 抛异常 → 请求 500 → **用户什么也看不到** | 引擎收到 `valid=False` → **走澄清流程，用户得到一句追问** |
| 性质 | 程序错误处理                             | 输入校验                                                  |

**同样是异常输入，一个变成崩溃，一个变成澄清**——这就是这道防线的价值。

再加上一层：**边界处必须校验**。`TaskHandler` 依赖"commands 一定是这四种之一"这个不变量，这个不变量在校验层被显式保证，下游才敢放心写。如果将来有人绕过 `Command.from_dict` 直接构造 `TurnPlan`（新增输入路径、测试里手工构造），这道防线还在。

这就是笔记里点明的"**防御性编程——不假设上游一定干净**"。

### Q3. 场景 A 和场景 C 都是"流程中点了订单"，为什么处理不同？

因为**当前流程是否还缺这个槽位**不一样。关键差异在第③步：**这个槽是不是已经填了。**

同样一次"点订单"，在退款流程的不同时刻，含义完全不同：
判定完全落在 `_flow_has_unfilled_collect_slot` 的**第③步**：

```python
if active_task.slots.get(slot_name):      # order_number 已经有值了？
    return False                          # 有值 → 不能填（场景 C）
```

- 在第一步点击：`order_number` 还没填 → 继续走到第④步 → 流程里确实有 `collect order_number` 的步骤 → 返回 `True` → **场景 A**
- 在第二步点击：`order_number` 已经填过 → 直接返回 `False` → **场景 C**

注意场景 C 返回 `False`，**不是因为"流程不需要订单号"**（流程当然需要，只是已经拿到了），而是因为"**已经有了**"。这个区分正说明模型的精确——同一个动作，在流程的前一步是 A，后一步就变成 C。

至于为什么场景 C 要"不打断"：用户已经在流程里了，粗暴打断去问"你想干嘛"会破坏流程状态；而且这次点击很可能只是顺手点的。**让流程继续等它要的东西，是代价最小的选择。**

### Q4. 为什么不直接改 `state`，要绕一圈构造 `SetSlotsCommand`？

两个理由，第二个是关键：

**① 统一入口**——下游 `TaskHandler` / `CommandProcessor` 不用区分"这个槽是打字填的还是点卡片填的"。

**② 复用流程推进逻辑**——填槽这个动作**只是流程推进的一半**。填完一个槽之后，流程不会自己停下，它还要：

```
判断 next 是什么
  → 下一个还是 collect 且已有值？继续往下跳
  → 下一个是 action？执行它
  → 生成对应回复（继续问下一个槽，或给出结果）
```

这套逻辑已经为文本消息实现在 `TaskHandler` 里了。如果对象消息直接 `state.set_slots(...)` 就结束，**流程会卡在中间**——用户点了卡片，却看不到下一步。

转成 `SetSlotsCommand` 交给同一个 `TaskHandler`，就能直接复用，**不必在对象处理这条路径里把整套流程推进重写一遍**。

再往上一层看，这是**归一化（适配器）思路**：把多种输入形式统一成一种内部表示，让下游只处理一种情况。以后要加新的输入形式（语音、图片选择、批量选择），只要能转成 `Command`，下游一行都不用改。

### Q5. 为什么坚持"先写死基础话术，再让 LLM 润色"？

**只用 LLM 生成，会踩三个坑：**

| 风险                   | 后果                                                         |
| ---------------------- | ------------------------------------------------------------ |
| **LLM 调用失败或超时** | 澄清本来就是兜底路径，兜底路径自己再没有兜底，用户就直接收不到任何回复 |
| **可能跑偏**           | 让 LLM 从零决定"该问什么"，它可能漏掉关键引导（用户点的是订单，却问"你想了解商品吗"） |
| **可能新增幻觉**       | 自由生成时可能加出系统并不支持的能力——"要不要帮你投诉？"     |

而两段式的设计把每个风险都压住了：

- **① 用 if-else 精确映射 reason → 话术**，这一步是**确定性的、可测的**，保证话术内容一定正确
- **② LLM 只做"改写得自然一点"**，并且有明确禁令：*"不要扩写，不要新增信息，不要改变澄清意图"*

**下限由规则保证，上限由 LLM 提升。**

------

这五道题其实都在讲同一个哲学——**确定性打底，LLM 增强**：

| 问题 | 确定性的部分                               | LLM 的部分                  |
| ---- | ------------------------------------------ | --------------------------- |
| Q1   | 校验器判断"对不对"                         | 交给 responder 决定"怎么说" |
| Q2   | 类型白名单硬性校验                         | —（这是纯确定性的一道墙）   |
| Q3   | `_flow_has_unfilled_collect_slot` 四步判断 | —（对象消息全程不经 LLM）   |
| Q4   | `SetSlotsCommand` 归一化                   | —（复用已有的推进逻辑）     |
| Q5   | **基础话术（规则保底）**                   | **润色（提升体验）**        |

这和笔记05 里 `TurnPlanner` 的设计是同一个思路的两面：

- `TurnPlanner`：给 LLM **划范围**（`available_flows` / `knowledge_intents`）+ 校验**兜底**
- `ClarifyResponder`：给 LLM 一个**正确底稿** + **约束禁令**

**都是让 LLM 做它擅长的事（理解、表达），把"对错"牢牢攥在代码手里。** 这也正是笔记01 那句核心命题的落地：

> 如何用工程化的方式驯服 LLM 的不确定性，保证业务结果稳定可控？

---

下一站 **笔记07（TaskHandler 与 CommandProcessor）**——四条输入路径（文本 task、对象 A/C 场景、澄清回路）最终都汇到那个 `handle(commands, state)`，但它在 04/05/06 里一直是 `return [BotMessage(text="任务已经处理")]`。07 会真正展开四种 `Command` 各怎么执行。

要继续吗？

## 笔记07 自测题

1. `commands` 传空列表时，`TaskHandler` 里会发生什么？这和笔记06 的哪个场景对应？
2. `start_flow` 的分支②和③配对的是**同一个** `InterruptedSystemContext`，为什么它们能共用？
3. `start_flow` 分支④（无活跃任务 + 目标在暂停栈）激活的是 `Resumed` 而不是 `Started`——用户看到的话有什么不同？
4. `resume_flow` 的"回退"具体在防什么问题？为什么调用**无参**的 `resumed_active_task()` 就能完成回退？
5. `_handle_set_slots` 在没有活跃任务时选择"什么都不做"，为什么不报错、也不提醒用户？

笔记07 的五道题：

---

### Q1. `commands` 传空列表时会发生什么？对应哪个场景？

```python
def run(self, commands, state, flows):
    for command in commands:      # 空列表 → 循环一次都不进
        self._apply(command, state, flows)
```

**state 完全不变**，然后 `TaskHandler` 直接进入阶段 2 推进流程。

对应笔记06 的**场景 C**——用户在一个流程中（比如正在收集 `refund_reason`）点了订单卡片，但这个对象对当前槽位没用。`_handle_object_message` 走到 `if state.active_task is not None:` 分支时，传的正是 `commands=[]`。

效果就是"**不打断、让流程继续**"：不改状态，但流程继续问它要的东西。

这个设计漂亮的地方在于——**"什么都不做"不需要任何特殊分支**。空列表是合法输入，遍历自然跳过，代码里连一个 `if not commands: return` 都不用写。

### Q2. 分支②和③为什么能共用同一个 `InterruptedSystemContext`？

因为 `InterruptedSystemContext` 要说的那句话，**只需要两个信息**：

```yaml
text: "好的，我们先把{{ context.interrupted_flow_name }}放一放，先处理{{ context.started_flow_name }}。"
```

| 分支 | 内部动作            | 用户听到的                |
| ---- | ------------------- | ------------------------- |
| ②    | 打断 A + **新建** B | "先把 A 放一放，先处理 B" |
| ③    | 打断 A + **恢复** B | "先把 A 放一放，先处理 B" |

**在用户听觉上这是同一件事。** 差别只在内部状态：② 的 B 是全新的（`step_id` 从头），③ 的 B 从暂停栈恢复（带着旧 `step_id` 和 `slots`）。

但这个差别**用户不需要在这句话里知道**——B 是新的还是接续的，下一句回复自然会体现。

所以规律是：**过场白的选择取决于"用户能感知到的处境差异"，而不是内部实现差异。** 如果为 ②③ 各写一套话术，反而要用户去理解系统内部的实现细节。

### Q3. 分支④激活 `Resumed` 而不是 `Started`，用户看到什么不同？

差别不只在措辞，**第二句也完全不同**：

|        | 分支④（之前做过一半）                | 分支⑤（全新）                    |
| ------ | ------------------------------------ | -------------------------------- |
| 第一句 | "好的，我们**继续**刚才的退款申请。" | "好的，我们**先处理**退款申请。" |
| 第二句 | "请简单说一下**退款原因**。"         | "请告诉我你的**订单号**。"       |

用户能感知到两点：

1. **"继续" vs "先处理"** ——提示了这是接着做还是新开始
2. **问的内容不同** ——分支④直接从 `refund_reason` 问起（`order_number` 已经在 `slots` 里了），分支⑤从 `order_number` 问起

如果分支④错误地激活 `Started`，用户会听到"我们先处理退款申请"，然后系统直接问"请说一下退款原因"——**话术和实际行为对不上，用户会疑惑"订单号你怎么不问了"**。

所以这个配对不是装饰：**它保证系统说的话和第 2 阶段实际做的事一致。**

### Q4. `resume_flow` 的"回退"在防什么？

**防的是"当前任务白白被挂起"。** 问题出在两步操作之间：
**如果不回退会怎样**：第 ① 步之后 `active = 空`，A 被挂在栈里。用户什么都没办成，**手里原本的事却消失了**。

**为什么无参调用就能回退**：

```python
state.interrupted_active_task()                    # = push：active_task 压到栈顶
if not state.resumed_active_task(target_flow_id):  # 指名查找，失败
    state.resumed_active_task()                    # = pop：弹栈顶
```

关键在于 `paused_tasks` 是**栈（LIFO）**，而 `interrupted_active_task()` 是 **push 到栈顶**。所以栈顶==**刚刚被压进去的那个 A**。无参恢复 = 弹栈顶 = 把 A 拿回来。

这个回退之所以成立，靠的是两个操作的**对称性**：

| 操作                        | 效果                          |
| --------------------------- | ----------------------------- |
| `interrupted_active_task()` | push `active_task` 到栈顶     |
| `resumed_active_task(None)` | **pop 栈顶** 到 `active_task` |

**先 push，失败后立刻 pop，一压一弹正好抵消。**

这是"要么全做、要么撤销"的思路在**没有事务机制的纯内存操作**里的落地。它给了一个通用提醒：**代码里一旦出现"先改状态 A、再改状态 B"的序列，就要提前想清楚"B 失败时 A 怎么办"。**

### Q5. `_handle_set_slots` 没活跃任务时为什么什么都不做？

```python
def _handle_set_slots(self, command, state):
    if state.active_task:
        state.set_slots(command.slots)
```

三层理由：

**① 本来就没有地方可填。** `state.set_slots` 内部操作的是 `active_task.slots`。没有活跃任务，就没有容器。硬填进一个不存在的任务里毫无意义。

**② 这不是用户的错，是对话的噪声。** 什么情况会走到这里？用户随口说了句带数字的话（"我用了一个月了"）被 LLM 误判成 `set_slots`；或者流程结束后才补充信息。这些都是**正常的对话噪声**，不是需要报告给用户的错误。

**③ 报错或提醒反而更糟。**

| 做法                             | 后果                                                         |
| -------------------------------- | ------------------------------------------------------------ |
| 抛异常                           | 请求 500，用户什么都收不到                                   |
| 生成提示"你没有正在进行的任务哦" | 用户一脸困惑（他本来就只是随口说句话），还白占一轮对话       |
| **静默跳过**                     | 阶段2 照常跑；没有活跃任务自然没有流程可推，本轮会走到一个"无话可说"的状态，由后面的兜底接住 |

一句话：**静默失败是这里最合适的行为。**

这跟笔记04 的 `load_state` 是同一个思路的两面：

|              | 边界情况     | 处理                             |
| ------------ | ------------ | -------------------------------- |
| `load_state` | 新用户查不到 | **内部消化，返回可用的空 state** |
| `set_slots`  | 没有活跃任务 | **内部消化，什么都不做**         |

**都不让调用方/用户为内部细节买单。**

---

这五道题分别对应了笔记07 里五个层次的设计：

- **Q1 空命令** —— "什么都不做"是**合法且有语义**的输入（对应场景 C 的"不打断"）
- **Q2 过场共用** —— 抽象的依据是**"用户能感知的差异"**，不是内部实现差异
- **Q3 Resumed vs Started** —— 系统说的话必须和**实际做的事一致**（继续 vs 从头）
- **Q4 回退** —— 多步状态修改必须考虑**中途失败怎么办**，push/pop 的对称性提供了免费的回滚
- **Q5 静默跳过** —— 噪声输入**内部消化**，不惊动用户

其中 Q4 是这一节最值得记住的：**它把"事务思维"带进了纯内存操作。** 后面笔记09 的 `FlowExecutor` 里还会反复看到这个模式——**推进流程时先改 `step_id`，如果 action 执行失败，同样要考虑状态要不要回退。**

---

下一站 **笔记08（Action 实现）**，它是笔记09 `FlowExecutor` 的前置零件——`action_response` 怎么渲染模板变量、`action_listen` 怎么表达"等用户"、三个自定义 action 怎么查订单/物流/商品。

要继续吗？

## 笔记08 自测题

1. `Action` 为什么只返回 `ActionResult` 而不直接修改 `state`？这样设计带来什么好处？
2. `action_lookup_order_status` 返回 `slot_updates`，`action_recommend_similar_products` 返回 `messages`——为什么要区分这两种风格？
3. `ActionResponse._render_text` 里 `context=state.active_system_task or state.active_task` 这个 `or` 是什么意思？它解释了 `system_flows.yml` 里的哪个写法？
4. `rephrase` 和 `generate` 共用 `_call_llm`，靠什么区分两种模式？
5. `register_custom_actions` 里 `if obj.__module__ != module.__name__: continue` 这一行在防什么？

笔记08 的五道题：

---

### Q1. 为什么 Action 只返回 `ActionResult`、不直接改 `state`？

四个好处：

| 好处           | 说明                                                         |
| -------------- | ------------------------------------------------------------ |
| **副作用集中** | 所有对 state 的写入都发生在 FlowExecutor **一处**，而不是散落在 5 个 action 里。审计"谁会改 state"，只看一个地方 |
| **易测试**     | 给一个 state + kwargs，断言返回的 `ActionResult` 就够了，纯函数式测试，不用检查 state 被改成什么样 |
| **可拦截**     | FlowExecutor 能在写回前做统一处理——将来加"槽位值校验""审计日志""失败重试"，都只改一处。如果 action 自己写 state，这些横切逻辑要在每个 action 里重写 |
| **时序可控**   | 多个 action 的产出何时落地，由调用方统一决定                 |

一句话：**Action 是"纯计算 + 外部查询"，只产生"变更意图"，落地时机由调用方掌握。**

这和前面几节是同一个套路：

- 笔记04：`engine` 是纯计算，**不碰数据库**
- 笔记06：`validator` 只判断，**不生成话术**
- 笔记08：`action` 只产出意图，**不改 state**

**都是把"决定"和"执行"分开。**

### Q2. 为什么区分 `slot_updates` 和 `messages` 两种风格？

因为这两类 action 干的是**不同性质的活**：

|        | 查询类                                               | 直接回复类                     |
| ------ | ---------------------------------------------------- | ------------------------------ |
| 做什么 | **获取数据**                                         | **生成回复**                   |
| 产物   | `slot_updates`（数据）                               | `messages`（话术）             |
| 为什么 | 数据是"中间结果"，**怎么说取决于后面哪个 step 用它** | 没有中间数据要留给别人，直接说 |

拆开的具体收益：

1. **数据可复用**——`order_status` 和 `order_summary` 两个槽可以被多个 step 使用（状态播报、摘要播报可以是两套不同话术）。如果查询 action 直接生成回复，数据就用完即弃。
2. **话术与数据解耦**——改话术只动 YAML 的 `text` 模板，改接口只动 Python，互不干扰。
3. **分工清晰**——查询 action 不关心"用户想听什么语气"，回复 action 不关心"数据从哪来"。
4. **可组合**——`action_lookup_logistics` 能被任意流程复用，只要配一个自己的 `action_response`。

反过来说 `action_recommend_similar_products` 用 `messages` 就很合理：它**没有需要留存的中间数据**，而且话术是动态拼出来的（带商品名），放 Python 里比放 YAML 模板更自然。

### Q3. `context=state.active_system_task or state.active_task` 是什么意思？

这是"**系统流程优先**"的取值策略：有系统过场时 `context` 指向过场，否则指向业务任务。

这和笔记02 里 `current_active_task()` 的 `return self.active_system_task or self.active_task` **完全一致**——同一个优先级规则，两处实现。

**那个 `or` 到底解决了什么**：
所以这一个 `or`，就解释了笔记03 里 `system_flows.yml` 那四个流程为什么能写出 `{{ context.started_flow_name }}`——**因为 `context` 指向的是 `StartedSystemContext`，它才带 `started_flow_name` 字段。**

### Q4. `rephrase` 和 `generate` 共用 `_call_llm`，靠什么区分？

靠**传不传 `rendered_text`**——用默认参数 `rendered_text: str = ""` 实现：

```python
# rephrase：先渲染 text 得到底稿，再传进去
rendered_text = self._render_text(text, state)
message = await self._call_llm(prompt_text, state, rendered_text)

# generate：不渲染 text，直接调
message = await self._call_llm(prompt_text, state)
```

而在 `_call_llm` 内部，它被塞进 prompt 变量 `current_response`：

| 模式       | `current_response` 的值 | LLM 在做什么                   |
| ---------- | ----------------------- | ------------------------------ |
| `rephrase` | 渲染好的**底稿**        | 在**一个已经正确的话术上润色** |
| `generate` | 空字符串                | **从零生成**                   |

好处是两种模式的"调 LLM 那部分"（模板构建、history 拼装、chain 调用）**完全复用**，不会出现两份重复的代码。

顺带看一层本质：**rephrase 和 generate 的真正差别是"要不要一个下限"。**

- `rephrase` 有底稿兜底 → 适合"必须在正确性上有保障"的场景
- `generate` 没有兜底 → 适合"纯粹自由发挥"的场景

这和笔记06 的 `ClarifyResponder` 两段式是**同一个思想**：有个正确底稿，LLM 只负责说得更好听。

### Q5. `obj.__module__ != module.__name__` 在防什么？

防**重复注册**。

`inspect.getmembers(module, inspect.isclass)` 会把模块里**所有可见的类**都吐出来，**包括 `import` 进来的**。

典型翻车场景：`lookup_logistics.py` 里如果要复用订单查询的逻辑，可能写了：

```python
from atguigu.task.action.custom.lookup_order_status import LookupOrderStatusAction
```

这时 `inspect.getmembers(lookup_logistics_module)` 会把 `LookupOrderStatusAction` 也算进来。**如果不加过滤，它就会被第二次注册。**

而 `ActionRegistry.register` 是 `self._actions[action.name] = action`——重复注册会**用后一个实例覆盖前一个**。这里两个实例功能一样，暂时看不出问题；但如果某个 action 有内部状态（缓存、计数器），被换成新实例就丢了。更麻烦的是**扫描顺序不确定**，行为变得不可预测。

`obj.__module__` 是"这个类**被定义在哪**"，`module.__name__` 是"当前**扫描的模块**"。只有两者相等，才说明这个类**是真正在这个模块里定义的**。

这跟笔记03 里 `if "if" in link_dict` 那种"只处理符合预期的项"是同一个习惯：**凡是"扫描 + 批量注册"的操作，永远要加过滤条件。** 自动发现很方便，但必须把"发现什么"定义清楚——过滤写松了，就会出现重复注册或误注册。

---

这五道题串起来，说明了笔记08 的一个核心立场——**把"数据"和"表达"、"决定"和"执行"分开**：

| 问题 | 分开的是什么                                            |
| ---- | ------------------------------------------------------- |
| Q1   | action **产生意图** vs 调用方**执行落地**               |
| Q2   | 查询类的**数据** vs 回复类的**话术**                    |
| Q3   | **系统上下文** vs 业务上下文（谁该拥有 `context`）      |
| Q4   | **底稿**（规则保证）vs **润色**（LLM 增强）             |
| Q5   | **框架的便利**（自动发现）vs **框架的严谨**（过滤条件） |

其中 Q1 最值得记住：**"不直接改状态"这个约束，是整个项目里反复出现的设计基调。** 从笔记04 的引擎、笔记06 的校验器、到笔记08 的 action，都在做同一件事——

> **让能产生副作用的组件尽可能少，让纯计算的部分尽可能多。**

原因很实际：副作用越集中，越容易测试、越容易审计、越容易在将来加横切逻辑。

---

下一站 **笔记09（FlowExecutor 执行器）**。它是这条链的最后一环，会把笔记08 全程标注的 `# TODO` 全部补齐：

- 谁构造 `ActionCall` 并交给 `ActionRunner`
- `slot_updates` 什么时候写回 `state`
- `action_listen` 怎么让循环 `break`
- `next` 的静态/条件跳转怎么求值
- 流程走完怎么推进 `step_id`、怎么判断 `end`

学完它，**"我要退款" → "退款申请已提交" 这条链路就真正闭环可跑了**。

要继续吗？

## 笔记09 自测题

### 五个自测题

1. 为什么要把"推进 step"和"执行 action"拆成两层循环？混在一起会怎样？
2. 内层循环里，`current_active_task()` 返回 `None` 时为什么可以直接返回 `action_listen`？这覆盖了哪两种情况？
3. `_run_end_step` 为什么要区分"清系统任务"和"清业务任务"？
4. `_run_action_step` 里如果先构造 `ActionCall` 再推进 `step_id`，会发生什么？
5. `_try_to_fill_collect_slot_focused_object` 解决的是什么场景？它和笔记06 对象消息的"场景 A"有什么不同？

笔记09 的五道题：

---

### Q1. 为什么拆两层循环？混在一起会怎样？

**核心原因：两者是不同粒度的操作。**

|              | 内层（推 step）            | 外层（执行 action）    |
| ------------ | -------------------------- | ---------------------- |
| 性质         | 纯状态推进                 | 带 I/O（调接口 / LLM） |
| 一次能做多少 | **可以连推好几步**（7 步） | 一次只做一件           |
| 会不会失败   | 基本不会                   | 可能失败/超时          |

**混在一起会怎样：**

1. **每次迭代都要做类型判断**——单层循环里每一步步都要问"这是推还是执行？"。而现在这个判断在内层是**已知的**：只有 action step 才退出。
2. **"连推好几步"变得别扭**——内层能一口气推完 `start → collect(有值) → collect(有值) → action`；单层循环里每一小步都要回到循环头重新判断，还得额外维护"本轮是推还是执行"的状态。
3. **退出条件变复杂**——现在只有一个信号 `action_listen`；混起来要同时处理两套终止逻辑。
4. **职责边界模糊**——`advance_until_action` 这个名字就说明了一切：**"一直推到需要 action 为止"**。这是一个清晰、可独立测试的能力。

再补一层：**拆分让 `advance_until_action` 成为一个可复用的公共方法**（笔记 9.2 节专门讲了它为什么不加下划线）——外部可以单独调它"只推进流程、不执行 action"。混在一层里，这个能力就暴露不出来。

一句话：**内层是纯计算，外层带副作用**——和笔记04 里"引擎纯计算、Service 管 I/O"是同一个分层思路。

### Q2. `current_active_task()` 返回 `None` 时，为什么可以直接返回 `action_listen`？

因为**"没事可做" 和 "等用户输入" 在这套模型里是同一件事**。

两种典型情况：

1. 业务流程刚跑完 `end`，`active_task` 被清空，又没有系统过场
2. 用户刚启动会话，还没开任何任务

这两种状态下系统确实**没话要说、没事要做**——自然就该把控制权交还给用户。

**为什么这是好设计**：如果加一个特殊的"结束"分支（返回 `None` 或抛异常），上层就要区分"正常结束"和"异常结束"。而现在**所有"无事可做"都被归一化成同一个信号**，外层循环只有一条退出路径。

这也是为什么 `action_listen` 要设计成**一个 action**而不是布尔标志——**它让"我推不动了"这个状态能被当作正常的 action 返回值**，类型统一，不需要额外分支。而它本身 `return ActionResult()`，**价值完全在"名字"上**：它承担的是"信号"职责，不是"行为"职责。

### Q3. `_run_end_step` 为什么要区分清系统任务和清业务任务？

因为**系统流是一个"临时叠加层"，业务任务还在它下面**。

| 当前         | 清谁                      | 之后                                                    |
| ------------ | ------------------------- | ------------------------------------------------------- |
| 系统过场跑完 | 只清 `active_system_task` | `current_active_task()` 返回**业务任务** → 继续推进业务 |
| 业务任务跑完 | 清 `active_task`          | 返回 `None` → 内层返回 `action_listen` → 本轮结束       |

**如果一律清业务任务**：系统过场结束时会把退款流程也清掉——用户刚说完"我要退款"，任务就没了。**致命。**

**如果一律只清系统任务**：业务流程跑到 `end` 时 `active_task` 永远清不掉 → 内层永远有任务可推 → 死循环，而且下一轮用户说任何话都会被塞进那个已跑完的流程里。

所以这个 `if state.active_system_task:` 判断，本质是在回答：**"现在结束的是叠加层，还是底下那件事？"**

这也间接说明了 `current_active_task()` 为什么必须是 `active_system_task or active_task`——**"系统优先"的规则和"系统是叠加层"的设计是一套的。**

### Q4. 如果先构造 `ActionCall` 再推进 `step_id`，会发生什么？

**死循环，而且用户会收到无数条重复消息。**

内层的逻辑是：

```python
action_call = self._run_step(state, step, flows)
if action_call is not None:
    return action_call          # 退出内层
```

外层执行完 action 后，**又回到内层开头**，重新：

```python
step = flow.get_step_by_id(current_active_task.step_id)
```

如果 `step_id` 没被推进 → `step` 还是同一个 action step → 又返回同一个 `ActionCall` → 外层又执行一遍 → 无限循环。每条结果都 `messages.extend(...)`，最终把内存撑爆。

**为什么"推进"必须在内层返回前做，而不是外层执行完再做**：

- 放在**外层**（执行完再推），action 抛异常时 `step_id` 就不会推进——看似"符合回退直觉"，但会导致**同一轮内状态不一致**。
- 放在**内层返回前**，语义更单纯：**"这个 action 我已经交出去了，我的责任就是把它标记为已处理。"** 至于执行成功与否，那是外层的事。

这其实是笔记07 那个"先 interrupt 再 resume、失败回退"的**反面**——那里需要回退，这里不需要。区别在于：**推进 `step_id` 是个幂等的标记动作**（只是记个号），而挂起/恢复任务是有真实语义的状态迁移。

### Q5. `_try_to_fill_collect_slot_focused_object` 解决什么场景？和场景 A 有何不同？

**解决的场景：用户"先点卡片、后说意图"（跨 turn）。**

```
Turn 1: 用户点了订单卡片 O1001   →  focused_object = O1001
Turn 2: 用户说"查物流"           →  start_flow(logistics_tracking) → collect order_number
```

如果不做自动补槽，用户已经点过订单了，进流程后还要被问"请告诉我你的订单号"——**"我刚不是点了吗？"**

依据是 **`focused_object` 跨 turn 持久化**（只有 session 过期才清）。

**和场景 A 的区别**：
**两个关键差异：**

|              | 自动补槽（笔记09）                                          | 场景 A（笔记06）                                 |
| ------------ | ----------------------------------------------------------- | ------------------------------------------------ |
| **时机**     | 点卡片**之后的某一轮**，流程开跑时                          | 点卡片**当轮**，流程已在跑                       |
| **判断角度** | 从**槽位**出发："这个槽要的东西，`focused_object` 里有吗？" | 从**点击**出发："这个对象能填当前流程缺的槽吗？" |
| **实现**     | collect step 里直接 `state.set_slots(...)`                  | 转成 `SetSlotsCommand` → 走 `CommandProcessor`   |
| **判断方法** | 检查 `focused_object.type` 是否匹配 `slot_name`             | `_flow_has_unfilled_collect_slot` 四步判断       |

**为什么两条路都要有**——因为用户的真实操作顺序是自由的：

| 情况                     | 只有场景 A                 | 只有自动补槽                                             |
| ------------------------ | -------------------------- | -------------------------------------------------------- |
| ① 先点卡片，后说"查物流" | ❌ 进流程后还会被追问订单号 | ✅ 自动补槽接住                                           |
| ② 流程问订单号时点卡片   | ✅ 场景 A 接住              | ❌ 白白浪费——要等下一轮才可能补上，而那时流程可能已经错过 |

**一句话**：场景 A 是"**点击时的入口**"，自动补槽是"**进流程时的兜底**"。一个主动、一个被动，合起来才让用户**不必重复提供已经给过的信息**。

---

## 一句话回顾

这五道题分别对应了 `FlowExecutor` 的五个设计决策：

| 问题 | 决策            | 一句话                                               |
| ---- | --------------- | ---------------------------------------------------- |
| Q1   | 两层循环        | **纯计算和带副作用分开**——粒度不同，退出条件才能唯一 |
| Q2   | 空任务 → listen | **"没事可做"归一化成"等用户输入"**，退出路径只有一条 |
| Q3   | end 分两种      | **系统流是叠加层**，结束它不等于结束底下那件事       |
| Q4   | 先推进再返回    | **交出去之前先标记为已处理**，否则原地打转           |
| Q5   | 自动补槽        | **用户的真实操作顺序是自由的**，两条路都得有         |

其中 **Q1 和 Q2 是结构性的**，决定了整个执行器的形状；**Q3 和 Q4 是两个具体的陷阱**，不注意就会出致命 bug（任务被误清 / 死循环）；**Q5 是体验层面的打磨**，让系统显得"记得住事"。

回头再看整条链路，你会发现一个反复出现的模式——**每个组件只做一件事，把"不知道"和"不该管"的部分推给别人**：

- `TurnPlanner` 只管理解，不管执行
- `Validator` 只管判断，不管怎么说
- `CommandProcessor` 只管改状态，不管后续
- `Action` 只管产出，不管落地
- `FlowExecutor` 只管推进，不管 action 内部
- `ClarifyResponder` 只管说话，不管为什么澄清

**每一层都很薄，但串起来能跑通一个完整的业务。** 这就是笔记01 那句"用工程化的方式驯服 LLM 的不确定性"在架构层面的答案。

---

下一站 **笔记10（信息检索与闲聊）**——把 `KnowledgeHandler` 和 `ChitchatHandler` 补上，三条轨道就全通了。之后笔记11 收尾会话历史。

要继续吗？

## 笔记10 自测题

### 五个自测题

1. 为什么要把 `activate` 拆成 `handler` 和 `responder` 两层？`TaskHandler` 里有没有对应的结构？
2. `KnowledgeProvider` 只有一个抽象方法 `retrieve(state)`，为什么不需要传"用户问了什么"？
3. `FAQProvider` 现在返回"未检索到相关问题"，这算不算没做完？它的价值在哪？
4. `_get_provider_ids_by_intents` 里的 `list(set(...))` 在防什么具体情况？
5. `OrderAPIProvider` 为什么用 `asyncio.gather` 而不是连续两个 `await`？

### Q1. 为什么拆 `handler` / `responder` 两层？`TaskHandler` 里有对应结构吗？

**有，而且完全同构。**

|      | 调度层             | 执行层                                               |
| ---- | ------------------ | ---------------------------------------------------- |
| 闲聊 | `ChitChatHandler`  | `ChitChatResponder`（调 LLM）                        |
| 知识 | `KnowledgeHandler` | `KnowledgeResponder` + providers                     |
| 任务 | `TaskHandler`      | `CommandProcessor` / `FlowExecutor` / `ActionRunner` |

拆开的具体好处：

1. **handler 不需要知道 prompt 长什么样**。它的职责纯粹是"从 state 里取原料"——`user_message` 和 `recent_turns`。prompt 模板、chain 组装、结果包装全在 responder。
2. **改 prompt 不牵连调度**。换模板、加 few-shot、换模型——只动 responder，handler 一行不改。
3. **可测试**：handler 可以 mock responder 单独测；responder 可以单独测 prompt 渲染。

再往上抬一层看：三个 handler 是**同一层的三个兄弟**，`DialogueEngine` 甚至可以说是"handler 的 handler"——它也只负责调度。

**每一层都很薄，但职责单一。**

### Q2. `retrieve(state)` 为什么不传"用户问了什么"？

这个问题问得好——直觉上检索应该要 query 啊？

**因为"检索目标的定位"已经编码在 state 里了。**

| Provider             | 实际用什么定位            | 性质               |
| -------------------- | ------------------------- | ------------------ |
| `ProductAPIProvider` | `state.focused_object.id` | **按 ID 精确查询** |
| `OrderAPIProvider`   | `state.focused_object.id` | **按 ID 精确查询** |

用户点了哪个商品，那个商品**就是**检索目标——不需要再从自然语言里解析一遍。

**那用户的问题文本呢？** 它在 `KnowledgeResponder` 里用：`{{ user_message }}` 进 prompt，用于**生成回复**，而不是用于检索。

**FAQ / RAG 将来确实需要 query**——但它们也能从 state 里拿到：`state.pending_turn.user_message` 就在里面。

所以接口设计的智慧是：**`retrieve(state)` 是"给你整个上下文，你按需自取"，而不是"我猜你需要什么，挑给你"。**

- API provider 取 `focused_object`
- FAQ / RAG 将来取 `pending_turn.user_message`
- 如果某个 provider 需要对话历史来消歧（"它"指哪个），也能从 `state.current_session().turns` 拿

**好处是接口只有一个参数**——新增 provider 不需要改签名。如果写成 `retrieve(query, focused_object, history, ...)`，将来加一种信息就要改所有实现。

### Q3. `FAQProvider` 返回占位内容算不算没做完？

**不算，这是有意的"契约优先"设计。** 四层价值：

1. **整条链路可以先跑通**——`refund_policy` 意图 → `faq.default` → chunk → prompt → 回复。**端到端能验证**，而不是"等 FAQ 库接好才能测"。
2. **接口契约被固定下来**——`provider_id` + `async def retrieve(state) -> list[KnowledgeChunk]`。将来接 ElasticSearch，只要保持签名，`KnowledgeHandler` / `Responder` / 提示词 / `intents.py` 的映射**全都不用动**。
3. **降级行为是对的**——返回"未检索到相关问题"，配合提示词里"信息不足时坦诚告知"，LLM 会**诚实说"我暂时查不到"**。比返回空然后让 LLM 编一个答案好得多。
4. **让"哪些能力没做"变得可见**——任何人看到这个返回值都知道"FAQ 检索待接入"。**占位实现是一种沟通方式。**

和笔记04 的占位引擎、笔记08 的占位推荐 action 是同一个手法。

### Q4. `list(set(...))` 在防什么？

防**同一个 provider 被查两遍**。

用户问"退款和退货政策有什么不同？"→ `intents = ["refund_policy", "return_policy"]`。查 `KNOWLEDGE_INTENTS`：

```python
"refund_policy":  provider_ids=["faq.default", "rag.default"],
"return_policy":  provider_ids=["faq.default", "rag.default"],
```

不去重的话 → `["faq.default", "rag.default", "faq.default", "rag.default"]`，**每个 provider 被 `retrieve` 两次**。

后果：
1. **浪费 I/O**——API provider 白调两次接口（多一倍延迟、多一倍配额）。
2. **chunks 出现重复内容**——`"\n\n".join(...)` 后 prompt 里有两份一模一样的资料，浪费 token，还可能让 LLM 误以为"这条信息被特别强调了"。

一个观察：**去重的边界应该画在"provider"这一层，而不是"intent"那一层。** 多个不同意图指向同一个数据源是正常的；但同一个 provider 在一次回复里只该被调用一次。

（小提醒：`list(set(...))` 会打乱顺序。这里无所谓；但如果将来有优先级需求，该改用 `dict.fromkeys()` 保序去重。）

### Q5. 为什么用 `asyncio.gather`？

因为两个请求**互不依赖**。
**为什么能并发？** 因为是 **async I/O**——`await` 在等网络响应时会**让出事件循环**，另一个协程可以去发它的请求。两个等待**重叠**了，而不是前后排队。

判断标准很简单：

| 情况                    | 做法             |
| ----------------------- | ---------------- |
| 两个 await **互不依赖** | `asyncio.gather` |
| 后一个要用前一个的结果  | 必须串行         |

**一个值得留意的不一致**：这里两个 `_fetch_*` 内部**没有 try/except**——接口挂了会直接抛异常炸掉整个知识轨道。

而笔记08 的 `shared.py` 里有兜底：

```python
async def fetch_order(order_id):
    try:
        ...
    except Exception:
        return None      # ← 优雅降级
```

**同一个项目里，两处调接口的容错策略不一致**：Action 的 fetch 有降级，Provider 的 fetch 没有。知识轨道遇到接口抖动时会直接 500，而不是给用户一句"暂时查不到"。这是可以顺手补上的地方。

---

# 笔记11 自测题

### Q1. 为什么后端还要返回 `session_id`？对分割线有帮助吗？

**对"插入分割线"这个需求，`session_id` 没有直接帮助。** 分割线表达的是"页面打开前/后"，那是浏览器的状态。

**但它保留了后端会话结构。** 历史接口返回的是一组**平铺消息**：

```
原始结构：
  session-a: 查订单 / 请提供订单号
  session-b: 我要退款 / 请问退款原因
        ↓ 平铺后不带 session_id
  [查订单, 请提供订单号, 我要退款, 请问退款原因]
  ← 归属关系彻底丢了
```

加上之后能支撑：

- 按会话**折叠**（"展开更早的对话"）
- 按会话**分组**展示
- 会话级的样式（不同 session 加时间标签）
- 排查问题时看出"这条消息属于哪次对话"

**本质是个取舍**：多返回一个字段的成本几乎为零（`session_id` 本来就在 `Session` 对象里），但**事后想补就得同时改接口和前端**。所以"保留结构信息"通常比"最小返回"划算。

而且注意职责划分：**后端负责"数据归属"，前端负责"展示边界"**。后端不去替前端猜"要不要分割线"。

### Q2. 为什么不把 `session_id` 做成 `UserMessage` 的字段？

因为 **`UserMessage` 表示的是"一条消息"，不是"某次会话里的某条消息"**。

它的定位是描述**这一条消息本身**（`sender_id` / `message_id` / `type` / `text` / `object`），而"属于哪个 session"是**容器和元素**的关系，存在于外层 `Session.turns` 里。

**硬加字段会怎样：**

1. **创建时填不出来**。`begin_turn(user_message)` 在 engine 里被调用时，它关心的是"把消息装进 pending_turn"——**根本不关心 session**（session 是 `_prepare_session` 早就处理好的）。这个字段要么填不出来，要么只能填 `None`。
2. **耦合**。将来会话合并时，消息自带旧 `session_id` 就成了脏数据。
3. **污染公共模型**。`UserMessage` 被 `ActionResponse`、`HistoryBuilder.build`、`TurnPlanner` 到处使用——**它们都不需要 session 信息**。为一个调用方的需求给通用模型加字段，是典型的"为了一个场景污染公共模型"。

**正确做法**：由外层遍历 session 的代码把 `session_id` 补进去——**谁有信息，谁负责传**。

顺带一个印证：**`session_id` 出现在 schema 层（`HistoryMessage`）而不是 domain 层**，这本身就在说——**这个字段是"展示需求"，不是"业务本质"。**

### Q3. 为什么内层用 `extend` 而不是 `append`？

因为 **`turn.bot_messages` 是列表**。

```python
# ✅ extend：把列表里每个元素依次加进去 → 平铺
chat_messages.extend([render_bot_message(...) for b_msg in turn.bot_messages])

# ❌ append：把整个列表当作一个元素加进去 → 嵌套
chat_messages.append([render_bot_message(...) for b_msg in turn.bot_messages])
# 结果：[HistoryMessage(user), [HistoryMessage(bot), HistoryMessage(bot)], ...]
#                         ↑ 嵌套了一个 list
```

用错的话，返回的 JSON 里会出现嵌套数组，前端要多解一层包，`list[HistoryMessage]` 的类型标注也名不副实。

**注意为什么 user 用 `append`、bot 用 `extend`：**

|                     | 数量         | 方法     |
| ------------------- | ------------ | -------- |
| `turn.user_message` | **单个**对象 | `append` |
| `turn.bot_messages` | **列表**     | `extend` |

**这个不对称不是随意的——它精确反映了数据结构的不对称。** 而数据结构的不对称又来自业务：**用户一轮只说一句话，但系统一轮可能说好几句**（先过场、再提问）。

这正是笔记02 里"`bot_messages` 是列表"那个设计，在整个项目里被反复消费的地方。

---

## 系列自测题全清单

到这里，从 01 到 11 的自测题都讲完了。它们其实在反复训练同一套思维习惯：

| 习惯                      | 典型问题                                        |
| ------------------------- | ----------------------------------------------- |
| **区分"谁的知识"**        | `session_id` 该放 domain 还是 schema？（11-Q2） |
| **分清"数据"和"展示"**    | `divider` 为什么是前端的事？（11-Q1）           |
| **约束 LLM 而不是信任它** | 为什么给 `available_flows`？（05-Q1）           |
| **确定性优先**            | `retrieve(state)` 为什么不传 query？（10-Q2）   |
| **副作用集中**            | action 为什么只返回 `ActionResult`？（08-Q1）   |
| **边界情况内部消化**      | `load_state` 为什么给空对象？（04-Q3）          |
| **先打通再加固**          | 为什么先写占位引擎？（04-Q1）                   |

---

那三件收尾的事我随时可以接着做：

1. **代码坑清单**——把 01–09 里我标过的问题整理成一份可对照的表格（`ResponseDefinition.model` vs `mode`、`canceled_flow_id` 的逗号、`_select_next_step` 的 `"没有下一步"`、provider 缺 try/except 等）。
2. **跨笔记索引**——按概念（`session_id`、`slots`、`SystemContext`、`action_listen`…）列出它在哪些笔记里出现、各自什么角色。
3. 也可以就某一条链路**完整复盘**一次，比如"从点订单卡片到填进槽位"到底经过了几个组件。

要哪个？
