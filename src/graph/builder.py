"""规划图的组装：注册节点、连接边。

位置：决策层。图的形状见 docs/architecture.md §3。
可测试性：不联网、不调模型、不需要任何密钥——**模型调用以参数注入**，
    所以没有 key 的机器也能构建并跑通这张图。
不做的事：不读写存储（那属于节点内部）；不决定用哪家模型（那是 src/llm 的事）。

骨架会继续长大，节点函数目前都堆在这个文件里；等它开始妨碍阅读时
（大约再有两三个节点），应当拆成独立的 nodes 模块。
"""

from __future__ import annotations

from typing import Any, Callable

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from src.data.base import DataAccess
from src.graph.candidate_pool import make_build_candidate_pool
from src.graph.completeness import find_missing_slots, slot_label
from src.graph.state import TripState

# 出行需求原文 → 槽位 dict。由调用方注入，图本身不知道它背后是不是模型。
Extractor = Callable[[str], dict[str, Any]]


def make_extract_slots(extractor: Extractor | None):
    """构造抽取节点。

    位置：规划图的第一个节点。
    副作用：取决于注入的 `extractor`——真实抽取器会发起模型请求。
    幂等性：取决于 `extractor`。
    失败模式：`extractor` 抛出的异常原样向上传播，**本节点不吞异常**。
        抽取失败时宁可让流程显式失败，也不要返回空槽位去问用户
        「出发城市是哪里」——那是用户刚刚说过的话。

    `extractor=None` 表示不抽取：状态里只保留调用方已填的槽位。
    这样图可以在没有 API key 的机器上构建与运行，测试也不会联网。
    """

    def extract_slots(state: TripState) -> dict:
        """把出行需求原文抽成结构化槽位。"""
        user_slots = state.get("slots") or {}
        raw_request = state.get("raw_request") or ""

        extracted = extractor(raw_request) if extractor else {}

        # 用户值放在后面，因此优先：用户明确填过的值不该被模型的推断改写。
        return {"slots": {**extracted, **user_slots}}

    return extract_slots


def check_completeness(state: TripState) -> dict:
    """判定槽位够不够开始规划，并把缺失项写进状态。

    位置：`extract_slots` 之后的判定节点，也是图中第一个分叉点。
    副作用：无。纯逻辑，不联网、不调模型。
    幂等性：是。
    失败模式：不抛异常。`slots` 缺失时视为「全缺」，走澄清分支。

    为什么必需槽位的规则写在代码里，而不是让模型顺带声明一份「缺失清单」：
        「哪些槽位必需」是一条确定性的业务规则，而模型返回的缺失清单只是它的
        判断。判定与生成分开是本项目的基本分工（见 docs/adr/0001），而且模型
        的判断一旦有偏差，图就会走错分支——这类错误不报错，只会静默跑偏。
    """
    return {"missing_slots": find_missing_slots(state.get("slots") or {})}


def route_after_check(state: TripState) -> str:
    """条件边：缺槽位去澄清，齐了继续。

    契约：
      副作用：无。纯函数，只读状态。
      幂等性：是。
      失败模式：不抛异常。返回值必须是 `add_conditional_edges` 映射表里的键。

    读的是上一个节点刚写下的 `missing_slots`，而不是自己重算一遍——
    重算会让「什么算完整」出现两个实现，迟早分叉。
    """
    return "clarify" if state.get("missing_slots") else "ready"


def askable_fields(pending: list[dict]) -> list[dict]:
    """把缺失项摊平成可逐个提问的字段。

    二选一的一组会摊成两个提问，此时每个提问都要带「二选一」提示：手工测试时
    发现两个提问原本共用同一个组标签（都叫「出发日期 或 天数」），看起来像要
    填两个——而实际上填任一即可。
    """
    fields: list[dict] = []
    for item in pending:
        alternatives = len(item["keys"]) > 1
        for key in item["keys"]:
            label = slot_label(key)
            if alternatives:
                label += "（与另一项二选一，填一个即可）"
            fields.append({"key": key, "label": label})
    return fields


