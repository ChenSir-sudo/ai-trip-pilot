"""规划图的共享状态：所有节点之间唯一的通信载体。

位置：决策层。图的形状见 docs/architecture.md §3。
可测试性：纯数据结构，无网络、无模型调用、无存储依赖，可在 CI 中直接构造。
不做的事：不放业务判断（判断属于节点）；不放会话标识（它由 checkpointer 的
    `thread_id` 承载，重复放进状态会产生两个真相来源）。
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from src.data.types import Candidate


class MissingRequirement(TypedDict):
    """一个缺失项。

    - `keys`：满足其中**任意一个**该缺失项即被填上。单键项只有一个键；
      二选一组有多个键（用户答日期或答天数都行）。
    - `label`：问给用户的原话。

    为什么要有这个类型：这个形状原本只靠约定维系，而它在四处被构造或消费
    （`completeness` 构造、本文件声明、`clarify` 消费、命令行入口再解析）。
    类型化之后形状只有一处定义，改键名时不会再散弹式改四个文件。
    """

    keys: list[str]
    label: str


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
    # 每项是一个 MissingRequirement：keys 满足任一即可，label 是问用户的原话。
    missing_slots: list[MissingRequirement]

    # ── 澄清：覆盖型 ──
    # 记录最近一次问出去的话。问句本身随中断的 payload 返回给调用方，
    # 这里留一份是为了让「问过什么」在状态里可查。
    clarify_question: str

    # ── 候选池：合并型 ──
    # 由 build_candidate_pool 写入，内容是数据访问层的返回。挂在 merge_candidates 上，
    # 因为图里有循环、将来还会有并行扇出，同一个节点会跑多次；直接拼接会产生重复 ID，
    # 让红线 A1（按 ID 命中）失去意义。
    candidates: Annotated[list[Candidate], merge_candidates]

    # ── 数据源的能力边界与降级记录：累积型 ──
    # 例如「离线侧类别 X 不可用」「候选被截断」。**累积**，所以挂 operator.add：
    # 这些是可观测的事实，不该被后一次覆盖掉。
    # 它存在的理由与红线 R8 同源——**不得静默放宽**：取不到的那几类必须在输出里
    # 看得见，否则方案会莫名少几个地点而没人知道为什么。
    data_notes: Annotated[list[str], operator.add]
