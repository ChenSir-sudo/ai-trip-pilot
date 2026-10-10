# TripTailor 与 ChinaTravel 数据集可行性核实（调研）

> 调研日：2026-10-11。

## 0. 一句话结论

**TripTailor 的数据集是公开可下载的**（GitHub `swxkfm/TripTailor` 根目录 `data.7z`，18.9 MB，已实测下载解压，5,622 景点 / 422,120 餐厅 / 89,224 酒店 / 40 城，**景点表含 `poiId` 与 `opening_hours`，餐厅与酒店表两者都没有**），**但整个仓库没有任何许可声明，按未授权对待**；**ChinaTravel 的 HuggingFace 主仓库根本不是 POI 数据、而是 query（对话/评测）数据集**，结构化 POI 在其**另一个**配套仓库 `LAMDA-NeSy/ChinaTravel-Sandbox`（仅 **12,172 条 POI、10 城**，但字段更全：id/坐标/类别/价格/营业时间俱全），**两仓库实际许可均为 CC-BY-4.0，而非现有文档所写的 CC-BY-NC-SA-4.0**。

---

## 1. TripTailor（ACL 2025 Findings）

论文：*TripTailor: A Real-World Benchmark for Personalized Travel Planning*，arXiv 2508.01432，官方页面 [ar5iv 全文](https://ar5iv.labs.arxiv.org/html/2508.01432) / [ACL Anthology PDF](https://aclanthology.org/2025.findings-acl.503.pdf)。

### 1.1 是否公开可下载

- ✅ **论文正文明确给出数据集发布地址**：`Our code and dataset are available at https://github.com/swxkfm/TripTailor.`（一手：论文摘要脚注，见上方 ar5iv 链接）。
- ✅ **结论：公开可下载，走 GitHub，无需申请**。GitHub API 核实仓库存在且公开：`swxkfm/TripTailor`，创建于 2025-05-29，最后 push 2025-10-22，23 stars，默认分支 `main`。仓库根目录直接放了一个**数据集压缩包 `data.7z`，18,892,569 字节（约 18 MB）**，无需登录即可下载（`https://github.com/swxkfm/TripTailor/raw/main/data.7z`）。核实方式：GitHub REST API `repos/swxkfm/TripTailor/contents/`（一手）。
- 仓库根目录实测内容 ✅：`README.md`（5,950 B）、`TripTailor/`（代码目录）、`data.7z`（18.9 MB）、`requirements.txt`。
- ✅ 是否另在 HuggingFace 发布：**未发布**。HuggingFace 数据集检索 `search=TripTailor` 返回 **0 条结果**（经 hf-mirror 调用官方搜索 API；仅按仓库 ID 匹配，理论上可能有改名仓库，但无官方迹象）。

### 1.2 许可

- ⚠️ **仓库未声明许可 → 按「未授权」对待**。GitHub REST API 返回的 `license` 字段为 `null`，即仓库根目录无 LICENSE 文件、GitHub 无法识别任何许可（一手：API 响应）。
- ❓ 论文正文未出现 license 相关表述（本次通读 ar5iv 全文至 §4.2，未见）。

### 1.3 体量与字段

**实测落地形态** ✅：解压 `data.7z` 得到 **8 个平铺文件**（无子目录）：`attractions.csv`、`restaurants.csv`、`accommodations.csv`、`Train_Schedule.csv`、`Flight_Schedule.csv`、`train.json`、`test.json`、`infomation.json`。⚠️ 代码里硬编码的读取路径是 `../../database_EN/*.csv`，**文件名与代码预期一致，但需自行建 `database_EN/` 目录放置**。数据是**英文版**，城市名为罗马音（实测 `city` 值如 `Harbin`、`Beijing`），POI 名如 `Saint Sophia Cathedral`。

论文声称规模 vs 本次实测 ✅（一手：论文 §3.1；实测：下载 `data.7z` → base64 解码 → `bsdtar -xf` 解压 → Python `csv.DictReader` 逐行统计）：

| 类别 | 论文声称 | 实测 | 吻合 |
| --- | --- | --- | --- |
| 景点 attractions | 5,622 | 5,622 | ✅ |
| 酒店 hotels | 89,224 | 89,224 | ✅ |
| 餐厅 restaurants | 422,120 | 422,120 | ✅ |
| 火车班次 | 28,832 | 28,832 | ✅ |
| 航班航线 | 15,110 | 15,110 | ✅ |
| 真实行程 | 近 4,000 对 | train 3,145 + test 703 = 3,848 | ✅ |
| 城市 | 40 目的地 + 10 出发 | 三张 POI 表均覆盖 40 城 | ✅ |

> 注：CSV 的 `summary` 等字段含换行，按行数（`wc -l`）会虚高（如 attractions 9,322 行 vs 实际 5,622 条），**必须用 CSV 解析器计数**。

实测表头 ✅（一手：解压后的 CSV 首行）：

- `attractions.csv`：`poiId, city, poiName, commentCount, commentScore, heatScore, sightLevelStr, price, latitude, longitude, tagNameList, shortFeatures, reference_time, summary, opening_hours`
- `restaurants.csv`：`name, real_city, avg_price, small_cate, stars, review_count, good_remarks, bad_remarks, longitude, latitude, product_rating, environment_rating, service_rating, nearby_attractions`
- `accommodations.csv`：同餐厅表，但**无** `nearby_attractions`
- `Train_Schedule.csv`：`Train_Number, Station_Number, Station_Name, Arrival_Time, Departure_Time, Stop_Time, Running_Time, Second_Class_Price, First_Class_Price, Longitude, Latitude`
- `Flight_Schedule.csv`：含 `Departure/Arrival City, Distance (km), Airline, Aircraft Type, Departure/Arrival Time, 两端机场名与经纬度, On-Time Performance, Average Delay (minutes), 周一到周日, Price`

逐项字段核查（**注意：ID 与营业时间只在景点表有**）：

| 需查字段 | 景点 | 餐厅 | 酒店 | 结论 |
| --- | --- | --- | --- | --- |
| 稳定 ID | ✅ `poiId` | ❌ 无 | ❌ 无 | ⚠️ **仅景点有**；实测 `poiId` 无重复（5,622 个互异），形如 `77064`、`130886889`，疑似高德 POI ID |
| 坐标 | ✅ `latitude`/`longitude` | ✅ | ✅ | ✅ 全有，可直接算距离 |
| 类别 | ✅ `tagNameList`, `sightLevelStr` | ✅ `small_cate` | ✅ `small_cate` | ✅ 全有 |
| 城市 | ✅ `city` | ✅ `real_city` | ✅ `real_city` | ✅ 全有（列名不统一） |
| 营业时间 | ✅ `opening_hours` | ❌ 无 | ❌ 无 | ⚠️ **仅景点有**，且非空率约 **82.6%** |
| 价格 | ✅ `price`（门票） | ✅ `avg_price` | ✅ `avg_price` | ✅ 全有 |

**旅程数据实测结构** ✅：`train.json`/`test.json` 为数组，每项含 `pid`（样本 ID，非 POI ID）、`destination_city`、`departure_city`、`day`、`meal_price_range`、`budget`、`query`；`infomation.json` 以 `pid` 字符串为键，给出该样本的参考信息（`hotel`、`transport_otd`/`train_options` 等）。**⚠️ `pid` 是行程样本 ID，不要当作 POI ID。**

### 1.4 数据来源与采集方式（影响可复用性）

✅ 论文 §3.2 Step I：POI 从**开放互联网**采集；景点只保留 4A 及以上或出现于已验证行程中的；剔除缺价格/类别/评分的酒店与餐厅；用高德（Amap）补齐经纬度。行程来自 OTA（在线旅游平台）高评分游记，再由 LLM 改写为带时间轴的自然语言。

⚠️ 含义：POI 原始来源是第三方站点（含高德），而仓库**无任何许可声明**（见 1.2），论文也未说明再分发授权。这一点对「当离线 POI 主来源」是实质风险。

### 1.5 可获取性小结

- ✅ **公开可下载、无需申请、无需登录**：`https://github.com/swxkfm/TripTailor/raw/main/data.7z`（18,892,569 B）。本次已实际下载、解压并读取表头与记录数，**全部与论文声称吻合**。
- ✅ 压缩包内**没有任何 LICENSE / README**，仓库 65 个条目中也无任何许可文件 → 按「未授权」对待（见 1.2）。
- ⚠️ **体量偏小**：约 517k 条 POI 仅占 18.9 MB，反映每行字段被裁剪——餐厅与酒店**无营业时间、无独立 ID**，英文描述也较短。
- ⚠️ 英文版（`_EN`）：POI 名与描述为英文翻译，`tagNameList` 也为英文；中文原名不在包内。

---

## 2. ChinaTravel（HuggingFace `LAMDA-NeSy/ChinaTravel`）

> 访问方式说明：本机 DNS 把 `huggingface.co` 解析到非公网地址，官方域名直连被拒。以下 HF 内容经 **`hf-mirror.com` 镜像**读取官方 README 与官方 API 元数据（内容为官方文本，未改写）；表格数据经镜像 `resolve/main/` 下载原文件后本地读表头。

### 2.1 这个仓库里到底是什么

- ✅ **结论：`LAMDA-NeSy/ChinaTravel` 是「查询（query）数据集」，不是结构化 POI 数据。** 它只含各种 query 切分的 CSV（`easy.csv`、`medium.csv`、`human.csv`、`human1000.csv`、`preference*_base50.csv`、`phase2/part-*.csv` 等）。官方 README 原文：*"The static POI and transport data are distributed separately in the companion sandbox dataset linked above."*
- ✅ **结构化 POI 在另一个配套仓库 `LAMDA-NeSy/ChinaTravel-Sandbox`**（另有 ModelScope 镜像）。这才是「POI 本体」。
- ✅ 本仓库实测字段（官方 README「Record Layout」）：`uid`（唯一查询 ID）、`tag`、`start_city`、`target_city`、`days`、`people_number`、`limit_rooms`、`limits_room_type`、`hard_logic_py`（可执行约束程序）、`nature_language`、`nature_language_en`；preference 切分另有 `preference`/`preference_en`/`preference_py`；Phase 2 另有 `hard_logic_nl`、`constraint_keys`、`official_phase2_evaluation`。
- ✅ 切分与体量：easy 300 / medium 150 / human 154 / preference_base50 50 / human1000 **1,000** / preference0–5 各 50 / Phase 2 **2,000**（含 100 条竞赛评测子集）。Hub 标签体量为 `1K<n<10K`，`format:csv`，下载量 1,280、likes 14（2026-09-15 更新）。

⚠️ **对「构建候选池」的直接含义：拿 `ChinaTravel` 这个仓库当 POI 来源是拿不到的**，它只有自然语言 query + 约束程序。可用的是它的**配套 sandbox 仓库**。

### 2.2 配套 sandbox 的 POI 字段（实测）

✅ 经镜像下载 `data/en/attractions.parquet`、`restaurants.parquet`、`poi.parquet`，从 parquet footer 读出真实列名：

| Config | 行数（zh = en） | 实测列名 |
| --- | --- | --- |
| `attractions` | 3,413 | `language, city, id, name, type, lat, lon, opentime, endtime, price, recommendmintime, recommendmaxtime` |
| `restaurants` | 4,655 | `language, city, id, name, lat, lon, price, cuisine, opentime, endtime, recommendedfood` |
| `accommodations` | 3,866 | ❓ 未逐列核实（README 只给行数）。⚠️ 论文 §2.1 写的是 **4,124** 家酒店，与实际 3,866 不一致，疑为版本修订 |
| `poi` | 12,172 | `language, city, name, lat, lon` —— ⚠️ **无 id、无 type**，仅为景点/餐厅/酒店的合并名录 |
| `trains` / `flights` / `subway_stations` | 5,345 / 720 / 3,635 | 未逐列核实 |

- ✅ **稳定 ID**：景点与餐厅**有** `id`（int64）；⚠️ 但 `poi` 汇总表**没有** id。
- ✅ **坐标** `lat`/`lon`、**类别** `type`/`cuisine`、**城市** `city`、**价格** `price`、**营业时间** `opentime`/`endtime` 全部具备（景点与餐厅）。
- ✅ 另有 `recommendmintime`/`recommendmaxtime`（建议游览时长）与 `recommendedfood`（推荐菜）。
- ✅ **规模很小**：全部 POI 合计 **12,172 条、仅 10 城**；论文 §2.1 表述为「收集中国 10 个最热门城市」。这与 TripTailor 论文评价 ChinaTravel「only covers 10 cities and about 1,200 POIs per city」一致（12,172/10 ≈ 1,217 ✅）。

### 2.3 许可

- ✅ **实际为 CC-BY-4.0**，**不是**现有文档所写的 CC-BY-NC-SA-4.0。两个仓库的官方 README 均写明 *"licensed under Creative Commons Attribution 4.0 International (CC BY 4.0)"*，官方 API 元数据 tags 亦为 `license:cc-by-4.0`。**现有项目文档此处需更正。**
- ✅ 双语：zh / en 两套（en 版统一了概念标签，如 `Shanghai cuisine`）。

### 2.4 对「能否构建候选池」的回答

- ⚠️ **`LAMDA-NeSy/ChinaTravel` 本身不能构建候选池**——它是 query + 约束程序，用于评测/对话，没有 POI 行。
- ✅ **配套 `ChinaTravel-Sandbox` 可以构建候选池**（有 id/坐标/类别/价格/营业时间），但**上限只有 12,172 条 POI、10 个城市**，字段比 TripTailor 更全（多营业时间与建议时长），体量则小两个数量级。
- ⚠️ 需要权衡：sandbox 的 `poi` 表无 id 无类别，实际要用 `attractions`/`restaurants`/`accommodations` 三表并集，且三表 id 是否跨表唯一**未确认**。

---

## 3. 两数据集对比速查

| 维度 | TripTailor | ChinaTravel（query） | ChinaTravel-Sandbox |
| --- | --- | --- | --- |
| 形态 | POI CSV + 行程 JSON | 查询 CSV + 约束程序 | POI Parquet/ZIP |
| POI 体量 | ~517k（40 城） | 无 POI | 12,172（10 城） |
| 城市数 | 40 | 10 | 10 |
| 稳定 POI ID | ⚠️ 仅景点有 `poiId` | — | ✅ 景点/餐厅有 `id`（`poi` 表无） |
| 营业时间 | ⚠️ 仅景点有（非空 82.6%） | — | ✅ 景点/餐厅均有 |
| 价格 | ✅ 三类均有 | — | ✅ 景点/餐厅有 |
| 许可 | ⚠️ 无任何许可声明 | ✅ CC-BY-4.0 | ✅ CC-BY-4.0 |
| 获取 | ✅ GitHub 直下 18.9 MB | ✅ HF 直下 | ✅ HF 直下 |
