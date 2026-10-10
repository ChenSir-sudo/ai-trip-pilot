"""命令行入口：把一句出行需求跑成结构化槽位，缺什么问什么。

位置：本阶段的临时入口。真正的入口是编排外壳（会话、幂等、路由），
    外壳排在 S6，届时本文件退回为调试工具。
可测试性：需要 langgraph 与一个可用的 `LLM_API_KEY`——真实抽取要调模型。
    完全离线的验证走 `python -m pytest`：那里的抽取器是注入的假实现。
不做的事：不做会话管理、不做幂等、不做重试策略、不落库。

用法：
    python -m src.main                       # 交互式：先输入需求
    python -m src.main "从杭州去上海玩 5 天"   # 需求作为参数；仍会追问缺失项

为什么要读标准输入：澄清不是一次调用，而是**挂起一次、恢复一次**。
    没有交互就走不完整这个循环——上一版只能把答案写死在代码里演示，
    那不是程序，是录像。
"""

from __future__ import annotations

import argparse
import sys

from langgraph.types import Command

from src.graph.builder import build_graph
from src.llm.extractor import make_llm_extractor
from src.llm.schema import validate_slots

REQUEST_PROMPT = "请输入出行需求："


def ask_for_fields(payload: dict) -> dict[str, str]:
    """按挂起时给出的字段逐个问用户，返回可回填的答复。

    契约：
      副作用：从标准输入读取，并向标准输出打印问题。
      失败模式：不吞 EOFError——输入耗尽时让它向上抛，由入口干净退出。
          如果在这里吞掉，空答复会让澄清再挂起一次，形成读不到输入的活锁。

    **校验发生在这里（边界），不在图里。** 见 docs/architecture.md §2：
    图只负责按「被问过的键」过滤，类型与取值合不合法由边界负责。
    填错就地重问，不让不合格式的值进入状态——「五天」不该变成一个字符串天数
    混进后面的求解器。
    """
    print(f"\n{payload['question']}")

    while True:
        answer: dict[str, str] = {}
        for field in payload["fields"]:
            reply = input(f"  {field['label']} [{field['key']}]: ").strip()
            if reply:
                answer[field["key"]] = reply

        if not answer:
            print("  （一项都没填，至少填一项；想放弃请按 Ctrl-C 或 Ctrl-D）")
            continue

        try:
            # 归一化后再交出去：字符串 "5" 会变成整数 5。
            return validate_slots(answer)
        except ValueError as exc:
            print(f"  这些回答不合法：{exc}")
            print("  请重新填写。")


def run(graph, raw_request: str, thread_id: str) -> dict:
    """跑完一次完整交互：invoke → 若干轮澄清 → 结束。

    契约：
      副作用：经 `graph` 发起模型请求；每轮澄清从标准输入读一次答复。
      失败模式：模型或抽取异常原样向上抛，由入口决定怎么报。
    """
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke({"raw_request": raw_request}, config=config)

    # 挂起一次就追问一次，直到槽位齐全（或者输入耗尽）。
    while "__interrupt__" in result:
        result = graph.invoke(Command(resume=ask_for_fields(result["__interrupt__"][0].value)), config=config)

    return result


def main(argv: list[str] | None = None) -> int:
    """入口。返回进程退出码：0 正常，1 没有输入，2 运行失败，130 被中断。"""
    parser = argparse.ArgumentParser(
        prog="python -m src.main",
        description="把一句出行需求跑成结构化槽位；缺什么会追问。",
    )
    parser.add_argument("request", nargs="?", help="出行需求原文；省略则交互式输入")
    args = parser.parse_args(argv)

    # 构造抽取器不联网；缺少 key 的报错会发生在第一次模型调用时。
    graph = build_graph(extractor=make_llm_extractor())

    raw_request = args.request
    if not raw_request:
        try:
            raw_request = input(REQUEST_PROMPT).strip()
        except EOFError:
            print("没有读到输入。", file=sys.stderr)
            return 1

    if not raw_request:
        print("需求为空，什么都没做。", file=sys.stderr)
        return 1

    try:
        result = run(graph, raw_request, "cli-1")
    except (EOFError, KeyboardInterrupt):
        print("\n已中断。", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 —— 命令行入口要把原因直接摆给人看
        print(f"失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        print(
            "（没有配置 LLM_API_KEY 时会走到这里：cp .env.example .env 并填入 key）",
            file=sys.stderr,
        )
        return 2

    print("\n=== 完成 ===")
    print("抽取到的槽位 :", result.get("slots"))
    print("仍缺         :", result.get("missing_slots") or "（无）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
