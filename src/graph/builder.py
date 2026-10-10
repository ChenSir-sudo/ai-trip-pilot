"""规划图的组装：注册节点、连接边。

位置：决策层。图的形状见 docs/architecture.md §3。
可测试性：不联网、不调模型、不需要任何密钥——没有模型也能构建并跑通这张图。
不做的事：不读写存储（那属于节点内部）。

骨架会继续长大，节点函数目前都堆在这个文件里；等它开始妨碍阅读时
（大约再有两三个节点），应当拆成独立的 nodes 模块。
"""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from src.graph.completeness import find_missing_slots
from src.graph.state import TripState


def extract_slots(state: TripState) -> dict:
    """把出行需求原文抽成结构化槽位。

    位置：规划图的第一个节点。
    副作用：无。不读存储、不发请求。
    幂等性：是。
    失败模式：不抛异常。

    ⚠️ 本步仍是桩实现：不调用模型，返回固定槽位，只为验证结构。

    但它已经体现了一条真实约束：**只补充，不覆盖用户已给的槽位**。
    用户明确填过的值不该被模型的推断改写——真抽取也必须守这条。
    """
    user_slots = state.get("slots") or {}
    stub_slots = {"destination_city": "上海", "days": 7}
    # 用户值放在后面，因此优先。
    return {"slots": {**stub_slots, **user_slots}}


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


def clarify(state: TripState) -> dict:
    """把缺失槽位拼成一句问话。

    位置：澄清分支的终点。
    副作用：无。
    幂等性：是。
    失败模式：不抛异常。

    ⚠️ 本步是占位实现：**只生成问句就结束，不做挂起。**

    真正的澄清要能挂起、等用户答复、再从断点继续——那是中断与 checkpointer 的
    职责，单独一步做。届时这个函数会多出中断调用。
    另：按 docs/prd.md §6.4，澄清问题必须附带两个以上可执行选项；附选项同样
    属于那一步，现在只把「缺什么」讲清楚。
    """
    missing = state.get("missing_slots") or []
    return {"clarify_question": "开始规划前还需要确认：" + "、".join(missing) + "。"}


def build_graph():
    """组装并编译规划图。

    可测试性：返回的图带内存 checkpointer，可以在没有数据库的机器上直接 invoke。
    """
    builder = StateGraph(TripState)

    builder.add_node("extract_slots", extract_slots)
    builder.add_node("check_completeness", check_completeness)
    builder.add_node("clarify", clarify)

    builder.add_edge(START, "extract_slots")
    builder.add_edge("extract_slots", "check_completeness")

    # 图中第一个条件边：判定结果是「缺」还是「齐」，决定走哪条路。
    builder.add_conditional_edges(
        "check_completeness",
        route_after_check,
        {"clarify": "clarify", "ready": END},
    )
    builder.add_edge("clarify", END)

    # InMemorySaver：进程内的 checkpointer，进程退出即丢失（旧版文档里叫 MemorySaver）。
    # 注意它目前仍是**接线但闲置**：图里还没有中断点，没有东西需要恢复。
    return builder.compile(checkpointer=InMemorySaver())
