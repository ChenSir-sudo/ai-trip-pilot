"""规划图的组装：注册节点、连接边。

位置：决策层。图的形状见 docs/architecture.md §3。
可测试性：不联网、不调模型、不需要任何密钥——没有模型也能构建并跑通这张图。
不做的事：不做路由判断（那属于条件边）；不读写存储（那属于节点内部）。
"""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from src.graph.state import TripState


def extract_slots(state: TripState) -> dict:
    """把出行需求原文抽成结构化槽位。

    位置：规划图的第一个节点。
    副作用：无。不读存储、不发请求。
    幂等性：是。
    失败模式：不抛异常。

    ⚠️ 本步是桩实现：不调用模型，写死返回，只为验证「状态能流转」。
    下一步把它替换为「模型 + 严格 schema 校验」的真抽取——替换的是函数体，
    图的结构不动。
    """
    # 刻意不读 state：本步验证的是状态能否流转，不是抽取质量。
    # 换成真抽取时，这里会是 state["raw_request"] 的模型调用。
    return {
        "slots": {"destination": "上海", "days": 7},
        "missing_slots": ["出发城市", "预算上限", "同行人"],
    }


def build_graph():
    """组装并编译规划图。

    可测试性：返回的图带内存 checkpointer，可以在没有数据库的机器上直接 invoke。
    """
    builder = StateGraph(TripState)

    builder.add_node("extract_slots", extract_slots)
    builder.add_edge(START, "extract_slots")
    builder.add_edge("extract_slots", END)

    # InMemorySaver：进程内的 checkpointer，进程退出即丢失（旧版文档里叫 MemorySaver）。
    # 本步用它，是因为「澄清挂起与恢复」只需要在会话内成立。
    # 将来换成持久化实现时，改的是这一行，不是图。
    return builder.compile(checkpointer=InMemorySaver())
