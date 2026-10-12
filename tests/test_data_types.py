"""数据访问层契约类型的测试。

离线、无 I/O：这里只验证形状与红线在类型层面的落点。
不做的事：不测任何实现的行为，只测契约的形状与红线在类型层面的落点。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.data.errors import CapabilityUnavailable, DataAccessError, UpstreamError
from src.data.types import AreaInfo, LatLon, Place, Provenance, RouteMode


def _prov(**over: object) -> Provenance:
    base = {
        "source": "osm-hot",
        "as_of": "2026-10-09",
        "is_sample": True,
        "license": "ODbL-1.0",
    }
    return Provenance(**{**base, **over})


def _place(**over: object) -> Place:
    base = {
        "id": "osm:node/1",
        "name": "测试地点",
        "lat": 30.25,
        "lon": 120.16,
        "provenance": _prov(),
    }
    return Place(**{**base, **over})


# ── 红线在类型层面的落点 ─────────────────────────────────────────────


def test_a_place_cannot_exist_without_provenance():
    """A8：每条事实带来源标记。

    这条不是靠纪律保证的——`provenance` 是必填字段，**没有来源的地点构造不出来**。
    """
    with pytest.raises(ValidationError):
        Place(id="x", name="无来源", lat=1.0, lon=2.0)  # type: ignore[call-arg]


def test_sample_marking_travels_with_the_record():
    """R7：离线数据必须能标成「示例数据」并带时间戳。"""
    cand = _place().to_candidate()

    assert cand["is_sample"] is True
    assert cand["as_of"] == "2026-10-09"


def test_upstream_data_can_be_marked_as_not_sample():
    """真实接口的数据不能被标成示例——反过来也一样要能区分。"""
    cand = _place(provenance=_prov(source="amap", is_sample=False, license="amap-terms")).to_candidate()

    assert cand["is_sample"] is False
    assert cand["source"] == "amap"


# ── 与下游的接口契约 ─────────────────────────────────────────────────


def test_candidate_carries_an_id_so_the_reducer_can_dedupe():
    """`to_candidate()` 必须带 `id`。

    这不是随便定的：图状态里的 `candidates` 挂的是 `merge_candidates`，而它
    **按 `id` 去重、缺 `id` 直接抛 KeyError**（见 src/graph/state.py）。
    这一行断言把两个模块之间的契约钉住了。
    """
    from src.graph.state import merge_candidates

    a = _place(id="osm:node/7").to_candidate()
    b = _place(id="osm:node/7", name="同一个地点的另一个来源").to_candidate()

    assert merge_candidates([], [a]) == [a]
    assert len(merge_candidates([a], [b])) == 1, "同 id 应被去重"


def test_candidate_is_flat_and_json_serializable():
    """摊平成 dict 是刻意的：状态要过 checkpointer，嵌套模型需要自定义序列化器。"""
    import json

    cand = _place(category="museum", city="杭州", adcode="330100").to_candidate()

    assert not any(isinstance(v, (dict, list)) for v in cand.values()), "候选不该有嵌套结构"
    json.dumps(cand, ensure_ascii=False)  # 不抛异常即通过


# ── 不可变与严格 ─────────────────────────────────────────────────────


def test_records_are_frozen():
    """候选一旦生成就不该被就地改写——改动要走状态，才留得下痕迹。"""
    place = _place()
    with pytest.raises(ValidationError):
        place.name = "改个名"  # type: ignore[misc]


def test_unknown_fields_are_rejected():
    """上游字段漂移必须当场报错，而不是被静默忽略。"""
    with pytest.raises(ValidationError):
        Place(  # type: ignore[call-arg]
            id="x", name="y", lat=1.0, lon=2.0, provenance=_prov(), unknown_field=1
        )


# ── 「没有能力」与「没有结果」必须分得开 ─────────────────────────────


def test_capability_unavailable_is_its_own_error():
    """离线侧没有班次数据，抛的是「能力不可用」，不是空列表。

    返回空列表会让上层把「没有这个能力」读成「当日无车」——**后者是一句凭空
    生成的事实**，正是红线 R2 要挡的东西。
    """
    err = CapabilityUnavailable("离线快照不含班次数据")

    assert isinstance(err, DataAccessError)
    assert not isinstance(err, UpstreamError), "能力缺失不是上游故障，排查方向不同"


def test_route_mode_values_match_the_upstream_parameter_names():
    assert [m.value for m in RouteMode] == ["driving", "walking", "transit"]


def test_latlon_and_area_info_are_immutable_value_objects():
    point = LatLon(lat=30.0, lon=120.0)
    area = AreaInfo(
        adcode="330100", name="杭州市", level="city", center=point, provenance=_prov()
    )

    assert area.center == LatLon(lat=30.0, lon=120.0)
    with pytest.raises(ValidationError):
        area.name = "改个名"  # type: ignore[misc]
