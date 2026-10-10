"""规划图的结构与状态流转测试。

全部零外部依赖：不联网、不调模型、不需要密钥、不需要数据库。
这是刻意的——图的结构是否正确，与节点内部的实现质量无关，
所以这部分测试不应该因为模型换供应商而变红。
"""

from __future__ import annotations

from src.graph.builder import build_graph
from src.graph.state import merge_candidates


def test_topology_is_start_to_extract_slots_to_end():
    """拓扑：START → extract_slots → END。"""
    graph = build_graph()

    edges = {(e.source, e.target) for e in graph.get_graph().edges}

    assert ("__start__", "extract_slots") in edges
    assert ("extract_slots", "__end__") in edges


def test_invoke_keeps_input_and_adds_slots():
    """状态流转：输入字段不被覆盖，节点返回的增量被合并进来。

    这条测试守的是「覆盖 vs 合并」这个最容易搞错的语义：节点只返回
    slots / missing_slots，而 raw_request 必须原样保留下来。
    """
    graph = build_graph()

    result = graph.invoke(
        {"raw_request": "规划一下去上海玩 7 天"},
        config={"configurable": {"thread_id": "test-1"}},
    )

    assert result["raw_request"] == "规划一下去上海玩 7 天"
    assert result["slots"]["destination"] == "上海"
    assert result["missing_slots"], "缺失槽位不应为空——它决定下一步是否要澄清"


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
