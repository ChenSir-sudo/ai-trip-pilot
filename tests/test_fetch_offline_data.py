"""离线快照抓取脚本的测试。

离线：夹具是自己造的 GeoJSON，不下载任何东西。**夹具数据是测试数据**。
"""

from __future__ import annotations

import io
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from scripts.fetch_offline_data import (
    build_snapshot,
    iter_features,
    report,
    representative_point,
    to_row,
)
from src.data.local import LocalSnapshotRepository


def feature(**over: Any) -> dict[str, Any]:
    base = {
        "type": "Feature",
        "id": "node/1",
        "properties": {"name": "西湖", "amenity": "park", "adm2_name": "杭州市"},
        "geometry": {"type": "Point", "coordinates": [120.1410, 30.2489]},
    }
    return {**base, **over}


def collection(*features: dict[str, Any]) -> bytes:
    return json.dumps(
        {"type": "FeatureCollection", "features": list(features)}, ensure_ascii=False
    ).encode("utf-8")


def stream(*features: dict[str, Any]):
    """夹具入口。

    注意不能用 `iter(collection(...))`——**`iter(bytes)` 产出的是整数**，
    不是 feature。这个错误在写测试时真的犯过。
    """
    return iter_features(io.BytesIO(collection(*features)))


# ── 流式解析 ─────────────────────────────────────────────────────────


def test_iter_features_yields_every_feature():
    blob = collection(feature(id="node/1"), feature(id="node/2"))

    found = list(iter_features(io.BytesIO(blob)))

    assert [f["id"] for f in found] == ["node/1", "node/2"]


def test_iter_features_tolerates_whitespace_and_newlines():
    """真实导出是格式化过的 JSON，逗号与换行会出现在任意位置。"""
    blob = json.dumps(
        {"type": "FeatureCollection", "features": [feature(), feature(id="node/2")]},
        indent=2,
    ).encode("utf-8")

    assert len(list(iter_features(io.BytesIO(blob)))) == 2


def test_iter_features_handles_an_empty_collection():
    assert list(iter_features(io.BytesIO(collection()))) == []


# ── 代表点 ───────────────────────────────────────────────────────────


def test_point_geometry_uses_its_coordinates():
    lat, lon = representative_point({"type": "Point", "coordinates": [120.1, 30.2]})

    assert (lat, lon) == (30.2, 120.1)


def test_polygon_uses_the_mean_of_its_outer_ring():
    ring = [[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0], [0.0, 0.0]]

    lat, lon = representative_point({"type": "Polygon", "coordinates": [ring]})

    assert (round(lat, 3), round(lon, 3)) == (0.8, 0.8)


def test_multipolygon_uses_its_first_polygon():
    ring = [[10.0, 20.0], [12.0, 20.0], [12.0, 22.0], [10.0, 22.0]]
    geom = {"type": "MultiPolygon", "coordinates": [[ring]]}

    lat, lon = representative_point(geom)

    assert (round(lat, 1), round(lon, 1)) == (21.0, 11.0)


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
        {"type": "Point", "coordinates": []},
        {"type": "Polygon", "coordinates": []},
        {},
    ],
)
def test_geometry_without_a_usable_point_returns_none(geometry: dict[str, Any]):
    """一条路不是一个可停靠的地点；取不到点就**不猜**。"""
    assert representative_point(geometry) is None


# ── 一条要素 → 一行 ──────────────────────────────────────────────────


def test_to_row_maps_the_osm_tags_we_need():
    row, disambiguated, skip = to_row(feature(), {})

    assert skip == ""
    assert disambiguated is False
    assert row is not None
    place_id, name, lat, lon, category, city, adcode, opening, price = row
    assert place_id == "osm:node/1"
    assert name == "西湖"
    assert (round(lat, 4), round(lon, 4)) == (30.2489, 120.141)
    assert category == "park"
    assert city == "杭州市"
    assert adcode is None, "OSM 导出没有可信的 adcode，留空而不是编一个"
    assert opening is None
    assert price is None


def test_duplicate_ids_are_disambiguated_and_reported():
    """HOT 导出的 id 不唯一（730,403 distinct < 762,586 行）。

    `places.id` 是主键，**直接插入会静默丢掉约 3 万行**。这里验证消歧生效，
    并且**这件事会被计数报出来**。
    """
    used: dict[str, int] = {}

    first, dup1, _ = to_row(feature(id="node/7"), used)
    second, dup2, _ = to_row(feature(id="node/7", properties={"name": "另一个"}), used)

    assert first is not None and second is not None
    assert first[0] == "osm:node/7"
    assert second[0] == "osm:node/7#2"
    assert (dup1, dup2) == (False, True)