def clarify(state: TripState) -> dict:
    """向用户提问并挂起，等答复后把答复回填进槽位。

    位置：澄清分支的节点，也是全图**唯一的挂起点**。
    副作用：**挂起等待**——依赖 checkpointer 把状态存下来，否则挂起之后无法恢复。
        函数本身不写存储、不发请求、不调模型。
    幂等性：**不幂等**。恢复时 LangGraph 会让本节点**从头重新执行**，
        `interrupt()` 之前的语句会再跑一遍（tests/test_graph.py 有一条测试专门
        固定这条框架语义）。因此 `interrupt()` 之前不允许出现任何副作用。
    失败模式：没有 checkpointer 时，首次 invoke **照常返回挂起结果、不报错**，
        但恢复时抛 `RuntimeError: Cannot use Command(resume=...) without checkpointer`。
        失败被推迟到恢复那一刻——挂起时看不出来，所以这条必须靠测试守。

    措辞遵循 docs/prd.md §6.4：一次只问一个批次，且每个问题都要让用户
    能一句话答完。
    """
    pending = state.get("missing_slots") or []
    question = "开始规划前还需要确认：" + "、".join(item["label"] for item in pending) + "。"

    # 恢复时 interrupt() 返回调用方在 Command(resume=...) 里给的答复。
    # 注意：本函数之后会被从头重新执行一遍，question 也会被重算——纯函数，无妨。
    answer = interrupt(
        {
            "question": question,
            "fields": askable_fields(pending),
        }
    )

    # 只接受问过的键。答复是**受控接口**，不是第二个入口：允许任意键写入
    # 等于给调用方开了一条绕过抽取通道、直接篡改槽位的路。
    # 代价是用户主动多说的内容（"顺便说下预算五千"）会被丢掉——那属于抽取
    # 通道的职责；将来若需要，应当把补充文本重新送给抽取节点。
    asked = {key for item in pending for key in item["keys"]}
    accepted = {key: value for key, value in (answer or {}).items() if key in asked}

    return {
        "clarify_question": question,
        "slots": {**(state.get("slots") or {}), **accepted},
    }


def build_graph(*, extractor: Extractor | None = None, data: DataAccess | None = None):
    """组装并编译规划图。

    参数：
      extractor：出行需求原文 → 槽位。`None` 表示不抽取（离线与测试用）；
          生产入口 `src/main.py` 传入真实的模型抽取器。
      data：数据访问实现。`None` 表示没有注入——**候选池节点会在被调用时明确报错**，
          而不是返回空池。两处依赖都用注入：这是让 60 多条测试在无密钥、无网络、
          无数据集的机器上跑完的原因（architecture.md §8）。

    可测试性：返回的图带内存 checkpointer，可以在没有模型密钥的机器上直接 invoke。
    注意 checkpointer 是**必需**的：图里有挂起点，去掉它就无法恢复。
    """
    builder = StateGraph(TripState)

    builder.add_node("extract_slots", make_extract_slots(extractor))
    builder.add_node("check_completeness", check_completeness)
    builder.add_node("clarify", clarify)
    builder.add_node("build_candidate_pool", make_build_candidate_pool(data))

    builder.add_edge(START, "extract_slots")
    builder.add_edge("extract_slots", "check_completeness")

    # 图中第一个条件边：判定结果是「缺」还是「齐」，决定走哪条路。
    builder.add_conditional_edges(
        "check_completeness",
        route_after_check,
        # `ready` 不再直接结束：槽位齐了就去取候选池——那是 S2 的可演示产出。
        {"clarify": "clarify", "ready": "build_candidate_pool"},
    )

    # 澄清循环：答复之后回到判定，答不全就再问一轮。
    # 这个环不会空转——每一轮都以挂起结束，必须等调用方给出答复才继续。
    builder.add_edge("clarify", "check_completeness")

    # 取完候选就结束。S3 会在这里插求解器，S2 到此为止。
    builder.add_edge("build_candidate_pool", END)

    # InMemorySaver：进程内的 checkpointer，进程退出即丢失（旧版文档里叫 MemorySaver）。
    # 它不再是「接线但闲置」——挂起点的状态存与取都靠它。
    return builder.compile(checkpointer=InMemorySaver())
