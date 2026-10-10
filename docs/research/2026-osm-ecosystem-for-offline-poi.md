# OSM 生态作为离线 POI 数据源的可行性（调研）

> 调研日：2026-10-11。

## 0. 一句话结论

HOT 的中国 POI 导出**可以拿到**——762,586 个要素，GeoParquet 101 MB，**S3 直链无需鉴权**（实测 range 请求返回 `HTTP 206`），许可 ODbL 清楚。**但它的字段残缺程度决定了它不能单独支撑红线**：`opening_hours` 缺失 **98.23%**（**A3 在离线侧做不了**）、`id` **不唯一**（730,403 distinct < 762,586，**A1 的「按 ID 命中」被削弱**）、`name` 缺失 **52.03%**（近半数地点无名，`name_zh` 更是缺 89.46%）。

→ **可用作候选池的「广度」来源，不能作为断言 A1 / A3 的唯一依据。**

## 1. HOT / OSM POI 导出（中国区）

### 1.1 现有文档给的链接**不可用** ❌

`docs/research/2026-travel-data-sources.md` 里写的 `feature.data-humdata-org.ahconu.org` 实测返回 **HTTP 401 + `WWW-Authenticate: Basic realm="restricted"`**，且响应头带 `x-robots-tag: noindex, nofollow`。

```
$ curl -s -D - -o /dev/null -L https://feature.data-humdata-org.ahconu.org/m/dataset/hotosm_chn_south1_points_of_interest
HTTP/2 401
www-authenticate: Basic realm="restricted"
x-robots-tag: noindex, nofollow, nosnippet, noarchive
```

判断：`feature.` 前缀 + `ahconu.org` 是 HDX 的**功能分支/预发布环境**（feature branch 部署），不是正式站点，需要内网 Basic 认证。❌ **该链接应从文档中替换。**（2026-10-11 实测）

### 1.2 正式站点 `data.humdata.org`

`https://data.humdata.org/dataset/hotosm_chn_south1_points_of_interest` 对脚本请求返回 **HTTP 202 + `x-amzn-waf-action: challenge`**（AWS WAF 人机挑战），即**对自动化抓取设防**，但浏览器可正常访问。⚠️ 结论：链接本身大概率存在，但需人工在浏览器确认，脚本无法验证。

### 1.3 可用入口：国家粒度 POI，不是「south1」 ❌→✅

通过 HDX CKAN API（`package_search?q=name:hotosm_chn*`）确认，**中国现有 12 个 HOT 导出数据集**，全部 `license_id: hdx-odc-odbl`，最后更新 **2026-10-10**。文档里那个 `south1` 分片**已不在列**，正确入口是国家级：

