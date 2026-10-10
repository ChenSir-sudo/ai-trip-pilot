"""手工跑一次规划图，验证环境链与状态流转。

位置：本步的临时入口。真正的入口是编排外壳（会话、幂等、路由），
    外壳在后续步骤实现，届时本文件退回为调试工具。
可测试性：需要 langgraph，不需要网络、不需要模型密钥。
不做的事：不做会话管理、不做幂等、不做错误处理、不落库。
"""

from __future__ import annotations

from src.graph.builder import build_graph

# 出行需求原文。术语与 CONTEXT.md 的「出行需求」对齐。
RAW_REQUEST = "规划一下去上海玩 7 天"


def main() -> None:
    """跑一次图并打印状态，用于人眼确认字段是否按预期流转。"""
    graph = build_graph()

    # thread_id 现阶段没有实际作用，但必须带上：澄清的中断与恢复要靠它找回
    # 断点。提前固定下来，可以避免后面接入中断时改动所有调用点。
    result = graph.invoke(
        {"raw_request": RAW_REQUEST},
        config={"configurable": {"thread_id": "demo-1"}},
    )

    print("raw_request   :", result["raw_request"])
    print("slots         :", result["slots"])
    print("missing_slots :", result["missing_slots"])
    # candidates 会显示成 [] 而不是「缺失」：挂了 reducer 的字段被框架预置成
    # reducer 的空值。因此后续节点读它时不需要写 .get("candidates", [])。
    print("candidates    :", result["candidates"])


if __name__ == "__main__":
    main()
