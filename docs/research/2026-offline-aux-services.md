# 离线辅助服务（天气 / 路线 / 地理编码）可得性与接口形状（调研）

> 调研日：2026-10-11。

## 0. 一句话结论

天气侧 ✅ 可用：Open-Meteo 免费层**无需 API Key**、有限但够用的配额（1 万次/天）、端点形状简单，**但免费层明确不含商用授权**，且中国境内预报依赖 CMA 源、该源官方自己标注了过载风险。路线侧 ✅ 可行但重：自建 OSRM 只需一份 Geofabrik 的 `.osm.pbf` extract + 官方 `ghcr.io` 镜像，代价在预处理时长与磁盘；对外提供服务时 OSM 的署名义务明确且门槛低（内部使用不触发）。地理编码/行政区划侧 ⚠️：Nominatim 全量自建过重；行政区划边界**有唯一一个许可完全干净的可下载来源（Natural Earth，公有领域）但它只到省级、无 adcode**；含 adcode 的现成源（DataV.GeoAtlas）**许可未确认**。→ 「中文地名 → 坐标」在离线侧只能做到行政区代表点这一档。

---

## 1. Open-Meteo（天气）

### 1.1 免费层是否需要 Key、有无调用限制

- ✅ **不需要 API Key**。免费层的调用是裸 `https://api.open-meteo.com/v1/forecast?...`，无 `apikey` 参数；付费层才在 `customer-api.open-meteo.com` 上带 `&apikey=`。来源：[Pricing](https://open-meteo.com/en/pricing)（"The API syntax is identical to the free tier — only the domain and key parameter differ"）。
- ✅ **有限制，且逐级收紧**（免费层）：600 次/分钟、5,000 次/小时、10,000 次/天、300,000 次/月。来源同上表 "Free / Open-Access" 行。
- ✅ **免费层商用列为 ❌**（表格 "Commercial use" 行，Free 列为 ❌）。免费层定位是 "for evaluation and prototyping"、"for non-commercial use ... carries no uptime guarantee"。来源同上。
- ⚠️ **「一次调用」不等于一次 HTTP 请求**：官方 FAQ 定义——请求超过 10 个天气变量、或单点时间跨度超过 2 周，按多次计（分数计数，例如 2 周 × 15 变量 = 1.5 次）。来源同上 FAQ "How is one API call defined?"。
- ⚠️ 免费层**不含** Historical Weather / Climate / Ensemble / Satellite Radiation API，这些要 Professional 档及以上；免费层含 Air Quality / Elevation / Flood / **Geocoding** / Marine。来源同上表格。

### 1.2 接口形状

- ✅ **预报端点**：`https://api.open-meteo.com/v1/forecast`
  关键参数：`latitude`、`longitude`（单点必填，也支持 `latitude=a,b,c` 多点逗号列表）、`hourly=` / `daily=` 变量清单、`timezone=Asia/Shanghai`、`forecast_days`（默认 7，最大 16）、`past_days`、`models`（官方文档列 `best_match` 会自动选该坐标最高分辨率模型）。来源：[Weather Forecast API 文档](https://open-meteo.com/en/docs)。
- ✅ **历史端点**：`https://archive-api.open-meteo.com/v1/archive`（文档中的 Historical Weather API，数据可回溯到 1940），参数为 `start_date` / `end_date`（而非 forecast_days）。来源：[Historical Weather API 文档](https://open-meteo.com/en/docs/historical-weather-api)。
- ✅ **返回字段名**（2026-10-11 直连实测，北京 39.9042/116.4074）：顶层含 `latitude`、`longitude`、`elevation`、`timezone`、`utc_offset_seconds`、`generationtime_ms`，以及**与请求同名的 unit 字典与数据字典**：`hourly_units` / `hourly` / `daily_units` / `daily`，各自带 `time` 数组（ISO8601，分钟粒度）。变量名即 `temperature_2m`、`precipitation_probability`、`weather_code`、`temperature_2m_max`、`temperature_2m_min`、`precipitation_sum`。返回坐标被**吸附到模式网格**（请求 39.9042/116.4074 → 返回 39.89455/116.35983），即解析度有限、不是任意点直读。
- ✅ **无 Key 调用成本为零**：上述三次调用均为无 Key 的裸 HTTPS GET，直接返回 200 与数据。
- ⚠️ 其他同站免费端点：`https://api.open-meteo.com/v1/elevation?latitude=&longitude=` 返回 `{"elevation":[47.0]}`（实测）；`/v1/geocoding` 见 [Geocoding API 文档](https://open-meteo.com/en/docs/geocoding-api)。

### 1.3 中国境内覆盖

- ⚠️ **预报**：`best_match` 在中国境内会落到官方列出的 **CMA 中国气象局 GFS GRAPES 全球模式**上，有专门的国别文档页。但该页顶部有一手警示：CMA 的开放数据服务近期严重过载、"nearly impossible to download forecasts reliably"，官方期待尽快修复。→ **中国境内预报可用性存在已知的上游不稳定风险，不是接口本身的问题。** 来源：[CMA Forecast API](https://open-meteo.com/en/docs/cma-api)。
- ✅ **实测可达**：2026-10-11 对北京坐标的 `v1/forecast` 与 `archive-api` 均正常返回（见 §1.2 实测），即当下没有断供。
- ⚠️ 官方对「中国境内覆盖到区县一级/精度多少」**没有给出逐国覆盖说明**；只有全球模式列表与 1–2km（区域中尺度）到 9–11km（全球）的分辨率区间描述。来源：[Pricing](https://open-meteo.com/en/pricing) "Resolution ranges from 1–2 km ... to 9–11 km"。**未确认**：中国境内哪些模式参与了 `best_match`、实际有效分辨率。

### 1.4 许可与商用限制

- ✅ **数据许可 CC BY 4.0**，强制署名（"attribution is a requirement under this licence"），允许商用与再分发，但**商用授权本身来自付费订阅**，与数据许可 CC BY 4.0 是两件事。来源：[Pricing](https://open-meteo.com/en/pricing) FAQ "Is it necessary to provide attribution to Open-Meteo?"。
- ✅ **服务端代码 AGPLv3**，可自建（"the practical path" for billions of calls）。来源同上页尾段与 [GitHub](https://github.com/open-meteo/open-meteo)。
- ✅ **署名有具体形式要求**：官方给出必须放在任何展示 Open-Meteo 数据的位置旁的链接片段 `<a href="https://open-meteo.com/">Weather data by Open-Meteo.com</a>`，并要求标注是否修改过。来源：[Licence](https://open-meteo.com/en/licence)。
- ✅ **上游数据源清单**（一手，逐条给了许可链接）：DWD、ECMWF、NOAA NCEP、CMC、Météo-France、JMA、MET Norway、**CMA 中国气象局（CC-BY）**、BOM、KNMI、DMI、UK Met Office（**CC-BY-SA**，注意与其余 CC-BY 不同）、ItaliaMeteo-ARPAE、MeteoSwiss、Copernicus Marine、C3S、GloFAS、GeoNames（CC-BY，用于地点库）、Weather Icons。来源：[Licence](https://open-meteo.com/en/licence)。
- ⚠️ **聚合层的 CC BY 4.0 不等于可以忽略上游**：UK Met Office 一条为 CC-BY-SA，若只取该源数据存在传染性条款风险；本项目只用 Open-Meteo 聚合结果时，按官方口径署 Open-Meteo 即可，但**未确认**逐条上游许可是否都需要单独署名。

---

## 2. OSRM（路线与耗时）

### 2.1 本地自建需要什么数据

- ✅ **就是 OSM extract，官方 README 直接点名 Geofabrik**：README "Quick Start / Using Docker" 一节写 `Download OpenStreetMap extracts for example from Geofabrik` + `wget http://download.geofabrik.de/europe/germany/berlin-latest.osm.pbf`。即 `.osm.pbf` 是国家/地区级 extract，不需要原始 planet。来源：[osrm-backend README](https://github.com/Project-OSRM/osrm-backend#quick-start)。
- ✅ **数据体量的量级可从官方 README 的实测推**：README 给出一个实测样点——"a Mexico's OSM file of 550.7MB took around 30 minutes to finish extraction"。即**预处理时间与 extract 体量近似线性**，550MB → 约 30 分钟。来源同上。
- ⚠️ **中国 extract 的确切体量本次未取到**（`download.geofabrik.de` 在本环境下 HEAD 请求超时）。→ **未确认**。可参照的是：中国 extract 远大于墨西哥量级，预处理需按小时计，且 MLD 产物（`.osrm.*` 系列文件）显著大于原始 pbf。
- ✅ OSRM 本体许可 **BSD-2-Clause**（`LICENSE.TXT`："Copyright (c) 2017, Project OSRM contributors ... Redistribution and use in source and binary forms, with or without modification, are permitted provided that..."，为两条款 BSD）。来源：[LICENSE.TXT](https://github.com/Project-OSRM/osrm-backend/blob/master/LICENSE.TXT)。

### 2.2 官方 Docker 镜像与启动方式

- ✅ **官方镜像托管在 GitHub Container Registry**：`ghcr.io/project-osrm/osrm-backend`（旧版本另在 Docker Hub `osrm/osrm-backend`）；前端镜像 `osrm/osrm-frontend`。来源：[README](https://github.com/Project-OSRM/osrm-backend#using-docker)。
- ✅ **两条预处理流水线**：Contraction Hierarchies（CH）与 Multi-Level Dijkstra（MLD）。官方推荐默认用 **MLD**，仅超大规模距离矩阵等特例用 CH。来源同上。
- ✅ **MLD 三步 + 起服务**（官方原样命令）：
  1. `docker run -t -v "${PWD}:/data" ghcr.io/project-osrm/osrm-backend osrm-extract -p /opt/car.lua /data/<name>.osm.pbf`
  2. `osrm-partition /data/<name>.osrm`
  3. `osrm-customize /data/<name>.osrm`
  4. `docker run -t -i -p 5000:5000 -v "${PWD}:/data" ghcr.io/project-osrm/osrm-backend osrm-routed --algorithm mld /data/<name>.osrm`
  （CH 流水线则把第 2、3 步换成单个 `osrm-contract`，启动加 `--algorithm ch`。）来源同上。
- ✅ **调用形状**：`curl "http://127.0.0.1:5000/route/v1/driving/13.388860,52.517037;13.385983,52.496891?steps=true"`。即 `/{service}/{profile}/{lon,lat};{lon,lat}?{options}`，**坐标序为 lon,lat**（与天气接口的 lat/lon 相反，易错）。来源同上。
- ✅ **可用服务**：Nearest / Route / Table / Match / Trip / Tile；HTTP API 细节见仓库 `docs/http.md`。来源：[README](https://github.com/Project-OSRM/osrm-backend#readme) 与 [docs/http.md](https://github.com/Project-OSRM/osrm-backend/blob/master/docs/http.md)。
- ✅ **镜像 tag 策略**：`latest`（master release）、`latest-assertions`、`latest-debug`、`<tag>`、`<tag>-debug`。来源同上。

### 2.3 用 OSM 数据对外提供路线服务时的许可义务

- ✅ **一手条文（OSMF 官方 Attribution Guidelines，2021-06-25 董事会通过，2026-09-10 最后编辑）中「Routing engines」小节原文要求三条**：
  1. "Routing engines that use OpenStreetMap data must credit OpenStreetMap"
  2. "Applications that incorporate such a routing engine must credit OpenStreetMap"
  3. "Routing instructions generated by such a routing engine need not maintain attribution attached to the instructions, as long as they do not form a Derivative Database"
  来源：[Licence/Attribution Guidelines § Routing engines](https://osmfoundation.org/wiki/Licence/Attribution_Guidelines#Routing_engines)。
- ✅ **署名文本与形式**：署名对象必须是 "OpenStreetMap"；必须让人看出数据按 ODbL 提供（做法是把 "OpenStreetMap" 链到 `openstreetmap.org/copyright`）；历史写法 "© OpenStreetMap contributors" 或 "© OpenStreetMap" 均可接受。来源同上 § Attribution text。
- ✅ **只在使用公开时才需要署名**："attribution is only necessary when a Produced Work is used Publicly (as defined by the ODbL). This guideline does not concern internal uses." → **纯本地/内部使用不触发署名义务**，但一旦对外可访问就需要。来源同上 § Introduction。
- ✅ **基础许可为 ODbL**：OSM 数据按 Open Database License 分发。来源同上 § Introduction。
- ⚠️ **仓库/数据层面的额外义务（若分发衍生库）**：Guidelines 的「Databases」小节要求：把 OSM 署名**和 ODbL 全文或链接**放进数据库/衍生数据库/集合数据库中，位置要放在用户会找的地方（如 readme、数据或元数据内）。→ 若把 OSRM 预处理产物或 OSM 子集随项目分发，这一条适用。来源同上 § Databases。
- ⚠️ **未确认**：OSRM 官方是否对「公开提供 demo 服务」另有限制（README 只指向 demo server，未见使用条款页）；Geofabrik 下载页的自身条款也未取到（页面请求超时）。
- ❓ **不是许可问题但需记账**：Google 风格的地理数据在中国境内受测绘法规约束，本节只论 OSM 许可，**不构成合规结论**。

---

## 3. 离线的地理编码与行政区划

### 3.1 Nominatim 自建

- ✅ **数据来源就是 OSM**，加载路径是 `nominatim import --osm-file <data file>`，底层用 **osm2pgsql** 灌进 PostgreSQL。来源：[Nominatim Manual — Import](https://nominatim.org/release-docs/latest/admin/Import/)。
- ✅ **体量与硬件（官方给出的 planet 实测基准，64GB RAM / 4 CPU / NVMe）**：
  | import style | 导入耗时 | DB 大小 | `--drop` 后 |
  |---|---|---|---|
  | **admin**（仅行政边界与地名） | **4h** | 215 GB | **20 GB** |
  | street | 22h | 440 GB | 185 GB |
  | address | 36h | 545 GB | 260 GB |
  | full（默认，含 POI） | 54h | 640 GB | 330 GB |
  | extratags | 54h | 650 GB | 340 GB |
  来源同上表格。
- ✅ **可以用小区域 extract 大幅削量**：官方推荐 "If you only need geocoding for a smaller region, then precomputed OSM extracts are a good way to reduce the database size and import time"，并点名 **Geofabrik** 提供多数国家的 extract 与每日更新。来源同上 § Using an extract。
- ✅ **对 `lookup_area` 这类需求有专门的裁剪开关**：`NOMINATIM_IMPORT_STYLE=admin` 只导入行政边界与地名。→ **行政区划查询不需要 full style**。来源同上 § Filtering Imported Data。
- ✅ **内存硬约束**：osm2pgsql 至少要 2GB RAM 给内部结构；不做 flatnode 时 `--osm2pgsql-cache` 建议设成 **pbf 文件大小（MB）**；大区域（欧洲/北美/planet）建议启用 flatnode 文件，**该文件目录需至少 75GB 空闲空间**。来源同上 § Notes on memory usage 与 § Flatnode files。
- ⚠️ **extract 边界不精确的已知陷阱**：官方明确警告 "some extracts are not cut exactly along the country boundaries. As a result some parts of the boundary may be missing which means that Nominatim cannot compute the areas for some administrative areas." → **用中国 extract 时，国境线附近的行政区面积计算可能残缺**，这会直接影响「某坐标属于哪个行政区」的判定。来源同上 § Using an extract。
- ⚠️ **中文检索能力未确认**：Nominatim 支持按 country 定制 tokenizer（[Country Settings](https://nominatim.org/release-docs/latest/customize/Country-Settings/) 与 [Tokenizers](https://nominatim.org/release-docs/latest/customize/Tokenizers/) 页面存在），但**中国的中文分词配置效果本次未实测、未确认**。OSM 中的中国地名以中文 `name` 为主，英文 `name:en` 覆盖不完整——这会决定 `resolve_place("西湖")` 这类查询能不能命中，**未确认**。
- ✅ Nominatim 本体为 **GPLv2**（未在本次抓取范围内复核，标注为**未确认**）。
- ⚠️ **可行性判断（不含方案建议，仅陈述可算出的量级关系）**：只做行政区划 + 地名（admin style）时，planet 级产物是 20GB / 4h；但**中国单国 extract 的 admin-style 产物大小本次未取到**，因为 Geofabrik 页面在本环境下不可达（见 §4）。

### 3.2 中国行政区划边界数据（含名称与层级 / adcode 或等价标识）

| 来源 | 许可 | 含名称/层级 | 含 adcode 或等价物 | 链接 |
|---|---|---|---|---|
| ✅ Natural Earth Admin-1 | **公有领域** | ✅ 中文名（GeoDB 格式保留本地文字） | ❌ 仅 FIPS/ISO/HASC | [下载](https://www.naturalearthdata.com/downloads/10m-cultural-vectors/10m-admin-1-states-provinces/)｜[许可](https://www.naturalearthdata.com/about/terms-of-use/) |
| ⚠️ OSM 行政边界（Geofabrik / Overpass） | ✅ **ODbL** | ✅ 中文 `name` | ❓ 未确认 | [wiki](https://wiki.openstreetmap.org/wiki/China/Boundaries) |
| ❓ DataV.GeoAtlas（阿里云） | ❓ 未确认 | ✅ 中文 `name` | ✅ **有 `adcode`** | [页面](https://datav.aliyun.com/portal/school/atlas/area_selector) |
| ⚠️ `modood/Administrative-divisions-of-China` | 仓库 **WTFPL**，数据许可另论 | ✅ | ✅ 统计局代码 | [repo](https://github.com/modood/Administrative-divisions-of-China) |
| ⚠️ `xiangyuecn/AreaCity-JsSpider-StatsGov` | 仓库 **MIT**，**数据混合高德/腾讯** | ✅ | ✅ | [repo](https://github.com/xiangyuecn/AreaCity-JsSpider-StatsGov) |
| ❓ 统计局区划代码 / 民政部平台 / GADM | ❓ 未确认 | — | — | 见下 |

- ✅ **Natural Earth 许可原文**："All versions of Natural Earth raster + vector map data found on this website are in the public domain... No permission is needed to use Natural Earth. Crediting the authors is unnecessary."（**唯一一个许可完全清楚、无需署名的来源**。）局限：**只到 admin-1（省级）**，属性为 "name attributes (including diacritical marks), name variants, and some statistical codes (FIPS, ISO, HASC)"，**无 adcode、无地级/县级**；且官方声明默认采用 **de facto（实际控制）边界**，可另选 POV worldview 多边形。来源：[Terms of Use](https://www.naturalearthdata.com/about/terms-of-use/)、[Admin 1 页面](https://www.naturalearthdata.com/downloads/10m-cultural-vectors/10m-admin-1-states-provinces/)。
- ✅ **DataV.GeoAtlas 接口实测形状**（2026-10-11 直连 `https://geo.datav.aliyun.com/areas_v3/bound/110000_full.json`）：FeatureCollection，每个 feature 的 `properties` 为 `{"adcode":110101,"name":"东城区","center":[116.418757,39.917544],"centroid":[...],"childrenNum":0,"level":"district","parent":{"adcode":110000},"subFeatureIndex":0,"acroutes":[100000,110000]}`。→ **名称、层级、adcode、代表点齐全，形状正合 `lookup_area` 所需**。
- ❓ **但 DataV 的许可未确认**：`datav.aliyun.com` 该页是纯客户端 JS 应用，本次抓取只得到标题、**未取到任何许可或使用条款文本**。→ **不得据此认为可自由使用或可商用。**
- ⚠️ **两个 GitHub 镜像仓库的许可只覆盖代码，不覆盖数据**：`modood/...` 为 **WTFPL**、`xiangyuecn/...` 为 **MIT**（均经 GitHub API `/repos/...` 的 `license.spdx_id` 确认）；但后者的仓库自述其数据"综合了中华人民共和国民政部、中国•国家地名信息库、统计局、**高德地图、腾讯地图**行政区划数据"。→ **数据来源混入商业地图，数据许可不明**。
- ❓ **三个未取到的来源**：① **国家统计局**「统计用区划和城乡划分代码」（`stats.gov.cn/sj/tjbz/tjyqhdmhcxhfdm/`）——adcode 的权威出处，本次请求返回 **HTTP 403（WAF 拦截）**，且未见开放许可声明；② **民政部全国行政区划信息查询平台**——本次搜索超时，未确认；③ **GADM**（常被引用的全球 4 级边界集）——`gadm.org` 两次请求均超时（HTTP=000），**许可文本未确认**；GADM 历来对商用另有限制，**在取到一手条文前不应假设可商用**。

### 3.3 离线侧能做到什么程度

- ✅ **`lookup_area`（坐标 → 行政区划）**：可行但精度取决于选源。Natural Earth 只能回到**省级**；回到**地级/县级**需要 OSM admin 边界（ODbL，需自建 Nominatim 或直接读 pbf 的 boundary 关系）或 DataV GeoAtlas（**许可未确认**）。跨城判断所需的「城市归属」在这一档可以满足，前提是接受所选来源的许可。
- ⚠️ **`resolve_place`（中文地名 → 坐标）**：离线侧**做不到公网 Nominatim 的质量**。能明确做到的是**行政区名 → 代表点**（DataV 的 `center`/`centroid` 字段正是此形状；Natural Earth 无代表点字段）。**景区/POI 级中文地名**（如"西湖""拙政园"）需要一个带中文名称的 POI 数据集，本次调研**未找到许可明确且含中文名称的可下载 POI 数据集**——这一项超出本文件范围，不重复此前 `2026-travel-data-sources.md` 的结论。
- ⚠️ **自建 Nominatim 在理论上能覆盖上述两者**，但代价与不确定性见 §3.1：planet admin-style 为 20GB / 4h（64GB RAM 基准）；中国 extract 的 admin-style 体量**未取到**；中文分词效果**未实测**。
- ⚠️ **与 `architecture.md` 的字段缺口记账对齐**：本节只回答了「城市归属/行政区划能否在离线侧补上」——答案是**能补，但三个候选中两个（DataV、GADM）许可未确认，唯一许可干净的 Natural Earth 只到省级**。**营业时间**缺口本节未涉及，仍为未解。

---

## 4. 未确认事项（明确列出，避免被当成结论）

- ❓ Geofabrik 中国 extract 的**确切体积**与 Geofabrik 自身的使用条款（`download.geofabrik.de` 在本环境所有请求均超时/空响应）。
- ❓ DataV.GeoAtlas 的**许可与商用条件**（页面未渲染出任何条款文本）。
- ❓ GADM 的**许可文本**（站点不可达）；商用是否需授权。
- ❓ 国家统计局面分类代码的**许可**（403 拦截）。
- ❓ OSM 中国行政边界关系上**是否带 adcode 或等价 `ref` 标签**（Overpass 查询返回 500，OSM wiki 页超时）。
- ❓ Nominatim 的**中文检索/分词实际效果**；Nominatim 本体的许可证文本（未复核）。
- ❓ Open-Meteo 在中国境内 `best_match` 实际参与的模式与有效分辨率。
- ❓ OSRM 官方是否对公开提供 demo 服务另有限制条款。
- ❓ 本文件**只论数据与软件许可**，不涉及中国境内测绘/地图服务的行政合规结论。

---


