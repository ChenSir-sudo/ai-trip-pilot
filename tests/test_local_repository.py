"""离线仓储的测试。

离线、无 I/O 依赖外部数据：快照是测试自己在临时目录里建的，用的是与抓取脚本
**同一份** `SCHEMA_SQL`。夹具里的地名是测试数据，不是产品数据。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.data.errors import CapabilityUnavailable, UpstreamError
from src.data.local import SCHEMA_SQL, LocalSnapshotRepository, haversine_m
from src.data.types import LatLon, RouteBasis, RouteMode

META = {
    "source": "osm-hot",
    "as_of": "2026-10-09",
    "license": "ODbL-1.0",
}

PLACES = [
    # id, name, lat, lon, category, city, adcode, opening_hours, price
    ("osm:node/1", "西湖", 30.2489, 120.1410, "park", "杭州", "330100", "全天", None),
    ("osm:node/2", "浙江省博物馆", 30.2530, 120.1470, "museum", "杭州", "330100", "09:00-17:00", 0.0),
    ("osm:node/3", "楼外楼", 30.2500, 120.1400, "restaurant", "杭州", "330100", "10:00-21:00", 120.0),
    ("osm:node/4", "外滩", 31.2397, 121.4900, "attraction", "上海", "310101", "全天", None),
]
AREAS = [
    ("330100", "杭州市", "city", 30.2741, 120.1551, "330000"),
    ("310000", "上海市", "city", 31.2304, 121.4737, "310000"),
]


@pytest.fixture()
def snapshot(tmp_path: Path) -> Path:
    path = tmp_path / "places.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_SQL)
    conn.executemany("INSERT INTO meta (key, value) VALUES (?, ?)", META.items())
    conn.executemany("INSERT INTO places VALUES (?,?,?,?,?,?,?,?,?)", PLACES)
    conn.executemany(
        "INSERT INTO areas VALUES (?,?,?,?,?,?)",
        [(a[0], a[1], a[2], a[3], a[4], a[5]) for a in AREAS],
    )
    conn.execute(
        "INSERT INTO weather VALUES (?,?,?,?,?)", ("330100", "2026-10-12", "晴", 15.0, 24.0)
    )
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def repo(snapshot: Path) -> LocalSnapshotRepository:
    return LocalSnapshotRepository(snapshot)


# ── 构造期的配置检查 ─────────────────────────────────────────────────


def test_missing_snapshot_says_how_to_get_one(tmp_path: Path):
    """配置问题要在构造时就说清楚，并且给出下一步动作。"""
    with pytest.raises(UpstreamError, match="fetch_offline_data"):
        LocalSnapshotRepository(tmp_path / "不存在.sqlite")


def test_snapshot_without_meta_is_rejected(tmp_path: Path):
    path = tmp_path / "empty.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()

    with pytest.raises(UpstreamError, match="meta.source"):
        LocalSnapshotRepository(path)


# ── 来源标记：R7 与 A8 的实际落点 ────────────────────────────────────


def test_describe_states_source_date_and_the_sample_marker(repo: LocalSnapshotRepository):
    """可演示产出要求「打印来源」；R7 要求标注示例数据与时间戳。"""
    text = repo.describe()

    assert "osm-hot" in text
    assert "2026-10-09" in text
    assert "示例数据" in text, "R7：离线结果必须被标成示例数据"
    assert "4" in text, "应当带上条目数"


def test_every_record_carries_sample_marking_and_license(repo: LocalSnapshotRepository):
    """不可协商：离线快照产出的每一条都必须是 is_sample=True。"""
    for place in repo.search_place(city="杭州"):
        assert place.provenance.is_sample is True
        assert place.provenance.source == "osm-hot"
        assert place.provenance.license == "ODbL-1.0"
        assert place.provenance.as_of == "2026-10-09"


# ── 检索 ─────────────────────────────────────────────────────────────


def test_search_filters_by_city(repo: LocalSnapshotRepository):
    names = {p.name for p in repo.search_place(city="杭州")}

    assert names == {"西湖", "浙江省博物馆", "楼外楼"}
    assert "外滩" not in names


def test_search_combines_keywords_and_category(repo: LocalSnapshotRepository):
    assert [p.name for p in repo.search_place(city="杭州", keywords="博物")] == ["浙江省博物馆"]
    assert [p.name for p in repo.search_place(city="杭州", category="restaurant")] == ["楼外楼"]
    assert repo.search_place(city="杭州", keywords="博物", category="restaurant") == []


def test_search_is_deterministically_ordered_and_limited(repo: LocalSnapshotRepository):
    """同一份快照下结果必须可复现，否则回归评测每次拿到的顺序都不同。"""
    assert [p.id for p in repo.search_place(city="杭州")] == [
        "osm:node/1",
        "osm:node/2",
        "osm:node/3",
    ]
    assert len(repo.search_place(city="杭州", limit=2)) == 2


def test_search_returns_ids_that_are_unique_within_a_result(repo: LocalSnapshotRepository):
    """`merge_candidates` 按 `id` 去重，**[同 id 会被合并掉一条]**。

    所以检索结果里的 id 必须唯一——否则候选池会静默丢地点，而且不报错。
    """
    ids = [p.id for p in repo.search_place(city="杭州")]

    assert len(ids) == len(set(ids))


def test_unknown_city_is_an_empty_result_not_an_error(repo: LocalSnapshotRepository):
    """「查到了但没有」与「查不了」必须分开。"""
    assert repo.search_place(city="不存在的城市") == []


# ── 地名解析：不许编坐标 ─────────────────────────────────────────────


def test_resolve_prefers_a_real_place_over_an_area_center(repo: LocalSnapshotRepository):
    place = repo.resolve_place(name="西湖")

    assert place is not None
    assert place.id == "osm:node/1"
    assert place.lat == pytest.approx(30.2489)


def test_resolve_falls_back_to_the_area_center(repo: LocalSnapshotRepository):
    """行政区表只有中心点，精度更差，但比编一个坐标诚实。"""
    place = repo.resolve_place(name="上海市")

    assert place is not None
    assert place.id == "area:310000"
    assert place.adcode == "310000"


def test_resolve_returns_none_rather_than_inventing_a_point(repo: LocalSnapshotRepository):
    """编一个中心点会让后续所有距离都错，而且不报错。"""
    assert repo.resolve_place(name="根本没有这个地方") is None


# ── 路线：估算必须自带标记 ───────────────────────────────────────────


def test_route_never_claims_to_be_road_network(repo: LocalSnapshotRepository):
    """离线只能给直线估算。**这个断言是 A4 能否被信任的前提。**

    如果离线实现把估算标成 `ROAD_NETWORK`，A4 就会拿估算值当实测值断言，
    而且不报错——那正是这个字段被补上的原因。
    """
    result = repo.route(
        origin=LatLon(lat=30.2489, lon=120.1410),
        destination=LatLon(lat=30.2530, lon=120.1470),
        mode=RouteMode.WALKING,
    )

    assert result.basis is RouteBasis.STRAIGHT_LINE_ESTIMATE
    assert result.provenance.is_sample is True


def test_route_duration_matches_distance_and_speed(repo: LocalSnapshotRepository):
    result = repo.route(
        origin=LatLon(lat=30.0, lon=120.0),
        destination=LatLon(lat=30.0, lon=120.0),
        mode=RouteMode.DRIVING,
    )

    assert result.distance_m == 0
    assert result.duration_s == 0


def test_haversine_matches_a_known_distance():
    """北京—上海直线距离约 1067 km；这里允许 3% 误差（大圆距离对坐标精度不敏感）。"""
    beijing = LatLon(lat=39.9042, lon=116.4074)
    shanghai = LatLon(lat=31.2304, lon=121.4737)

    assert haversine_m(beijing, shanghai) == pytest.approx(1_067_000, rel=0.03)


# ── 天气：没覆盖不等于没有 ───────────────────────────────────────────


def test_weather_reads_the_snapshot(repo: LocalSnapshotRepository):
    report = repo.weather(adcode="330100", date="2026-10-12")

    assert report.text == "晴"
    assert report.temp_max_c == 24.0
    assert report.provenance.is_sample is True


def test_weather_outside_the_snapshot_raises_instead_of_returning_nothing(
    repo: LocalSnapshotRepository,
):
    """「快照没覆盖那天」与「那天没有天气」是两件事，不能都变成空值。"""
    with pytest.raises(CapabilityUnavailable, match="不表示那天没有天气"):
        repo.weather(adcode="330100", date="2099-01-01")


# ── 班次：能力边界 ───────────────────────────────────────────────────


def test_train_schedule_is_a_capability_boundary_not_an_empty_list(
    repo: LocalSnapshotRepository,
):
    """返回空列表会被读成「当日无车」——那是一句凭空生成的事实。"""
    with pytest.raises(CapabilityUnavailable, match="两个不同的事实"):
        repo.train_schedule(from_city="杭州", to_city="上海", date="2026-10-12")


# ── 行政区 ───────────────────────────────────────────────────────────


def test_lookup_area_returns_center_and_parent(repo: LocalSnapshotRepository):
    area = repo.lookup_area(adcode="330100")

    assert area is not None
    assert area.name == "杭州市"
    assert area.level == "city"
    assert area.parent_adcode == "330000"
    assert area.center is not None and area.center.lat == pytest.approx(30.2741)


def test_lookup_area_returns_none_for_unknown_code(repo: LocalSnapshotRepository):
    assert repo.lookup_area(adcode="999999") is None
