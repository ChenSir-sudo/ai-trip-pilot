"""规划图的共享状态：所有节点之间唯一的通信载体。

位置：决策层。图的形状见 docs/architecture.md §3。
可测试性：纯数据结构，无网络、无模型调用、无存储依赖，可在 CI 中直接构造。
不做的事：不放业务判断（判断属于节点）；不放会话标识（它由 checkpointer 的
    `thread_id` 承载，重复放进状态会产生两个真相来源）。
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict


def merge_candidates(old: list[dict], new: list[dict]) -> list[dict]:
    """合并候选池：按 id 去重，重复的保留先到的那个。

    这是 `candidates` 字段的 reducer。本项目里只有挂了 reducer 的字段才会
    「合并」，其余字段一律整体覆盖。

    副作用：无。纯函数，不读存储、不发请求。
    幂等性：是。对同一批输入反复调用结果不变——这是它能安全用于循环的前提。
    失败模式：候选缺少 `id` 键时抛 KeyError。这是刻意的——按红线 R2，
        没有 id 的候选不允许进入候选池；静默跳过会让它出现在方案里却无法追溯。

    为什么不用 operator.add（看起来最直观的写法）：
        图里有修复循环，取候选的节点会被执行第二次、第三次。直接拼接会让重复
        id 进入候选池，使红线断言 A1（方案中每个停靠点都能在候选池中按 ID 命中）
        失去意义——重复 id 会让「命中」这个判断变得不可信。
    """
    merged: dict[Any, dict] = {c["id"]: c for c in old}
    for candidate in new:
        # setdefault：先到的保留，后到的同 id 候选不覆盖。
        merged.setdefault(candidate["id"], candidate)
    return list(merged.values())


class TripState(TypedDict, total=False):
    """规划图的共享状态。

    字段分两类，写法完全不同；判断依据是「这个字段会不会被多个节点同时写」：

    - **裸字段（覆盖型）**：后写的整个替换先写的。节点想保留历史必须自己拼回去。
    - **挂 reducer 的字段（合并型）**：由 reducer 决定新旧值怎么合。

    `total=False` 是必需的：图启动时只需要部分字段，而 TypedDict 默认要求所有键
    都存在，否则类型检查会要求每个调用点把全部字段都填上。
    """

    # ── 输入：一次规划内不变 ──
    raw_request: str

    # ── 抽取结果：覆盖型 ──
    # 「本轮型」字段。重抽一次就该整体替换——这正是想要的语义，所以不加 reducer。
    slots: dict[str, Any]

    # ── 完整性判定结果：覆盖型 ──
    # 由 check_completeness 计算，**不是抽取节点声明的**：「哪些槽位是必需的」
    # 是一条代码里的规则（见 src/graph/completeness.py），交给模型判断会让图走错分支。
    missing_slots: list[str]

    # ── 澄清：覆盖型 ──
    # 目前只存一句问句。接入中断后，它会与挂起状态一起被持久化。
    clarify_question: str

    # ── 候选池：合并型 ──
    # 现在还没有节点写它。提前定义，是因为这个字段的 reducer 决定了后续每个节点
    # 的返回值该怎么写；等并行扇出的节点写出来再定，就要回头改动所有节点。
    candidates: Annotated[list[dict], merge_candidates]
