"""手工跑一遍，看见「真抽取 → 判定 → 挂起 → 答复 → 继续」。

位置：本步的临时入口。真正的入口是编排外壳（会话、幂等、路由），
    外壳在后续步骤实现，届时本文件退回为调试工具。
可测试性：需要 langgraph 与一个可用的 `LLM_API_KEY`——真实抽取要调模型。
    完全离线的验证走 `python -m pytest`：那里的抽取器是注入的假实现。
不做的事：不做会话管理、不做幂等、不做错误处理、不落库。

为什么这里是一段流程而不是几次独立 invoke：澄清不是一次调用，而是
    **挂起一次、恢复一次**。第一次 invoke 返回的是「问题」，第二次才把答复
    送进去——这个过程必须能被肉眼看见，否则「中断」等于没验证。
"""

from __future__ import annotations

from langgraph.types import Command

from src.graph.builder import build_graph
from src.llm.extractor import make_llm_extractor

RAW_REQUEST = "规划一下去上海玩 7 天"


def main() -> None:
    """跑两个场景：一个需要澄清（挂起 + 恢复），一个槽位已齐（不挂起）。"""
    # 真实抽取器在这里注入。构造**不联网**（延迟到第一次调用才读配置、建客户端），
    # 所以缺少 key 的报错会发生在 invoke 那一刻，而不是启动时。
    graph = build_graph(extractor=make_llm_extractor())

    # ── 场景一：信息不全，走澄清 ──
    print("=== 场景一：需求信息不全 → 挂起 → 答复 → 继续 ===")
    config = {"configurable": {"thread_id": "demo-clarify"}}

    # 第一次 invoke 会真的调一次模型，然后执行到 clarify 里的 interrupt() 挂起。
    # 注意它是**正常返回**的，不是抛异常——挂起不是失败。
    try:
        suspended = graph.invoke({"raw_request": RAW_REQUEST}, config=config)
    except Exception as exc:  # noqa: BLE001 —— 这是调试入口，要让人一眼看到原因
        print(f"抽取阶段失败：{type(exc).__name__}: {exc}")
        print("（没有配置 LLM_API_KEY 时会走到这里：cp .env.example .env 并填入 key）")
        return

    print("抽取到的槽位  :", suspended.get("slots"))
    payload = suspended["__interrupt__"][0].value
    print("状态          : 已挂起，执行停在", graph.get_state(config).next[0])
    print("问用户        :", payload["question"])
    print("可答的键      :", [field["key"] for field in payload["fields"]])

    # 第一次答复故意给空：证明澄清是个循环，答不全就会再问一次。
    again = graph.invoke(Command(resume={}), config=config)
    print("答复空对象后  :", "仍挂起，再问一次" if "__interrupt__" in again else "意外地继续了")

    # 第二次答复给全：图跑完。
    done = graph.invoke(Command(resume={"origin_city": "杭州"}), config=config)
    print("补上出发城市后:", "完成" if "__interrupt__" not in done else "又挂起了")
    print("最终 slots    :", done.get("slots"))
    print("最终 missing  :", done.get("missing_slots"))

    # ── 场景二：槽位已齐，不挂起 ──
    print("\n=== 场景二：槽位已齐 → 不挂起，直接结束 ===")
    ready = graph.invoke(
        {
            "raw_request": "从杭州去上海玩 5 天",
            "slots": {"origin_city": "杭州", "destination_city": "上海", "days": 5},
        },
        config={"configurable": {"thread_id": "demo-ready"}},
    )
    print("挂了没        :", "挂起了" if "__interrupt__" in ready else "没挂起")
    print("missing_slots :", ready.get("missing_slots"))


if __name__ == "__main__":
    main()
