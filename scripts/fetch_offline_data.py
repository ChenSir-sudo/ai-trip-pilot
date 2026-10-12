"""抓取离线快照：把 HOT/OSM 的中国 POI 导出落成一个 SQLite 库。

位置：开发期脚本，**不在运行路径上**。数据访问层只读快照（见 src/data/local.py），
    抓取与使用分开，测试才不需要 100MB 的下载。
可测试性：解析与落库都被拆成可单独调用的函数，测试用自己造的 GeoJSON 夹具验证，
    不需要网络（见 tests/test_fetch_offline_data.py）。
不做的事：不抓天气、不抓班次、不抓行政区划。

    **为什么不做天气**：快照的 `meta` 只有一个 `source`/`license` 字段，而 POI 来自
    OSM（ODbL）、天气来自 Open-Meteo（CC-BY-4.0）——混在一张表里就没法如实标注来源，
    那正是红线 A8 要挡的。要加天气就先给 `weather` 表自己的一份来源。
    **为什么不做班次与行政区划**：离线侧没有许可明确的来源，见
    docs/research/2026-offline-aux-services.md §3。

数据来源：HOT 的中国 POI 导出（ODbL），直链实测可下、无需鉴权。
"""

from __future__ import annotations

import argparse
import io
import json
import sqlite3
import sys
import urllib.request
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.local import SCHEMA_SQL  # noqa: E402

# 已实测可下（HTTP 206 range 请求）的直链。**不要用 data.humdata.org 的数据集页**：
# 它对脚本请求返回 AWS WAF 的人机挑战（HTTP 202）。
DEFAULT_URL = (
    "https://production-raw-data-api.s3.amazonaws.com/ISO3/CHN/points_of_interest/"
    "hotosm_chn_points_of_interest_osm_geojson.zip"
)
DEFAULT_OUT = Path("data/offline/places.sqlite")

# 类别来自 OSM 的四个互斥标签：同一要素通常只带其中一个，所以要挨个取第一个非空。
_CATEGORY_KEYS = ("amenity", "man_made", "shop", "tourism")
_NAME_KEYS = ("name", "name_zh", "name_en", "name_latin")
_READ_BLOCK = 1 << 20


def iter_features(stream: io.BufferedIOBase) -> Iterator[dict[str, Any]]:
    """从 GeoJSON FeatureCollection 里**逐条**产出 feature。

    契约：
      副作用：从 `stream` 顺序读取。
      失败模式：JSON 截断时抛 `json.JSONDecodeError`。

    > **为什么不用 `json.load`**：中国 POI 的 GeoJSON 解压后是数百 MB，
    > 整体读进内存会白白占掉一两 GB。这里按块读取 + `raw_decode` 逐条解析，
    > 内存占用与文件大小无关。
    """
    decoder = json.JSONDecoder()
    buf = ""

    def fill() -> bool:
        nonlocal buf
        chunk = stream.read(_READ_BLOCK)
        if not chunk:
            return False
        buf += chunk.decode("utf-8", errors="replace")
        return True

    while '"features"' not in buf:
        if not fill():
            return
    buf = buf[buf.index("[", buf.index('"features"')) + 1 :]

    while True:
        buf = buf.lstrip(" \t\r\n,")
        while not buf:
            if not fill():
                return
            buf = buf.lstrip(" \t\r\n,")
        if buf.startswith("]"):
            return
        try:
            obj, end = decoder.raw_decode(buf)
        except json.JSONDecodeError:
            if not fill():
                raise
            continue
        buf = buf[end:]
        if isinstance(obj, dict):
            yield obj


def representative_point(geometry: dict[str, Any]) -> tuple[float, float] | None:
    """从一个几何体取一个代表点 `(lat, lon)`。

    契约：
      副作用：无。纯函数。
      失败模式：取不到点时返回 `None`，**不猜**。

    规则：点直接取坐标；面与多多边形取外环顶点的算术平均——**那是形心近似，不是
    真实的几何质心**，对形状不规则的面会有偏差。线状要素返回 `None`（一条路不是
    一个可停靠的地点）。
    """
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")

    if gtype == "Point" and isinstance(coords, list) and len(coords) >= 2:
        lon, lat = coords[0], coords[1]
        return (float(lat), float(lon))

    if gtype == "Polygon" and isinstance(coords, list) and coords:
        ring = coords[0]
    elif gtype == "MultiPolygon" and isinstance(coords, list) and coords:
        ring = coords[0][0] if coords[0] else []
    else:
        return None

    if not isinstance(ring, list) or not ring:
        return None
    lons = [p[0] for p in ring if isinstance(p, list) and len(p) >= 2]
    lats = [p[1] for p in ring if isinstance(p, list) and len(p) >= 2]
    if not lons or not lats:
        return None
    return (sum(lats) / len(lats), sum(lons) / len(lons))


