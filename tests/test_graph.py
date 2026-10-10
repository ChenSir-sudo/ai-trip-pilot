"""规划图的结构与状态流转测试。

全部零外部依赖：不联网、不调模型、不需要密钥、不需要数据库。
这是刻意的——图的结构是否正确，与节点内部的实现质量无关，
所以这部分测试不应该因为模型换供应商而变红。
"""

from __future__ import annotations

from src.graph.builder import build_graph
from src.graph.state import merge_candidates


def test_topology_has_a_fork_after_completeness_check():
    """拓扑：START → extract_slots → check_completeness →{clarify | END}。"""
    graph = build_graph()

    edges = {(e.source, e.target, e.conditional) for e in graph.get_graph().edges}

    assert ("__start__", "extract_slots", False) in edges
    assert ("extract_slots", "check_completeness", False) in edges
    assert ("check_completeness", "clarify", True) in edges
    assert ("check_completeness", "__end__", True) in edges
    assert ("clarify", "__end__", False) in edges


def test_invoke_keeps_input_and_adds_slots():
    """状态流转：输入字段不被覆盖，节点返回的增量被合并进来。

    这条测试守的是「覆盖 vs 合并」这个最容易搞错的语义：节点只返回
    自己的那几个字段，而 raw_request 必须原样保留下来。
    """
    graph = build_graph()

    result = graph.invoke(
        {"raw_request": "规划一下去上海玩 7 天"},
        config={"configurable": {"thread_id": "test-1"}},
    )

    assert result["raw_request"] == "规划一下去上海玩 7 天"
    assert result["slots"]["destination_city"] == "上海"


def test_missing_slots_take_the_clarify_branch():
    """缺槽位 → 走澄清分支，并且真的生成了问句。

    桩节点只给了目的城市与天数，所以缺出发城市（「日期或天数」已由 days 满足）。
    """
    graph = build_graph()

    result = graph.invoke(
        {"raw_request": "规划一下去上海玩 7 天"},
        config={"configurable": {"thread_id": "test-clarify"}},
    )

    assert result["missing_slots"] == ["出发城市"]
    assert "出发城市" in result["clarify_question"]


def test_complete_slots_take_the_ready_branch():
    """槽位齐全 → 不走澄清分支：没有任何问句被写进状态。

    「没写」正是这条边存在的证据——如果分支走错，clarify 会给这个字段赋值。
    """
    graph = build_graph()

    result = graph.invoke(
        {
            "raw_request": "从杭州去上海玩 5 天",
            "slots": {"origin_city": "杭州", "destination_city": "上海", "days": 5},
        },
        config={"configurable": {"thread_id": "test-ready"}},
    )

    assert result["missing_slots"] == []
    assert "clarify_question" not in result


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
    """reducer 必须幂等——因为图里有修复循环，同一个节点会被执行多次。"""
    round_one = [{"id": "a"}, {"id": "b"}]

    once = merge_candidates([], round_one)
    twice = merge_candidates(once, round_one)

    assert twice == once


def test_reducer_field_is_pre_seeded_with_empty_list():
    """挂了 reducer 的字段会被框架预置成空列表，而不是缺失。

    这条测试的作用是把一个「写代码时顺手发现的行为」固定成依据：节点读
    candidates 时可以写成 state["candidates"] 而不必写 .get(..., [])。
    框架升级若改变这个行为，这里会先变红。
    """
    graph = build_graph()

    result = graph.invoke(
        {"raw_request": "规划一下去上海玩 7 天"},
        config={"configurable": {"thread_id": "test-2"}},
    )

    assert result["candidates"] == []