def test_category_falls_back_across_the_four_mutually_exclusive_tags():
    """OSM 把类别分散在四个互斥标签里，同一要素通常只带其中一个。"""
    keys = ("amenity", "man_made", "shop", "tourism")
    for key in keys:
        row, _, _ = to_row(feature(properties={"name": "X", key: key + "-value"}), {})
        assert row is not None and row[4] == key + "-value"


def test_name_falls_back_to_the_chinese_tag():
    row, _, _ = to_row(feature(properties={"name_zh": "西湖", "adm2_name": "杭州市"}), {})

    assert row is not None and row[1] == "西湖"


@pytest.mark.parametrize(
    ("over", "reason"),
    [
        ({"properties": {}}, "no_name"),
        ({"geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}}, "no_geometry"),
        ({"id": None, "properties": {"name": "无 id"}}, "no_id"),
    ],
)
def test_rows_that_cannot_be_used_report_why(over: dict[str, Any], reason: str):
    row, _, skip = to_row(feature(**over), {})

    assert row is None
    assert skip == reason


# ── 落库：与数据访问层的接口契约 ─────────────────────────────────────


def test_built_snapshot_is_readable_by_the_repository(tmp_path: Path):
    """**这是本文件最重要的一条**：抓取脚本产出的库必须能被离线仓储直接读。

    两边共用 `SCHEMA_SQL`，这条测试把「共用」从一句话变成可执行的约束——
    任何一边改了表结构而另一边没跟上，这里就会红。
    """
    out = tmp_path / "places.sqlite"
    stats = build_snapshot(
        stream(feature(id="node/1"), feature(id="node/2", properties={"name": "灵隐寺"})),
        out,
        source="osm-hot",
        as_of="2026-10-09",
        license_id="ODbL-1.0",
    )
    assert stats["loaded"] == 2

    repo = LocalSnapshotRepository(out)

    assert "示例数据" in repo.describe()
    assert [p.name for p in repo.search_place(city="杭州市", category="park")] == ["西湖"]


def test_build_snapshot_writes_the_source_metadata(tmp_path: Path):
    out = tmp_path / "places.sqlite"
    build_snapshot(stream(), out, source="osm-hot", as_of="2026-10-09",
                   license_id="ODbL-1.0")

    with sqlite3.connect(out) as conn:
        meta = dict(conn.execute("SELECT key, value FROM meta"))

    assert meta["source"] == "osm-hot"
    assert meta["as_of"] == "2026-10-09"
    assert meta["license"] == "ODbL-1.0"


def test_build_snapshot_counts_what_it_dropped_and_what_lacks_fields(tmp_path: Path):
    out = tmp_path / "places.sqlite"
    stats = build_snapshot(
        stream(
            feature(
                id="node/1",
                properties={"name": "有营业时间", "opening_hours": "09:00-17:00", "adm2_name": "杭州市"},
            ),
            feature(id="node/2", properties={"name": "没有营业时间", "adm2_name": "杭州市"}),
            feature(id="node/3", properties={}),
        ),
        out,
        source="osm-hot",
        as_of="2026-10-09",
        license_id="ODbL-1.0",
    )

    assert stats["loaded"] == 2
    assert stats["skipped_no_name"] == 1
    assert stats["with_opening_hours"] == 1
    assert stats["with_city"] == 2


def test_report_states_the_missing_rates_because_they_decide_which_redline_holds(
    tmp_path: Path,
):
    """营业时间的缺失率决定 A3 离线能否断言，所以它必须出现在报告里。"""
    stats = {
        "loaded": 4,
        "skipped_no_name": 0,
        "skipped_no_geometry": 0,
        "skipped_no_id": 0,
        "disambiguated_ids": 1,
        "with_opening_hours": 1,
        "with_city": 4,
        "with_category": 3,
    }

    text = report(stats, tmp_path / "x.sqlite")

    assert "缺失率决定 A3" in text
    assert "25.00%" in text, "1/4 的营业时间覆盖率要显式打出来"
    assert "OpenStreetMap" in text or "ODbL" in text