def to_row(
    feature: dict[str, Any], used_ids: dict[str, int]
) -> tuple[tuple[Any, ...] | None, bool, str]:
    """把一条 feature 转成 `places` 表的一行。

    返回 `(行, 是否做了 id 消歧, 跳过原因)`；行是 `None` 时第三个值是原因
    （`"no_name"` / `"no_geometry"` / `"no_id"`），调用方据此计数——**统计要显式，
    否则「跳过了一堆要素」这件事没人知道**。

    > **id 消歧是必须的**：研究实测 HOT 导出的 `id` **不唯一**（730,403 distinct
    > < 762,586 行）。`places.id` 是主键，直接插入会丢掉约 3 万行——**而且是静默丢**。
    > 这里给重复的 id 加 `#2`、`#3` 后缀，并把消歧条数报出来。
    > 消歧后的 id 在**同一份快照内**稳定，足够支撑 A1（按 ID 命中）；它不跨快照稳定，
    > 而 A1 也不需要跨快照。
    """
    props = feature.get("properties") or {}
    if not isinstance(props, dict):
        return None, False, "no_name"

    name = next((str(props[k]).strip() for k in _NAME_KEYS if props.get(k)), "")
    if not name:
        # 无名的地点进不了方案——方案里要展示它。丢掉并计数，不静默。
        return None, False, "no_name"

    geometry = feature.get("geometry") or {}
    point = representative_point(geometry if isinstance(geometry, dict) else {})
    if point is None:
        return None, False, "no_geometry"
    lat, lon = point

    raw_id = feature.get("id") or props.get("id")
    if raw_id in (None, ""):
        return None, False, "no_id"

    base = f"osm:{raw_id}"
    seen = used_ids.get(base, 0) + 1
    used_ids[base] = seen
    place_id = base if seen == 1 else f"{base}#{seen}"

    category = next((str(props[k]) for k in _CATEGORY_KEYS if props.get(k)), None)
    city = props.get("adm2_name") or None
    opening = props.get("opening_hours") or None

    return (place_id, name, lat, lon, category, city, None, opening, None), seen > 1, ""


def build_snapshot(
    features: Iterator[dict[str, Any]],
    out: Path,
    *,
    source: str,
    as_of: str,
    license_id: str,
) -> dict[str, int]:
    """把 feature 流写成快照库，返回统计。

    契约：
      副作用：**覆盖写 `out`**（先写临时文件再替换，避免写到一半留下半成品）。
      失败模式：路径不可写时抛 `OSError`。
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    stats = {
        "loaded": 0,
        "skipped_no_name": 0,
        "skipped_no_geometry": 0,
        "disambiguated_ids": 0,
        "with_opening_hours": 0,
        "with_city": 0,
        "with_category": 0,
    }
    used_ids: dict[str, int] = {}

    tmp = out.with_suffix(out.suffix + ".tmp")
    conn = sqlite3.connect(tmp)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.executemany(
            "INSERT INTO meta (key, value) VALUES (?, ?)",
            {
                "source": source,
                "as_of": as_of,
                "license": license_id,
                "note": "离线快照，界面须标注「示例数据」（红线 R7）",
            }.items(),
        )
        for feature in features:
            row, disambiguated, skip = to_row(feature, used_ids)
            if row is None:
                stats[f"skipped_{skip}"] = stats.get(f"skipped_{skip}", 0) + 1
                continue
            conn.execute("INSERT INTO places VALUES (?,?,?,?,?,?,?,?,?)", row)
            stats["loaded"] += 1
            stats["disambiguated_ids"] += int(disambiguated)
            stats["with_opening_hours"] += int(row[7] is not None)
            stats["with_city"] += int(row[5] is not None)
            stats["with_category"] += int(row[4] is not None)
        conn.commit()
    finally:
        conn.close()
    tmp.replace(out)
    return stats


def report(stats: dict[str, int], out: Path) -> str:
    """把统计写成人能读的一段话。**缺失率要显式打出来**，它们决定了哪条红线离线可断言。"""
    loaded = max(stats["loaded"], 1)
    lines = [
        f"快照已写入 {out}",
        f"  载入地点      {stats['loaded']:,}",
        f"  无坐标跳过    {stats.get('skipped_no_geometry', 0):,}",
        f"  无名跳过      {stats.get('skipped_no_name', 0):,}",
        f"  无 id 跳过    {stats.get('skipped_no_id', 0):,}",
        f"  id 消歧       {stats['disambiguated_ids']:,}"
        f"（{stats['disambiguated_ids'] / loaded:.2%}，HOT 导出的 id 不唯一）",
        f"  有营业时间    {stats['with_opening_hours']:,}"
        f"（{stats['with_opening_hours'] / loaded:.2%}）← 缺失率决定 A3 离线能否断言",
        f"  有城市        {stats['with_city']:,}（{stats['with_city'] / loaded:.2%}）",
        f"  有类别        {stats['with_category']:,}（{stats['with_category'] / loaded:.2%}）",
        "",
        "署名义务（ODbL）：数据 © OpenStreetMap 贡献者，依 ODbL-1.0 提供。",
    ]
    return "\n".join(lines)


def _open_features(from_file: Path | None, url: str) -> Iterator[dict[str, Any]]:
    if from_file is not None:
        if from_file.suffix == ".zip":
            with zipfile.ZipFile(from_file) as archive:
                member = next(n for n in archive.namelist() if n.endswith(".geojson"))
                with archive.open(member) as stream:
                    yield from iter_features(stream)
        else:
            with from_file.open("rb") as stream:
                yield from iter_features(stream)
        return

    with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310
        blob = io.BytesIO(response.read())
    with zipfile.ZipFile(blob) as archive:
        member = next(n for n in archive.namelist() if n.endswith(".geojson"))
        with archive.open(member) as stream:
            yield from iter_features(stream)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.fetch_offline_data")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--from-file", type=Path, default=None, help="用本地 zip/geojson")
    parser.add_argument("--as-of", default=None, help="快照日期，默认今天")
    parser.add_argument("--limit", type=int, default=0, help="只取前 N 条（0 = 全部）")
    args = parser.parse_args(argv)

    from datetime import date

    as_of = args.as_of or date.today().isoformat()
    features = _open_features(args.from_file, args.url)
    if args.limit:
        features = (f for _, f in zip(range(args.limit), features))

    stats = build_snapshot(
        features, args.out, source="osm-hot", as_of=as_of, license_id="ODbL-1.0"
    )
    print(report(stats, args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
