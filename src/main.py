"""手工跑两个场景，看见图的分支。

位置：本步的临时入口。真正的入口是编排外壳（会话、幂等、路由），
    外壳在后续步骤实现，届时本文件退回为调试工具。
可测试性：需要 langgraph，不需要网络、不需要模型密钥。
不做的事：不做会话管理、不做幂等、不做错误处理、不落库。

为什么要跑两个场景：桩节点返回固定槽位，只会走澄清分支；把槽位直接注入
    第二个场景，才能看见「槽位齐全」那条边的真实走向。
"""

from __future__ import annotations

from src.graph.builder import build_graph

SCENARIOS: tuple[tuple[str, dict, str], ...] = (
    (
        "场景一：只给出行需求原文",
        {"raw_request": "规划一下去上海玩 7 天"},
        "demo-missing",
    ),
    (
        "场景二：槽位已齐（直接注入，模拟抽取已填全）",
        {
            "raw_request": "从杭州去上海玩 5 天",
            "slots": {"origin_city": "杭州", "destination_city": "上海", "days": 5},
        },
        "demo-ready",
    ),
)


def main() -> None:
    """跑两个场景并打印状态，用于人眼确认分支走对了。"""
    graph = build_graph()

    for title, payload, thread_id in SCENARIOS:
        # thread_id 现阶段没有实际作用，但必须带上：澄清的中断与恢复要靠它找回
        # 断点。提前固定下来，可以避免后面接入中断时改动所有调用点。
        result = graph.invoke(payload, config={"configurable": {"thread_id": thread_id}})

        print(f"\n=== {title} ===")
        print("slots         :", result.get("slots"))
        print("missing_slots :", result.get("missing_slots"))
        if "clarify_question" in result:
            print("走了哪条边    : → clarify")
            print("问用户        :", result["clarify_question"])
        else:
            print("走了哪条边    : → 继续（下一步的节点还不存在，直接结束）")


if __name__ == "__main__":
    main()
