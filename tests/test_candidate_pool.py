"""候选池节点的测试。

离线：数据源是 `tests/fakes.py` 里的假实现，不需要网络、快照或密钥。
"""

from __future__ import annotations

from typing import Any

import pytest
from fakes import FakeDataAccess, make_place

from src.graph.builder import build_graph
from src.graph.candidate_pool import CANDIDATE_CATEGORIES, make_build_candidate_pool


def run_node(data: Any, slots: dict[str, Any], **kwargs: Any) -> dict:
    return make_build_candidate_pool(data, **kwargs)({"slots": slots})


# ── 取回候选 ─────────────────────────────────────────────────────────


def test_pool_is_built_from_the_injected_source():
    """S2 的可演示产出：给定需求 → 取回候选池。"""
    data = FakeDataAccess(
        [
            make_place("a:1", name="西湖", category="attraction"),
            make_place("a:2", name="楼外楼", category="restaurant"),
        ]
    )

    out = run_node(data, {"destination_city": "杭州"})

    assert {c["name"] for c in out["candidates"]} == {"西湖", "楼外楼"}
    assert all(c["source"] == "fake" for c in out["candidates"]), "每条都要带来源（A8）"


def test_pool_is_deterministic_and_deduped_by_id():
    """同一份输入必须得到同一批候选，否则回归评测不可比。

    同一 id 出现两次时只留一条——`merge_candidates` 会兜底，但 `max_total`
    得按去重后的条数算，否则截断条数会随重复数漂移。
    """
    data = FakeDataAccess(
        [
            make_place("a:2", name="乙"),
            make_place("a:1", name="甲"),
            make_place("a:1", name="甲的另一个来源"),
        ]
    )

    out = run_node(data, {"destination_city": "杭州"})

    assert [c["id"] for c in out["candidates"]] == ["a:1", "a:2"], "按 id 定序"
    assert [c["name"] for c in out["candidates"]] == ["甲", "乙"], "同 id 保留先到的"


def test_every_configured_category_is_searched_once():
    """类别词表是跨数据源的契约，四类都要被问到。"""
    data = FakeDataAccess([])

    run_node(data, {"destination_city": "杭州"})

    assert [category for _, category in data.searches] == list(CANDIDATE_CATEGORIES)


def test_destination_city_is_used_verbatim():
    data = FakeDataAccess([])

    run_node(data, {"destination_city": "上海"})

    assert {city for city, _ in data.searches} == {"上海"}


# ── 来源与边界必须可见 ───────────────────────────────────────────────


def test_notes_name_the_data_source():
    """「打印来源」是可演示产出的一部分，也是协议 7.7 的正向署名义务。

    来源必须在输出里看得见，而不是只存在于某个对象的属性里。
    """
    data = FakeDataAccess([])

    out = run_node(data, {"destination_city": "杭州"})

    assert any("假数据源" in note for note in out["data_notes"])


def test_an_unavailable_category_is_recorded_and_does_not_abort():
    """一类取不到不该让整个规划失败——**但也不能不留痕迹**（红线 R8 的同一精神）。"""
    data = FakeDataAccess([make_place("a:1")], unavailable=("hotel", "restaurant"))

    out = run_node(data, {"destination_city": "杭州"})

    assert [c["id"] for c in out["candidates"]] == ["a:1"], "其余类别照常取回"
    assert sum("不可用" in note for note in out["data_notes"]) == 2


def test_empty_result_is_recorded_rather_than_looking_like_a_normal_empty_pool():
    data = FakeDataAccess([])

    out = run_node(data, {"destination_city": "没有地点的地方"})

    assert out["candidates"] == []
    assert any("没有取到任何候选" in note for note in out["data_notes"])


def test_truncation_is_recorded():
    places = [make_place(f"a:{i}") for i in range(10)]
    data = FakeDataAccess(places)

    out = run_node(data, {"destination_city": "杭州"}, per_category=10, max_total=3)

    assert len(out["candidates"]) == 3
    assert any("截到 3 条" in note for note in out["data_notes"])


def test_failed_geocoding_is_recorded_but_search_still_runs():
    """解析不出中心点也继续——但要说出来。"""
    data = FakeDataAccess([make_place("a:1")], resolved=None)

    out = run_node(data, {"destination_city": "杭州"})

    assert any("没有" in note and "中心点" in note for note in out["data_notes"])
    assert out["candidates"], "解析失败不代表检索要放弃"


# ── 用错的方式必须响亮地失败 ─────────────────────────────────────────


def test_no_data_source_is_a_loud_error_not_an_empty_pool():
    """返回空池会让下游以为「这个城市没有地点」。"""
    with pytest.raises(RuntimeError, match="load_data_access"):
        run_node(None, {"destination_city": "杭州"})


def test_missing_destination_is_a_programming_error():
    """图保证到这里必需槽位齐全；走到这里说明有人直接调了这个节点。"""
    with pytest.raises(ValueError, match="destination_city"):
        run_node(FakeDataAccess([]), {})


# ── 与图连起来 ───────────────────────────────────────────────────────


def test_the_graph_fills_the_pool_after_the_slots_are_complete():
    """端到端：槽位齐了之后，候选池出现在状态里，且来源可见。

    这条把 S2 的两半钉在一起——**图的变化**与**数据层的变化**必须同时成立，
    否则「给定需求 → 取回候选池」只是文档里的一句话。
    """
    data = FakeDataAccess([make_place("a:1", name="西湖", category="attraction")])
    graph = build_graph(
        # 必需槽位要给全（出发城市也在其中），否则图停在澄清、根本走不到候选池
        extractor=lambda raw: {"origin_city": "上海", "destination_city": "杭州", "days": 3},
        data=data,
    )

    result = graph.invoke(
        {"raw_request": "去杭州玩三天"}, config={"configurable": {"thread_id": "pool"}}
    )

    assert result["missing_slots"] == []
    assert [c["name"] for c in result["candidates"]] == ["西湖"]
    assert any("假数据源" in note for note in result["data_notes"])
