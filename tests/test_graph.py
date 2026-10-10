"""规划图的结构、状态流转与中断测试。

全部零外部依赖：不联网、不调模型、不需要密钥、不需要数据库。
这是刻意的——图的结构是否正确，与节点内部的实现质量无关，
所以这部分测试不应该因为模型换供应商而变红。
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from src.graph.builder import build_graph
from src.graph.state import merge_candidates

RAW_REQUEST = "规划一下去上海玩 7 天"


def _config(thread_id: str) -> dict:
    """同一个 thread_id 才算同一次会话——挂起与恢复靠它配对。"""
    return {"configurable": {"thread_id": thread_id}}


# ── 拓扑 ──────────────────────────────────────────────────────────────


def test_topology_has_a_fork_and_a_clarify_loop():
    """拓扑：START → extract_slots → check_completeness →{clarify | END}，clarify 回到判定。"""
    graph = build_graph()

    edges = {(e.source, e.target, e.conditional) for e in graph.get_graph().edges}

    assert ("__start__", "extract_slots", False) in edges
    assert ("extract_slots", "check_completeness", False) in edges
    assert ("check_completeness", "clarify", True) in edges
    assert ("check_completeness", "__end__", True) in edges
    assert ("clarify", "check_completeness", False) in edges, (
        "澄清必须能回到判定，否则答复不全时就卡住了"
    )


# ── 状态流转 ──────────────────────────────────────────────────────────


def test_invoke_keeps_input_and_adds_slots():
    """输入字段不被覆盖，节点返回的增量被合并进来。"""
    graph = build_graph()

    result = graph.invoke({"raw_request": RAW_REQUEST}, config=_config("test-merge"))

    assert result["raw_request"] == RAW_REQUEST
    assert result["slots"]["destination_city"] == "上海"


def test_reducer_field_is_pre_seeded_with_empty_list():
    """挂了 reducer 的字段会被框架预置成空列表，而不是缺失。

    这条把「写代码时顺手发现的行为」固定成依据：节点读 candidates 时
    可以写成 state["candidates"] 而不必写 .get(..., [])。
    """
    graph = build_graph()

    result = graph.invoke({"raw_request": RAW_REQUEST}, config=_config("test-seed"))

    assert result["candidates"] == []


# ── reducer ───────────────────────────────────────────────────────────


def test_merge_candidates_dedupes_by_id_keeping_first():
    """reducer 语义：按 id 去重，先到的保留。

    这条测试守着红线 A1（方案中每个停靠点都能在候选池中按 ID 命中）。
    如果 reducer 退化成直接拼接，重复 id 会进入候选池，「按 id 命中」
    这个判断就不再可信。
    """
    first_round = [{"id": "a", "name": "外滩"}, {"id": "b", "name": "豫园"}]
    second_round = [{"id": "b", "name": "豫园"}, {"id": "c", "name": "武康路"}]

    merged = merge_candidates(first_round, second_round)

    assert [c["id"] for c in merged] == ["a", "b", "c"]
    assert len(merged) == 3, "同 id 的候选必须被合并，而不是各留一份"


def test_merge_candidates_is_idempotent():
    """reducer 必须幂等——因为图里有循环，同一个节点会被执行多次。"""
    round_one = [{"id": "a"}, {"id": "b"}]

    once = merge_candidates([], round_one)
    twice = merge_candidates(once, round_one)

    assert twice == once


# ── 中断：挂起与恢复 ──────────────────────────────────────────────────


def test_first_invoke_suspends_at_clarify():
    """信息不全时是**挂起**，不是结束——而且是正常返回，不是抛异常。"""
    graph = build_graph()
    config = _config("test-suspend")

    result = graph.invoke({"raw_request": RAW_REQUEST}, config=config)

    assert "__interrupt__" in result, "信息不全时应当挂起"
    payload = result["__interrupt__"][0].value
    assert "出发城市" in payload["question"]
    assert {"key": "origin_city", "label": "出发城市"} in payload["fields"]

    # 状态被存下来了 —— 这正是 checkpointer 在干活，而不是「接线但闲置」
    assert graph.get_state(config).next == ("clarify",)


def test_resume_with_the_answer_finishes():
    """答复之后从断点继续，并真的把答复写进了槽位。"""
    graph = build_graph()
    config = _config("test-resume")
    graph.invoke({"raw_request": RAW_REQUEST}, config=config)

    result = graph.invoke(Command(resume={"origin_city": "杭州"}), config=config)

    assert "__interrupt__" not in result, "答复补齐后不该再挂起"
    assert result["missing_slots"] == []
    assert result["slots"]["origin_city"] == "杭州"


def test_incomplete_answer_suspends_again():
    """澄清是个循环：答复没能补齐，就再问一次。"""
    graph = build_graph()
    config = _config("test-loop")
    graph.invoke({"raw_request": RAW_REQUEST}, config=config)

    result = graph.invoke(Command(resume={}), config=config)

    assert "__interrupt__" in result, "空答复不该让循环结束"


def test_keys_that_were_not_asked_are_ignored():
    """答复是受控接口，不是第二个入口。

    允许任意键写入，等于给调用方开了一条绕过抽取通道、直接篡改槽位的路。
    """
    graph = build_graph()
    config = _config("test-keys")
    graph.invoke({"raw_request": RAW_REQUEST}, config=config)

    result = graph.invoke(
        Command(resume={"origin_city": "杭州", "budget": 5000}), config=config
    )

    assert result["slots"]["origin_city"] == "杭州"
    assert "budget" not in result["slots"], "没被问过的键不该进入槽位"


def test_interrupt_makes_the_node_rerun_from_the_start():
    """固定一条我们依赖的框架语义：恢复时节点**从头重新执行**。

    所以 `interrupt()` 之前不能有副作用——否则每次恢复都会重复执行一次，
    而且是静默的。这条测试守的是**框架行为**：LangGraph 升级若改变它，
    这里会先红，我们能在被坑之前知道。
    """
    runs: list[str] = []

    class MiniState(TypedDict, total=False):
        done: bool

    def node(state: MiniState) -> dict:
        runs.append("interrupt 之前")
        interrupt({"ask": "?"})
        runs.append("interrupt 之后")
        return {"done": True}

    builder = StateGraph(MiniState)
    builder.add_node("n", node)
    builder.add_edge(START, "n")
    builder.add_edge("n", END)
    compiled = builder.compile(checkpointer=InMemorySaver())
    config = _config("test-reexec")

    compiled.invoke({}, config=config)
    assert runs == ["interrupt 之前"]

    runs.clear()
    compiled.invoke(Command(resume="答复"), config=config)

    assert runs == ["interrupt 之前", "interrupt 之后"], "恢复时节点应从头重跑"
