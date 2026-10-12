"""真实数据访问实现：高德 Web 服务 REST 接口。

位置：数据访问层的**真实实现**。用于演示与抽样验证（architecture.md §7）。
可测试性：**取数函数是注入的**（`Fetcher`）。测试传一个记录调用并返回预置响应的
    假函数，因此全部离线；真实实现只是把这个函数换成 httpx 版本。
不做的事：**不缓存、不落库、不重试**。前两条不是风格问题——高德协议禁止在平台外
    缓存或存储其内容，见 docs/research/2026-amap-compliance-verify.md §5 第 1 条。

为什么走 REST 而不是官方 MCP：托管端**不公布工具 schema**，唯一的 schema 材料是
官方 npm 包（2025-04 发布，包内有两处拼写缺陷）；而 REST 的参数与返回字段已在官方
文档里核到字段级。取舍过程见 docs/research/2026-amap-mcp-integration.md。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from src.data.errors import CapabilityUnavailable, MissingCredential, UpstreamError
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

BASE_URL = "https://restapi.amap.com"
SOURCE = "amap"
LICENSE = "amap-terms"

# 官方建议 `offset` 不超过 25；同参数翻页最多 200 条。
_PAGE_SIZE = 25
_MAX_PAGES = 4  # 100 条，远低于 200 的硬顶，也照顾到基础搜索服务的月配额

# 我们的类别词表 → 高德 `types` 参数用的中文类别名。
#
# 官方文档写 `types` 接受「六位分类代码**或汉字**」，所以传中文是在契约内的；
# 但**「哪个中文词对应哪一类」是我们自己的映射，没有与高德的分类表逐个核对过**。
# 它是已知的待核实项（与 2026-amap-mcp-integration.md §7 的 ❓ 并列，需要有效 key
# 才能闭合）。映射错了的表现是「检索结果为空」而**不是报错**——所以真实路径的
# 类别检索在核实前不应被当作已验证的能力。
_CATEGORY_TO_TYPES: dict[str, str] = {
    "attraction": "风景名胜",
    "museum": "科教文化服务",
    "restaurant": "餐饮服务",
    "hotel": "住宿服务",
}

# 已核到字段级的端点。**不在这个集合里的端点一律不实现**——凭空按记忆写参数，
# 会得到「代码看起来对、上游其实不认」的假实现。
_VERIFIED = {
    "v3/place/text",
    "v3/geocode/geo",
    "v3/direction/driving",
    "v3/direction/walking",
    "v3/weather/weatherInfo",
}

# 取数函数的契约：给定完整 URL 与查询参数，返回已解析的 JSON 对象；
# 传输层失败时抛 `UpstreamError`（**由实现负责转换，调用方不必处理 httpx 的异常类型**）。
Fetcher = Callable[[str, dict[str, str]], dict[str, Any]]


def make_httpx_fetcher(timeout: float = 10.0) -> Fetcher:
    """造一个基于 httpx 的取数函数。"""

    def fetch(url: str, params: dict[str, str]) -> dict[str, Any]:
        try:
            response = httpx.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise UpstreamError(f"请求高德失败：{type(exc).__name__}: {exc}") from exc

    return fetch


def _optional_str(value: Any) -> str | None:
    """把可能缺失的字符串字段读成 `str | None`。

    > 这是高德的一个**已知类型陷阱**，官方原文：「部分返回值当返回值存在时，将以
    > 字符串类型返回；当返回值不存在时，则以数组类型返回。」
    > 直接 `.strip()` 会在字段缺失时抛 `AttributeError`——**而字段缺失是常态，
    > 不是上游故障**。把常态当异常处理会让错误处理逻辑整个跑偏。
    """
    if isinstance(value, str):
        return value or None
    return None


def _location(raw: Any) -> LatLon | None:
    """解析高德的 `"经度,纬度"`。

    > **注意顺序是「经度在前」**，与其他接口常见的 lat,lon 相反。写反了不会报错，
    > 只会让所有距离都离谱——而那种错误在没有断言的地方看不出来。
    """
    text = _optional_str(raw)
    if not text or "," not in text:
        return None
    lon_s, lat_s = text.split(",", 1)
    try:
        return LatLon(lat=float(lat_s), lon=float(lon_s))
    except ValueError:
        return None


class AmapRepository:
    """高德 Web 服务的实现。"""

    def __init__(
        self,
        api_key: str,
        *,
        fetch: Fetcher | None = None,
        timeout: float = 10.0,
    ) -> None:
        """契约：
          失败模式：`api_key` 为空时抛 `MissingCredential`——**这是配置问题，
              要在构造时就说，而不是等第一次请求被上游拒绝**。
        """
        if not api_key or not api_key.strip():
            raise MissingCredential(
                "缺少高德 Web 服务 Key。在 .env 里填 AMAP_API_KEY（见 .env.example）。"
            )
        self._key = api_key.strip()
        self._fetch = fetch or make_httpx_fetcher(timeout)

    # ── 内部 ────────────────────────────────────────────────────────

    def _provenance(self) -> Provenance:
        return Provenance(
            source=SOURCE,
            as_of=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            is_sample=False,
            license=LICENSE,
        )

    def _call(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        if path not in _VERIFIED:
            raise ValueError(
                f"端点 {path} 未核到字段级，不实现。"
                "要么先把它核实并加进 _VERIFIED，要么明确抛 CapabilityUnavailable。"
            )
        payload = self._fetch(f"{BASE_URL}/{path}", {**params, "key": self._key, "output": "JSON"})

        if payload.get("status") != "1":
            code, info = _optional_str(payload.get("infocode")), _optional_str(payload.get("info"))
            # 10001 = INVALID_USER_KEY。**这是本次唯一实测拿到的错误码**：无 key 请求
            # 托管端返回的就是它（见 2026-amap-mcp-integration.md §1.4）。映射成
            # 「缺凭据」而不是「上游故障」，因为要做的事完全不同：去填 .env，不是查状态页。
            if code == "10001":
                raise MissingCredential(f"高德拒绝了这个 Key（{code} {info}）")
            raise UpstreamError(f"高德返回错误 {code} {info}（{path}）")
        return payload

    # ── 六个能力 ────────────────────────────────────────────────────

    def describe(self) -> str:
        """一句话说明当前实现。

        契约：无副作用。**这句话会被打印给用户**，所以它同时承担协议 7.7 条要求的
        来源署名——「来源必须可见」在这里落地。
        """
        return "高德 Web 服务（实时调用，不缓存）——数据版权归高德所有"

    def search_place(
        self,
        *,
        city: str,
        keywords: str | None = None,
        category: str | None = None,
        limit: int = 50,
    ) -> list[Place]:
        """关键字或类型检索，翻页直到取够或上游没有更多。

        契约补充：**高德要求 `keywords` 与 `category` 至少给一个**（官方「二选一必填」）。
        这条约束是实现第二份实现时才发现的——离线实现两者都不给也能列出整城，
        于是契约漏了它。现在两份实现都拒绝「一个都不给」。
        """
        if not keywords and not category:
            raise ValueError("高德的检索接口要求 keywords 与 category 至少给一个")
        if limit <= 0:
            return []

        params: dict[str, str] = {
            "city": city,
            "citylimit": "true",
            "offset": str(_PAGE_SIZE),
            # `extensions=all` 是**必需的**：`adcode` / `cityname` / `pcode` 只有它才返回，
            # 而「这个地点属于哪个城市」要用 adcode 判断。
            "extensions": "all",
        }
        if keywords:
            params["keywords"] = keywords
        if category:
            mapped = _CATEGORY_TO_TYPES.get(category)
            if mapped is None:
                # **不把未映射的类别原样传下去**：高德不认识英文标签，结果会是
                # 一片空——而「没有这类地点」与「这个词高德不认」是两件事。
                raise CapabilityUnavailable(
                    f"类别 {category!r} 没有对应的中文类型名，不能拿它去查高德。"
                    f"已知映射：{sorted(_CATEGORY_TO_TYPES)}"
                )
            params["types"] = mapped

        found: list[Place] = []
        for page in range(1, _MAX_PAGES + 1):
            params["page"] = str(page)
            payload = self._call("v3/place/text", params)
            pois = payload.get("pois") or []
            if not isinstance(pois, list) or not pois:
                break
            found.extend(self._place(p) for p in pois if isinstance(p, dict))
            if len(found) >= limit or len(pois) < _PAGE_SIZE:
                break

        return found[:limit]

    def resolve_place(self, *, name: str, city: str | None = None) -> Place | None:
        """地理编码。查不到返回 `None`，**不编坐标**。"""
        params = {"address": name}
        if city:
            params["city"] = city
        payload = self._call("v3/geocode/geo", params)
        geocodes = payload.get("geocodes") or []
        if not isinstance(geocodes, list) or not geocodes:
            return None

        first = geocodes[0]
        if not isinstance(first, dict):
            return None
        point = _location(first.get("location"))
        if point is None:
            return None

        adcode = _optional_str(first.get("adcode"))
        return Place(
            id=f"{SOURCE}:geo:{adcode or 'unknown'}:{point.lon},{point.lat}",
            name=name,
            lat=point.lat,
            lon=point.lon,
            category=_optional_str(first.get("level")),
            city=_optional_str(first.get("city")),
            adcode=adcode,
            provenance=self._provenance(),
        )

    def route(self, *, origin: LatLon, destination: LatLon, mode: RouteMode) -> RouteResult:
        """驾车或步行路径规划。

        契约：`TRANSIT` 抛 `CapabilityUnavailable`——公交接口需要 `city` 与 `cityd`
        两个参数，而**当前接口签名里没有它们**。缺参数就少传、让上游按默认城市猜，
        会得到一条看起来正常、实际属于别的城市的公交方案。
        """
        if mode is RouteMode.TRANSIT:
            raise CapabilityUnavailable(
                "公交路径规划需要 city 与 cityd 参数，当前接口签名没有携带它们。"
                "补齐签名后再实现——用错误的城市参数会返回一条误导性的方案。"
            )

        path = {
            RouteMode.DRIVING: "v3/direction/driving",
            RouteMode.WALKING: "v3/direction/walking",
        }[mode]
        params = {
            "origin": f"{origin.lon},{origin.lat}",
            "destination": f"{destination.lon},{destination.lat}",
            # strategy=10 = 躲避拥堵 + 路程较短，对齐高德 APP 的默认策略。
            "strategy": "10",
            "extensions": "base",
        }
        payload = self._call(path, params)
        paths = ((payload.get("route") or {}).get("paths")) or []
        if not isinstance(paths, list) or not paths:
            raise UpstreamError(f"高德没有返回可用路径（{path}）")

        first = paths[0]
        try:
            distance = int(first["distance"])
            duration = int(first["duration"])
        except (KeyError, TypeError, ValueError) as exc:
            raise UpstreamError(f"路径响应缺少 distance/duration：{exc}") from exc

        return RouteResult(
            origin=origin,
            destination=destination,
            mode=mode,
            distance_m=distance,
            duration_s=duration,
            basis=RouteBasis.ROAD_NETWORK,
            provenance=self._provenance(),
        )

    def weather(self, *, adcode: str, date: str) -> WeatherReport:
        """预报天气。`city` **只能传 adcode**——这是官方明确要求的。"""
        payload = self._call("v3/weather/weatherInfo", {"city": adcode, "extensions": "all"})
        forecasts = payload.get("forecast") or []
        if not isinstance(forecasts, list) or not forecasts:
            raise UpstreamError(f"高德没有返回 {adcode} 的预报")

        for cast in (forecasts[0].get("casts") or []):
            if isinstance(cast, dict) and cast.get("date") == date:
                return WeatherReport(
                    adcode=adcode,
                    date=date,
                    text=_optional_str(cast.get("dayweather")) or "未知",
                    temp_min_c=_as_float(cast.get("nighttemp")),
                    temp_max_c=_as_float(cast.get("daytemp")),
                    provenance=self._provenance(),
                )
        raise CapabilityUnavailable(
            f"高德的预报只覆盖未来数日，没有 {date} 的记录。"
            "这不表示那天没有天气——历史天气要换数据源。"
        )

    def train_schedule(
        self, *, from_city: str, to_city: str, date: str
    ) -> list[TrainService]:
        """恒抛 `CapabilityUnavailable`。

        **不是「还没做」**：12306 官方从未向第三方开放接口（官方多次声明），
        社区实现有风控与失效风险，高德也不提供班次。见
        docs/research/2026-amap-mcp-integration.md §6。
        """
        raise CapabilityUnavailable(
            "高德不提供列车班次，12306 也没有官方接口。"
            "班次要等一个显式的、失败可降级的接入口，不要用空列表糊过去。"
        )

    def lookup_area(self, *, adcode: str) -> AreaInfo | None:
        """恒抛 `CapabilityUnavailable`。

        **因为行政区划接口的契约没有核到字段级。** `_VERIFIED` 里没有它，而按记忆
        猜参数会写出「看起来对、上游其实不认」的实现。候选池当前不需要它：
        `search_place` 的响应在 `extensions=all` 下已经带 `adcode` 与 `cityname`。
        """
        raise CapabilityUnavailable(
            "高德行政区划查询的参数与返回字段尚未核到一手文档。"
            "需要时先补核实，再把它加进 _VERIFIED。"
        )

    # ── 解析 ────────────────────────────────────────────────────────

    def _place(self, poi: dict[str, Any]) -> Place:
        point = _location(poi.get("location"))
        if point is None:
            raise UpstreamError(f"POI 缺少可用坐标：{poi.get('name')!r}")

        poi_id = _optional_str(poi.get("id"))
        if not poi_id:
            raise UpstreamError(f"POI 缺少 id，A1 无法按 ID 命中：{poi.get('name')!r}")

        return Place(
            id=f"{SOURCE}:{poi_id}",
            name=_optional_str(poi.get("name")) or "(无名)",
            lat=point.lat,
            lon=point.lon,
            category=_optional_str(poi.get("type")),
            city=_optional_str(poi.get("cityname")),
            adcode=_optional_str(poi.get("adcode")),
            provenance=self._provenance(),
        )


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
