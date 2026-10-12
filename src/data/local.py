"""离线数据访问实现：读一个本地 SQLite 快照。

位置：数据访问层的**离线实现**。用于开发、回归评测、CI 与断网环境；它是
    「演示与评测走同一条代码路径」里评测的那条（architecture.md §7）。
可测试性：只读 SQLite，无网络。测试用临时库构造夹具，不需要真数据集。
不做的事：不下载、不写库、不联网。**取数（抓快照）是 `scripts/fetch_offline_data.py`
    的职责**——把「有数据」和「用数据」分开，测试才不需要 101MB 的下载。

数据来源与许可写在快照的 `meta` 表里，并**逐条随记录带出**（`Provenance`）。
本项目不把任何数据集入仓库，快照目录在 `.gitignore` 里。
"""

from __future__ import annotations

import math
import sqlite3
from pathlib import Path

from src.data.errors import CapabilityUnavailable, UpstreamError
from src.data.types import (
    AreaInfo,
    LatLon,
    Place,
    Provenance,
    RouteBasis,
    RouteMode,
    RouteResult,
    TrainService,
    WeatherReport,
)

# 快照的表结构。抓取脚本与测试夹具**共用这一份**，避免两处维护必然分叉。
SCHEMA_SQL = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE places (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    lat           REAL NOT NULL,
    lon           REAL NOT NULL,
    category      TEXT,
    city          TEXT,
    adcode        TEXT,
    opening_hours TEXT,
    price         REAL
);
CREATE INDEX idx_places_city ON places(city);
CREATE INDEX idx_places_category ON places(category);
CREATE TABLE areas (
    adcode        TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    level         TEXT NOT NULL,
    lat           REAL,
    lon           REAL,
    parent_adcode TEXT
);
CREATE TABLE weather (
    adcode     TEXT NOT NULL,
    date       TEXT NOT NULL,
    text       TEXT NOT NULL,
    temp_min_c REAL,
    temp_max_c REAL,
    PRIMARY KEY (adcode, date)
);
"""

# 直线估算用的系数：`(绕行系数, 平均速度 km/h)`。
#
# ⚠️ **这三个数字未标定**——它们不是从任何数据测出来的，只是让离线路径能跑通的
# 量级假设。项目汇报纪律要求「没测过的写未测」，所以这里明确记为**未测**：
# **不得拿离线耗时做任何结论性的时长结论**（A4 只能跑通、不能当证据）。
# 要让它有资格当证据，得换成 OSRM 实测，见 docs/research/2026-offline-aux-services.md。
_ESTIMATE_FACTORS: dict[RouteMode, tuple[float, float]] = {
    RouteMode.DRIVING: (1.35, 30.0),
    RouteMode.WALKING: (1.20, 4.5),
    RouteMode.TRANSIT: (1.40, 22.0),
}

_EARTH_RADIUS_M = 6_371_000.0


def haversine_m(a: LatLon, b: LatLon) -> float:
    """两点间大圆距离（米）。纯函数。"""
    lat1, lon1, lat2, lon2 = map(math.radians, (a.lat, a.lon, b.lat, b.lon))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(h))


class LocalSnapshotRepository:
    """从本地 SQLite 快照取数。"""

    def __init__(self, snapshot: Path | str) -> None:
        """契约：
          副作用：打开一个只读连接（惰性，每次查询现开）。
          失败模式：快照不存在或 `meta` 表不完整时抛 `UpstreamError`——**配置问题
              要在构造时就说清楚**，不要拖到第一次查询时报一个无关的 SQL 错。
        """
        self._path = Path(snapshot)
        if not self._path.exists():
            raise UpstreamError(
                f"离线快照不存在：{self._path}。"
                "先运行 python -m scripts.fetch_offline_data 抓一份。"
            )
        try:
            self._meta = self._read_meta()
        except sqlite3.DatabaseError as exc:
            raise UpstreamError(f"离线快照不是可用的 SQLite 库：{self._path}（{exc}）") from exc
        for required in ("source", "as_of", "license"):
            if required not in self._meta:
                raise UpstreamError(f"离线快照缺少 meta.{required}：{self._path}")

    # ── 内部 ────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{self._path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def _read_meta(self) -> dict[str, str]:
        with self._connect() as conn:
            return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM meta")}

    def _provenance(self) -> Provenance:
        """快照里每一条事实的来源。

        `is_sample=True` 是**硬编码**的，不是读出来的：这一层存在的意义就是离线快照，
        **没有哪个快照记录会被当成实时数据**（红线 R7）。
        """
        return Provenance(
            source=self._meta["source"],
            as_of=self._meta["as_of"],
            is_sample=True,
            license=self._meta["license"],
        )

    # ── 六个能力 ────────────────────────────────────────────────────

    def describe(self) -> str:
        """一句话说明当前实现。

        契约：无副作用（只读一次计数）。**这句话会被打印给用户**，并按红线 R7
        带上「示例数据」与快照日期。
        """
        with self._connect() as conn:
            n = conn.execute("SELECT COUNT(*) AS c FROM places").fetchone()["c"]
        return (
            f"离线快照 {self._meta['source']}（快照日 {self._meta['as_of']}，"
            f"{n:,} 个地点，许可 {self._meta['license']}）——**示例数据，非实时**"
        )

    def search_place(
        self,
        *,
        city: str,
        keywords: str | None = None,
        category: str | None = None,
        limit: int = 50,
    ) -> list[Place]:
        """契约补充：`keywords` 与 `category` 至少给一个。

        离线侧本来两者都不给也能列出整城，但**真实侧的上游接口要求二选一必填**，
        所以这里同样拒绝——否则同一个调用会在两份实现上表现不同。
        """
        if not keywords and not category:
            raise ValueError("检索要求 keywords 与 category 至少给一个（契约见 base.py）")
        if limit <= 0:
            return []

        sql = "SELECT * FROM places WHERE city = ?"
        args: list[object] = [city]
        if keywords:
            sql += " AND name LIKE ?"
            args.append(f"%{keywords}%")
        if category:
            sql += " AND category = ?"
            args.append(category)
        # 没有名次概念，用 id 定序：**让同一份快照下的结果可复现**，
        # 否则回归评测每次拿到的候选顺序都不一样。
        sql += " ORDER BY id LIMIT ?"
        args.append(limit)

        with self._connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [self._place(r) for r in rows]

    def resolve_place(self, *, name: str, city: str | None = None) -> Place | None:
        """先查地点表，再退回行政区表。

        顺序是刻意的：地点表里有坐标更准的 POI；行政区表只有中心点。
        **返回 `None` 而不是编一个坐标**——编出来的中心点会让后续所有距离都错。
        """
        sql = "SELECT * FROM places WHERE name = ?"
        args: list[object] = [name]
        if city:
            sql += " AND city = ?"
            args.append(city)
        sql += " ORDER BY id LIMIT 1"
        with self._connect() as conn:
            row = conn.execute(sql, args).fetchone()
            if row is not None:
                return self._place(row)
            area = conn.execute(
                "SELECT * FROM areas WHERE name = ? ORDER BY adcode LIMIT 1", (name,)
            ).fetchone()

        if area is None or area["lat"] is None or area["lon"] is None:
            return None
        return Place(
            id=f"area:{area['adcode']}",
            name=area["name"],
            lat=area["lat"],
            lon=area["lon"],
            category="行政区中心",
            city=area["name"],
            adcode=area["adcode"],
            provenance=self._provenance(),
        )

    def route(self, *, origin: LatLon, destination: LatLon, mode: RouteMode) -> RouteResult:
        """用直线距离 × 未标定系数估算。

        > **它返回的 `basis` 是 `STRAIGHT_LINE_ESTIMATE`，不是路网结果。** 这是本实现
        > 与真实实现最大的差别，也是 A4 断言必须看 `basis` 的原因——**否则会拿估算值
        > 当实测值断言，而且不报错**。系数未标定，见上方 `_ESTIMATE_FACTORS` 的说明。
        """
        straight = haversine_m(origin, destination)
        detour, speed_kmh = _ESTIMATE_FACTORS[mode]
        distance = straight * detour
        duration_s = int(distance / (speed_kmh * 1000 / 3600))

        return RouteResult(
            origin=origin,
            destination=destination,
            mode=mode,
            distance_m=int(distance),
            duration_s=duration_s,
            basis=RouteBasis.STRAIGHT_LINE_ESTIMATE,
            provenance=self._provenance(),
        )

    def weather(self, *, adcode: str, date: str) -> WeatherReport:
        """读快照里的天气。

        快照里没有的日期**返回空值会误导**，所以抛 `CapabilityUnavailable` ——
        「这个快照没覆盖那天」与「那天没有天气」是两件事。
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM weather WHERE adcode = ? AND date = ?", (adcode, date)
            ).fetchone()
        if row is None:
            raise CapabilityUnavailable(
                f"离线快照没有 {adcode} 在 {date} 的天气记录。"
                "这表示快照未覆盖该日期，不表示那天没有天气。"
            )
        return WeatherReport(
            adcode=row["adcode"],
            date=row["date"],
            text=row["text"],
            temp_min_c=row["temp_min_c"],
            temp_max_c=row["temp_max_c"],
            provenance=self._provenance(),
        )

    def train_schedule(
        self, *, from_city: str, to_city: str, date: str
    ) -> list[TrainService]:
        """恒抛 `CapabilityUnavailable`。

        **这不是「还没实现」，是刻意的能力边界**：离线侧没有合规的班次数据源
        （12306 无官方接口，社区实现有风控风险，见 2026-amap-mcp-integration.md §6）。
        返回空列表会让上层把「没有这个能力」读成「当日无车」。
        """
        raise CapabilityUnavailable(
            "离线快照不含班次数据；班次只在真实实现里可用。"
            "不要把本异常当成「当日无车」——那是两个不同的事实。"
        )

    def lookup_area(self, *, adcode: str) -> AreaInfo | None:
        """按行政区划代码查行政区。

        契约：
          失败模式：查不到返回 `None`。**离线快照的 `areas` 表通常是空的**——
              离线侧没有许可明确的行政区划来源（见 data/README.md），此时本方法
              恒返回 `None`。这**不是**能力边界：能力是有的，只是没有数据。
        """
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM areas WHERE adcode = ?", (adcode,)).fetchone()
        if row is None:
            return None
        center = (
            LatLon(lat=row["lat"], lon=row["lon"])
            if row["lat"] is not None and row["lon"] is not None
            else None
        )
        return AreaInfo(
            adcode=row["adcode"],
            name=row["name"],
            level=row["level"],
            center=center,
            parent_adcode=row["parent_adcode"],
            provenance=self._provenance(),
        )

    # ── 行 → 记录 ───────────────────────────────────────────────────

    def _place(self, row: sqlite3.Row) -> Place:
        return Place(
            id=row["id"],
            name=row["name"],
            lat=row["lat"],
            lon=row["lon"],
            category=row["category"],
            city=row["city"],
            adcode=row["adcode"],
            opening_hours=row["opening_hours"],
            price=row["price"],
            provenance=self._provenance(),
        )