| 数据集 | 链接 |
| --- | --- |
| **Points of Interest of China** | [data.humdata.org/dataset/hotosm_chn_points_of_interest](https://data.humdata.org/dataset/hotosm_chn_points_of_interest) |

其余 11 个：`cultural_places`、`sea_ports`、`airports`、`financial_services`、`populated_places`、`health_facilities`、`education_facilities`、`railways`、`waterways`、`roads`、`buildings`。

### 1.4 体量、格式、直链（**S3 直链可离线下载**）✅

数据集页被 AWS WAF 挡脚本（HTTP 202 challenge），但**资源直链在 `production-raw-data-api.s3.amazonaws.com`，公开可下、无鉴权**。`curl -I` 实测 **HTTP 200**，`Last-Modified: 2026-10-10`：

| 格式 | 体量 | 直链 |
| --- | --- | --- |
| GeoJSON (zip) | 73.1 MB | [hotosm_chn_points_of_interest_osm_geojson.zip](https://production-raw-data-api.s3.amazonaws.com/ISO3/CHN/points_of_interest/hotosm_chn_points_of_interest_osm_geojson.zip) |
| **SHP (zip)** | **99.9 MB** | [..._osm_shp.zip](https://production-raw-data-api.s3.amazonaws.com/ISO3/CHN/points_of_interest/hotosm_chn_points_of_interest_osm_shp.zip) |
| GeoPackage | 99.0 MB | [..._osm_gpkg.zip](https://production-raw-data-api.s3.amazonaws.com/ISO3/CHN/points_of_interest/hotosm_chn_points_of_interest_osm_gpkg.zip) |
| **GeoParquet** | **101.0 MB** | [points_of_interest.parquet](https://production-raw-data-api.s3.amazonaws.com/ISO3/CHN/_layers/osm/points_of_interest.parquet) |
| KML | 73.0 MB | [..._osm_kml.zip](https://production-raw-data-api.s3.amazonaws.com/ISO3/CHN/points_of_interest/hotosm_chn_points_of_interest_osm_kml.zip) |
| PMTiles | 120.9 MB | [..._osm.pmtiles](https://production-raw-data-api.s3.amazonaws.com/ISO3/CHN/points_of_interest/hotosm_chn_points_of_interest_osm.pmtiles) |

规模：**762,586 个要素**（410,838 点 / 326,591 面 / 24,234 线 / 921 多多边形 / 2 几何集合），坐标系 **EPSG:4326**，快照日期 **2026-10-09**，上游为 **Geofabrik CHN 2026-10-09**。

### 1.5 字段清单（含缺失率，来自 STAC item 元数据）✅

来源：[hotosm_chn_points_of_interest_osm_item.json](https://production-raw-data-api.s3.amazonaws.com/ISO3/CHN/points_of_interest/hotosm_chn_points_of_interest_osm_item.json)（`table:columns` 的 `oex:null_percent`）。共 27 列。

| 需求项 | 字段 | 缺失率 | 判定 |
| --- | --- | --- | --- |
| **name** | `name` | **52.03%** | ⚠️ 近半数无名；`name_latin` 50.65%，`name_zh` 89.46% 缺失 |
| **类别** | `amenity` / `man_made` / `shop` / `tourism` | 42.25% / 77.23% / 89.24% / 90.99% | ✅ 四列覆盖，但四列互斥，需自己合并 |
| **坐标** | `geom` | 0% | ✅ |
| **城市/行政区划** | `adm1_name`（省）`adm2_name`（地级市） | **1.38%** | ⚠️ 到地级市尚可；`adm3/4` **100% 为空**，**没有区县/街道** |
| 地址 | `addr_city` / `addr_street` | 97.07% / 96.33% | ❌ 不可用 |
| **opening_hours** | `opening_hours` | **98.23%** | ❌ **见第 3 节** |
| id | `id` | 0% | ✅ 但 distinct 730,403 < 762,586，**id 不唯一** ⚠️ |

（`adm0_pcode`/`adm0_name` 为 `CHN`/`China` 单值；`source` 列 100% 空。）

### 1.6 ODbL 义务 ✅

HDX 元数据 `license_id: hdx-odc-odbl`，`license_url: https://opendatacommons.org/licenses/odbl/1-0/`，STAC 里 `license: ODbL-1.0`。义务两条：

1. **署名（Attribution）**：须标明数据来源为 OpenStreetMap 及其贡献者，并指向 ODbL 许可。
2. **相同方式共享（Share-Alike）**：基于该数据产生的**衍生数据库**（Derivative Database）若对外分发，须同样以 ODbL 授权。

⚠️ 未确认的边界：**「产生的结果」（Produced Work，如渲染出的行程/地图图片、行程文本）不需要以 ODbL 授权**，只需署名——ODbL 1.0 正文明确区分 Derivative Database 与 Produced Work，但**具体到本项目输出是否算 Produced Work，属法律判断，本文不做结论**。参考：[ODbL 1.0 全文](https://opendatacommons.org/licenses/odbl/1-0/)、[OSM 署名指南](https://osmfoundation.org/wiki/Licence/Attribution_Guidelines)。

## 2. Geofabrik 中国 extract

**本次未能核实：`download.geofabrik.de` 在本环境完全不可达。**

实测 `curl https://download.geofabrik.de/asia/china-latest.osm.pbf` 返回 `HTTP 000`，**耗时 910 秒后超时**；`asia.html` 与 `china-latest.osm.pbf.md5` 同样超时。

**这是环境限制，不是「不存在」**——Geofabrik 是长期存在的公开服务。但它的体量、以及是否有省/市级细分，**本次拿不到一手数据**，所以不写结论。

→ 需要换网络环境重试；或改用 §1.4 已验证可用的 HOT S3 直链作为 OSM 数据的入口。

**依据间接证实的一点**：HOT 的中国导出**上游就是 Geofabrik CHN**（快照 2026-10-09），所以「Geofabrik 有中国数据」由 §1.4 侧面成立，缺的只是体积与细分层级。

## 3. `opening_hours` 覆盖率（关键问题）

**结论：缺失率 98.23% —— `opening_hours` 在离线 OSM 路径上支撑不了 A3。**

数据来自 STAC item 元数据的 `oex:null_percent`（见 §1.5 表），**不是我抽样估计**。

后果必须说清楚：项目的验收断言 **A3「所有停靠点在营业时间内」在离线路径上做不了**。这不是「数据质量差一点」，而是**这条断言在离线回归里没有依据**——如果不记账，就会变成一条永远通过的测试。

三条出路，按代价排序：

1. **把 A3 限定在真实路径**（走高德接口时有营业时间），并在文档里明确记账：**离线回归不覆盖 A3**。
2. **换字段更全的离线源**：`ChinaTravel-Sandbox`（CC-BY-4.0）的 attractions 与 restaurants **同时有 `opentime`/`endtime` 与 `id`**——这是目前唯一能同时支撑 A1 与 A3 的离线源，代价是只有 **10 城 / 12,172 条**。见 [2026-datasets-triptailor-chinatravel.md](./2026-datasets-triptailor-chinatravel.md)。
3. **绕过 HOT、直接解析 Geofabrik PBF** —— **覆盖率的量级不会变**：HOT 的导出上游就是 Geofabrik CHN（§1.4），同一份数据的同一个标签，换入口不增加字段。

> **本次未核实**：`opening_hours` 缺失率在不同城市/类别间的分布（98.23% 是全国均值，商圈与景区可能显著更低）。若要把 A3 做成「只在部分类别上可断言」，需要按类别重算缺失率。
