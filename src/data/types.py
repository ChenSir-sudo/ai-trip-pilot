"""数据访问层的记录类型与来源标记。

位置：数据访问层的**契约层**。上层（图与外壳）只认这里的类型，不认任何具体数据源。
    两类实现（离线快照 / 地图服务）都必须返回这些类型，见 `base.py`。
可测试性：纯数据模型，无网络、无 I/O，可直接构造。
不做的事：不发请求、不读文件、不知道数据源是谁——那是各实现自己的事。

为什么这里用 Pydantic 而不是 dataclass：**上游返回的是不可信输入**。地图服务的 JSON
字段名会变、类型会漂（见 `docs/research/2026-amap-mcp-integration.md` 里地理编码
「存在时返回字符串、不存在时返回数组」），校验放在解析边界上，坏数据当场报错而不是
一路混到方案里。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Provenance(BaseModel):
    """一条事实的来源标记。

    它是产品红线 A8（每条事实带来源标记）与 R7（离线数据必须标为「示例数据」并带
    时间戳）在类型层面的落点：**没有来源的 `Place` 构造不出来**，因为 `provenance`
    是必填字段。这比「记得加来源」的纪律可靠。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str = Field(description='数据源标识，如 "amap" / "osm-hot" / "open-meteo"')
    as_of: str = Field(description="取数时间，ISO 8601。离线快照填快照日期")
    is_sample: bool = Field(description="True = 离线快照，界面必须标注「示例数据」")
    license: str = Field(description='许可标识，如 "ODbL-1.0" / "amap-terms"')


class LatLon(BaseModel):
    """一个坐标点。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lat: float
    lon: float


class Place(BaseModel):
    """一个地点。

    字段清单不是从数据源倒推的，是**从验收断言推出来的**（见 architecture.md §7.1）：
    `id` 服务于 A1（按 ID 命中）、`opening_hours` 服务于 A3、`lat`/`lon` 服务于
    A2/A4/A6、`price` 服务于 A5、`provenance` 服务于 A8 与 R7。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(description="候选池内唯一的标识；A1 按它命中")
    name: str
    lat: float
    lon: float
    category: str | None = None
    city: str | None = None
    adcode: str | None = Field(default=None, description="行政区划代码；天气接口要用它")
    opening_hours: str | None = Field(default=None, description="原始营业时间字符串")
    price: float | None = None
    provenance: Provenance

    def to_candidate(self) -> dict:
        """转成候选池里的一条记录（进图状态那一份）。

        契约：
          副作用：无。纯函数。
          幂等性：是。

        为什么摊平成 dict 而不是把模型塞进状态：状态要过 checkpointer，**嵌套的
        Pydantic 对象需要自定义序列化器**，而摊平后的 dict 在所有实现下都安全。
        这也是 `merge_candidates` 只认 `id` 键的原因。
        """
        return {
            "id": self.id,
            "name": self.name,
            "lat": self.lat,
            "lon": self.lon,
            "category": self.category,
            "city": self.city,
            "adcode": self.adcode,
            "opening_hours": self.opening_hours,
            "price": self.price,
            "source": self.provenance.source,
            "as_of": self.provenance.as_of,
            "is_sample": self.provenance.is_sample,
            "license": self.provenance.license,
        }


class RouteMode(str, Enum):
    """出行方式。取值与地图服务的接口参数同名，但不在这里做拼接。"""

    DRIVING = "driving"
    WALKING = "walking"
    TRANSIT = "transit"


class RouteBasis(str, Enum):
    """一段耗时是**怎么算出来的**。

    > 这个字段是补上的：写离线实现时才发现，离线侧只能给「直线距离 × 经验系数」，
    > 而那与路网算出来的耗时**不是同一个量**。没有这个字段，两者会在状态里混成
    > 一个数字，A4（单日移动总时长）就会拿估算值当实测值断言——**而且不报错**。
    """

    ROAD_NETWORK = "road_network"
    STRAIGHT_LINE_ESTIMATE = "straight_line_estimate"


class RouteResult(BaseModel):
    """一段路线。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    origin: LatLon
    destination: LatLon
    mode: RouteMode
    distance_m: int
    duration_s: int
    basis: RouteBasis = Field(
        description="计算依据。离线快照恒为直线估算，调用方据此决定能不能拿它断言"
    )
    provenance: Provenance


class WeatherReport(BaseModel):
    """某个行政区在某个日期的天气。

    用 `adcode` 而不是城市名做键：地图服务的天气接口**只接受行政区划代码**，
    而离线源也用同一口径，两边对齐后上层不必做转换（见 `docs/research/2026-amap-mcp-integration.md`）。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    adcode: str
    date: str
    text: str = Field(description="天气现象，如「晴」")
    temp_min_c: float | None = None
    temp_max_c: float | None = None
    provenance: Provenance


class AreaInfo(BaseModel):
    """一个行政区。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    adcode: str
    name: str
    level: str = Field(description='层级，如 "province" / "city" / "district"')
    center: LatLon | None = None
    parent_adcode: str | None = None
    provenance: Provenance


class TrainService(BaseModel):
    """一趟列车。

    本项目**离线侧没有班次数据**，所以离线实现会抛「能力不可用」而不是返回空列表
    ——两者的区别见 `errors.py` 的 `CapabilityUnavailable`。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    train_no: str
    from_station: str
    to_station: str
    depart_at: str = Field(description="发车时间，HH:MM")
    arrive_at: str = Field(description="到达时间，HH:MM")
    duration_min: int | None = None
    provenance: Provenance
