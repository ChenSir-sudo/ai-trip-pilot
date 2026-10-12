"""数据访问层的统一接口，两类实现共用。

位置：契约层。`local.py`（离线快照）与 `amap.py`（地图服务）各实现一遍；上层经
    `factory.py` 按环境变量拿到其中一份，**不知道自己拿到的是哪一份**——这是
    「演示与评测走同一条代码路径」的实现方式（architecture.md §7）。
可测试性：`Protocol` 只约束形状，**测试可以直接传一个假实现**，不需要网络也不需要
    数据集（见 tests/test_candidate_pool.py）。
不做的事：不做缓存、不做重试、不做静默降级。重试策略属于调用方（它与预算和时限有关）；
    而**降级必须是显式事件**（红线 R8 禁止静默放宽约束，数据缺失同理）。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.data.types import (
    AreaInfo,
    LatLon,
    Place,
    RouteMode,
    RouteResult,
    TrainService,
    WeatherReport,
)


@runtime_checkable
class DataAccess(Protocol):
    """六个能力。新增能力时先问：**它服务于哪条验收断言？** 答不上来的不加。"""

    def describe(self) -> str:
        """一句话说明当前实现是什么、数据有多新。

        用途：可演示产出要求「打印来源」，而**来源必须在界面上可见**（协议 7.7 的
        正向署名义务，见 docs/research/2026-amap-compliance-verify.md）。
        """
        ...

    def search_place(
        self,
        *,
        city: str,
        keywords: str | None = None,
        category: str | None = None,
        limit: int = 50,
    ) -> list[Place]:
        """按城市检索地点，返回候选地点。

        契约：
          幂等性：是（同一个快照下）。
          失败模式：上游不可用时抛 `UpstreamError`；**没有结果返回空列表**，
              不抛异常——「查到了但没有」是正常结果。

        `keywords` 与 `category` 同时给时是「与」的关系。
        """
        ...

    def resolve_place(self, *, name: str, city: str | None = None) -> Place | None:
        """把地名解析成一个带坐标的地点。

        它是候选池构建的第一步：**先用它把「杭州」变成中心点，再围绕它检索**。
        先地理编码再检索，是省配额的唯一办法（个人认证的基础搜索服务按次计费，
        见 docs/research/2026-amap-compliance-verify.md）。

        返回值：解析不到时返回 `None`，**不要造一个假坐标**。
        """
        ...

    def route(self, *, origin: LatLon, destination: LatLon, mode: RouteMode) -> RouteResult:
        """算两点之间的路线与耗时。

        契约：
          失败模式：上游算不出路线时抛 `UpstreamError`。**不要返回直线距离冒充
              路线耗时**——那是两个不同的量，混用会让 A4 的时长断言失去意义。
        """
        ...

    def weather(self, *, adcode: str, date: str) -> WeatherReport:
        """查某个行政区在某个日期的天气。

        用 `adcode` 而不是城市名：地图服务的天气接口**只认行政区划代码**，
        见 docs/research/2026-amap-mcp-integration.md §5.4。
        """
        ...

    def train_schedule(
        self, *, from_city: str, to_city: str, date: str
    ) -> list[TrainService]:
        """查两地某日的车次。

        契约：
          失败模式：**离线实现会抛 `CapabilityUnavailable`**，因为离线数据集里没有
              班次数据。返回空列表是错的——那会让上层把「没有这个能力」读成
              「当日无车」，而后者是一句凭空生成的事实。
        """
        ...

    def lookup_area(self, *, adcode: str) -> AreaInfo | None:
        """按行政区划代码查行政区的名称、层级与中心点。

        用途：候选池要知道「这个地点属于哪个城市」，才能判断某天的安排是否跨城。
        查不到返回 `None`。
        """
        ...
