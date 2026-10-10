# 出行规划 Agent 的真实数据可得性调研（2026-10）

> 调研日：2026-10-10。目标：LangGraph + 意图识别 + RAG + Multi-Agent 的出行 Agent，在中国究竟能拿到什么数据。
> 标注：✅ = 直接打开官方页面核实；⚠️ = 二手/镜像，未取到原文；❓ = 未确认，需自己核对。
>
> **更正（同日主 agent 复核）**：本报告第 1 节称「高德个人认证 POI 搜索仅 **100 次/日**」，该数据取自第三方镜像页，**已被官方定价页推翻**——正确口径为基础搜索服务 **5,000 次/月**（超限 30 元/万次）。详见 [2026-amap-compliance-verify.md](./2026-amap-compliance-verify.md)。**该更正不改变本报告的结论方向**：真正的硬约束是协议明文禁止「存储/缓存」与「数据集构建」，而非配额，因此离线评测路径依然必需。

> **更正（2026-10-11，三处事实错误）**：后续核实推翻了本报告的三处结论，详见 [2026-datasets-triptailor-chinatravel.md](./2026-datasets-triptailor-chinatravel.md) 与 [2026-osm-ecosystem-for-offline-poi.md](./2026-osm-ecosystem-for-offline-poi.md)：
>
> 1. **ChinaTravel 的许可不是 CC-BY-NC-SA-4.0，而是 CC-BY-4.0**（HF API 标签 `license:cc-by-4.0`，实测）。**「非商业」限制并不存在**，本报告第 3、6、7 节的相应表述作废。
> 2. **ChinaTravel 主仓库里没有 POI 数据**——它是 query / 对话数据集。结构化 POI 在配套的 `LAMDA-NeSy/ChinaTravel-Sandbox`（**12,172 条 / 10 城**，attractions 与 restaurants 字段较全）。
> 3. **本报告给的中国 POI 导出链接不可用**：`feature.data-humdata-org.ahconu.org` 实测 `HTTP 401`（它是 HDX 的预发布分支环境）。正确入口是国家粒度的 `hotosm_chn_points_of_interest`，其 S3 直链公开可下（**762,586 要素 / GeoParquet 101 MB**）。
>
> 另有一项**新增的阻塞性发现**：**TripTailor 仓库没有任何许可声明**（GitHub API `license: null`、`/license` 端点 404、全仓库 65 个条目无 LICENSE），而它的 POI 来自第三方站点（含高德）。**在许可澄清之前不应入库**——数据本身可用、字段与论文一致，但缺授权。

## 0. 一句话结论

**地图能力几乎全免费且质量最好（路线/地理编码/天气/POI 都有官方 MCP）；票务、住宿、UGC 攻略基本没有官方接口，只剩高风险抓取或干脆放弃。** 真正的瓶颈是 POI 搜索配额（个人 100 次/日）和平台条款，不是模型。

## 1. 地图 / POI / 路线

**高德接口齐全**：关键字/周边/多边形搜索 POI、输入提示、地理与逆地理编码、驾车/步行/骑行/公交/电动车路线规划、距离测量、天气、行政区划、交通态势、静态地图（[Web 基础服务](https://developer.amap.com/api/webservice/summary)、[高级服务](https://developer.amap.com/api/webservice/guide/api-advanced/search)）✅

**个人 vs 企业配额**（[官方 FAQ](https://lbs.amap.com/faq/account/certification/39670) 为 JS 渲染未取到正文；数据取自[镜像页](https://amap.apifox.cn/doc-541078)，标注修改于 2026-05-28）⚠️

| 能力 | 个人认证/日 | 企业/日 |
|---|---|---|
| 地理编码、逆地理编码、坐标转换、IP 定位、行政区划、静态地图 | 5,000 | 30 万~300 万 |
| 驾车/公交/步行/骑行路线规划、距离测量、输入提示 | 5,000 | 30 万 |
| **POI 关键字/周边/多边形/ID 搜索** | **100** | 1,000 |

表中未列天气查询，疑与旧接口下线有关，待确认。❓ **POI 搜索 100 次/日是 demo 最硬的约束**，一次多城行程很容易打满。

**能否用于公开 demo —— 这是最大的坑。** 高德英文《Map Platform Terms of Service》（[原文](https://lbs.amap.com/api/policies/terms)，更新 2025-12-03）第 1.2 条明确禁止 ✅：禁止 scrape / export 高德内容；禁止 **pre-fetch、index、store、reshare、rehost** 与批量下载 geocodes、directions、places；**(h) 禁止在平台外缓存或存储高德内容**；禁止做实质相似/可替代产品；禁止与非高德底图或数据集混用；1.2.2(c) 禁止用于 AI 模型训练。
⚠️ 这是国际版英文条款，中国站中文协议（[入口](https://developer.amap.com/pages/terms/)）**必须你自己核对**。可确定的结论是：**高德禁止抓取、转存、再分发**。公开 demo 应实时调用、保留署名与 Logo、不落库导出、不把高德 POI 与 OSM 混在同一张图上。

**高德官方 MCP Server 是首选**（文档更新 2026-03-17）：[概述](https://developer.amap.com/api/mcp-server/summary)｜[快速接入](https://developer.amap.com/api/mcp-server/gettingstarted) ✅
- 2025-03 首发含位置服务、地点搜索、路径规划、天气等 **12 大能力**；2025-05 起可与高德 APP 打通，把行程一键生成专属地图。
- 工具：生成专属地图、导航唤端、打车唤端、地理编码、逆地理编码、IP 定位、天气、骑行/步行/驾车/公交路径规划（公交跨城需传 city/cityd）。
- 接入（推荐 Streamable HTTP）：
  `https://mcp.amap.com/mcp?key=<你的KEY>`；或 Node I/O：`npx -y @amap/amap-maps-mcp-server`，环境变量 `AMAP_MAPS_API_KEY`。
- 官方还有[出行规划专属地图案例](https://developer.amap.com/api/mcp-server/application-case/travel-planning-case)。
- ❓ 是否免费、是否消耗个人配额、Key 是否需企业认证：页面未写，建 Key 时确认。
- ⚠️ npm 包 `amap-mcp-server`（`sugarforever/amap-mcp-server`）是**社区版**，与官方 `@amap/amap-maps-mcp-server` 不是一回事。

**百度 / 腾讯对比** ✅ [百度开发者权益](https://lbsyun.baidu.com/solutions/privilege)：个人地理编码 5,000/日、逆地理 **300**/日、地点检索 **100**/日、路线规划 5,000/日，**并发仅 3 QPS**。[腾讯配额](https://lbs.qq.com/quotaImprove)（更新 2025-11-13）：个人地点搜索 **200**/日、POI 详情 200/日、**多边形搜索 0（个人不可用）**、逆地址解析与路线规划各 6,000/日，并发 5；且腾讯明确「企业或其他非公益机构持续使用不享受免费权益，必须办理商业授权」。
**结论：高德最优**（MCP 开箱即用、路线 5,000/日够用）；百度并发太低；腾讯条款最严。但三家个人 POI 配额都在 100~200 次/日，是行业性约束。

## 2. 交通数据

**12306：无官方 API，官方明确否认开放。** ✅ 官方口径见 2026-10-06 [新华网《官方发声：加速包、"余票监控"等抢票方式都是假的！》](https://app.xinhuanet.com/news/article.html?articleId=202610061d4be90d94bf460396c9aea0c23d5f8b)、[央视「12306 从未向任何第三方平台开放接口」](https://www.techweb.com.cn/ucweb/news/id/2970935)、2026-02-04 [央广网《把免费候补包装成"付费特权"》](http://news.cnr.cn/native/gd/20260204/t20260204_527515328.shtml)。

可用方案**全部是非官方**、直连 12306 前端：⚠️ [drfccv/mcp-server-12306](https://github.com/drfccv/mcp-server-12306)（MCP，余票/车站/经停/中转换乘）、[train-ticket-mcp](https://pypi.org/project/train-ticket-mcp/)、[@iflow-mcp/12306-mcp](https://www.npmjs.com/package/@iflow-mcp/12306-mcp)。❓ 具体 endpoint（社区多走 `kyfw.12306.cn` 余票接口）、验证码与风控强度未逐个核实。风险：有 IP 风控，项目常见「接口频繁」失效；**抢票/下单风险极高，只读查询在 demo 里相对可控但随时可能挂**。建议只读 + 缓存 + 失败降级。
**航班**：航旅纵横/飞常准无个人免费开放平台。VariFlight 走企业商务：[dataworks API 文档](https://dataworks.variflight.com/api-docs/flight-status-query-v3.md)、[飞友 AI 开放平台](https://ai.variflight.com/docs/aviation)，❓ 价格与试用未确认。海外替代：[AviationStack](https://aviationstack.com/)（免费 tier 很小、国内覆盖有限）、[AeroDataBox](https://geekflare.com/guides/flight-data-api/)、OpenSky（主要给轨迹非库存）。⚠️

## 3. 住宿 / 门票 / 攻略

**个人开发者拿不到任何合规的 OTA 实时价格。** 携程开放能力属 B 端分销/供应商体系（[分销平台手册](http://pages.ctrip.com/union/excl/Tbooking.docx)、[网站联盟 OPEN API](http://event.traveldaily.cn/download/thack2014/xiechengapi.pdf)），需企业资质与签约；飞猪走阿里开放平台面向 ISV/商家；美团有[技术服务合作中心 AI Hub](https://developer.meituan.com/ai-hub/skill-list/detail/12)，面向合作商家。⚠️

**爬虫的法律风险是明确的，不是灰色地带。** 北京知识产权法院法官[《爬取数据，存在哪些法律风险》](https://bjzcfy.bjcourt.gov.cn/article/detail/2023/03/id/7214062.shtml)（《光明日报》2023-03-25）✅ 列明：百度地图大量爬取大众点评评论构成不正当竞争（**实质替代 + 攫取流量**）；"鹰击"爬微博，即便前台公开数据、但绕过防范抓后台非公开数据，同样构成不正当竞争；数据持有者有实质投入即受保护。小红书相关案件亦有高额判赔（[抓取用户数据牟利判赔 110 万](https://www.ciplawyer.cn/articles/157825.html)）⚠️。叠加《数据安全法》《个人信息保护法》，抓取点评昵称/头像属个人信息处理。**结论：不要爬。**

**公开数据集（推荐）** ✅：[ChinaTravel](https://huggingface.co/datasets/LAMDA-NeSy/ChinaTravel)（中文旅行规划数据集，**CC-BY-NC-SA-4.0，非商业**）、[TripTailor](https://aclanthology.org/2025.findings-acl.503/)（ACL 2025，**50 万+ 真实 POI + 近 4,000 条真实行程**）、[HOT/OSM POI 导出](https://feature.data-humdata-org.ahconu.org/m/dataset/hotosm_chn_south1_points_of_interest)（ODbL，署名 + 相同方式共享）、Wikivoyage（CC-BY-SA）作攻略语料。马蜂窝/穷游/小红书抓取：不推荐，违反 robots.txt 与用户协议会加重不正当竞争认定。❌

## 4. 大模型 / embedding / rerank

**DeepSeek**（[官方定价](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)）✅：`deepseek-flash`(V4.1-Flash) 与 `deepseek-v4-pro`(V4-Pro-0813)；**上下文 1M、输出上限 384K**；**支持 Tool Calls / JSON Output / Responses API / Anthropic API**；OpenAI 兼容 `https://api.deepseek.com`（可直接用 `langchain-openai` 接 LangGraph）。

| 模型 | 输入(缓存命中) | 输入(未命中) | 输出 |
|---|---|---|---|
| deepseek-flash | 0.02 / 0.04 | 1 / 2 | 4 / 8 |
| deepseek-v4-pro | 0.15 / 0.30 | 4.5 / 9 | 13.5 / 27 |

（元/百万 tokens；空闲为高峰半价，高峰=工作日 9-12、14-18 点。）✅ 无公开新人免费额度说明。❓

**智谱 GLM**（[官方定价](https://docs.bigmodel.cn/cn/guide/start/pricing.md)）✅：GLM-5.3（1M，8/28 元）、GLM-5.3-Flash（1M，0.8/2.8 元，支持图文视频）、**GLM-4.7-Flash（200K，输入输出全免费）**、GLM-4-Flash-250414（免费）、GLM-4-Long（1M，1/1）。**Embedding-3（8K，0.5 元/百万 tokens）、Rerank（4K，0.8 元/百万 tokens）**、Search-Std 0.01 元/次。

**阿里云百炼 / 通义千问**（[新人免费额度规则](https://help.aliyun.com/zh/model-studio/new-free-quota)）✅：首次开通自动发放**各模型独立免费额度（通常每模型 100 万 tokens）**，**有效期 90 天**，**仅华北2（北京）**，**无需实名认证即可领**；未认证用完即停，认证后自动转按量付费。❓ qwen3 系列具体单价未取到，见[模型定价页](https://help.aliyun.com/zh/model-studio/model-pricing)。

**Kimi**（[定价页](https://platform.kimi.com/docs/pricing/chat)）✅：在售 **K3 系列、K2.7 Code、K2.6**，支持上下文缓存（5min/1h TTL）。❓ 单价表格未渲染，需自行打开。**豆包/火山方舟**：[模型价格页](https://ai.volcengine.com/docs/ark-aihub/2646927?lang=zh) 存在，❓ 价格与免费额度未取到。

**Embedding / Rerank 选型**：云端用百炼 `text-embedding-v3/v4`（[同步接口文档](https://www.alibabacloud.com/help/zh/model-studio/text-embedding-synchronous-api)，吃免费额度）或智谱 Embedding-3 + Rerank；本地用 `BAAI/bge-m3`（多语言 8K，dense+sparse+colbert 一体，约 0.5~2GB，CPU 可跑但慢）+ `bge-reranker-v2-m3`。⚠️ **建议：先本地 bge-m3 + bge-reranker-v2-m3 省 API 费；要省事就百炼 text-embedding-v4 + 智谱 Rerank。**

## 5. 开源项目扫描

❓ 项目名与描述来自搜索结果，**未逐个打开仓库，故不列 star 数**。

| 项目 | 技术栈 / 特点 | 真实数据 |
|---|---|---|
| [Pennyv99/Agent-Oriented-ReAct-System…](https://github.com/Pennyv99/Agent-Oriented-ReAct-System-with-Human-in-the-Loop) | LangGraph + FastAPI + Postgres + Redis，Function Calling + **MCP(AMap LBS)** + human-in-the-loop | 高德 ✅ |
| [drfccv/lvji-travel](https://github.com/drfccv/lvji-travel) | 旅迹：对话驱动，输出**可编辑逐日行程** | 地图 + 天气 + MCP |
| [Haohao-end/Ctrip-Style-AI-Travel-Assistant](https://github.com/Haohao-end/Ctrip-Style-AI-Travel-Assistant) | LangChain + LangGraph 多 agent，权限控制、human-in-the-loop | 未核实 |
| [kbhujbal/Multi-Agent-AI-Travel-Advisor](https://github.com/kbhujbal/Multi-Agent-AI-Travel-Advisor) | CrewAI + LangChain，7 个专职 agent + RAG + tool-calling | 未核实 |
| [senseirandystl/trip-planner-ai-agent](https://github.com/senseirandystl/trip-planner-ai-agent) | OpenAI tool-calling + **实时 OSM POI + Wikivoyage RAG + 行程校验 + PyDeck** | OSM（合规）✅ |
| [drfccv/mcp-server-12306](https://github.com/drfccv/mcp-server-12306) | 12306 MCP | 12306（非官方） |
| [BreadIceCream/ai-traveler-backend](https://github.com/BreadIceCream/ai-traveler-backend) | **Spring Boot 3 + Spring AI** + GIS | 未核实 |
| [78percent/LangGraph_Trip_Planner](https://github.com/78percent/LangGraph_Trip_Planner)、[HuangLianjin/ai-travel-agent](https://github.com/HuangLianjin/ai-travel-agent)、[jgalt0311/ai-travel-planner](https://github.com/jgalt0311/ai-travel-planner)、[bu-he/langchain-trip-planner](https://github.com/bu-he/langchain-trip-planner) | 入门级 demo（LangGraph / 中文 / React+Node / LangChain） | 未核实 |

**通病（有硬证据）**：① **LLM 编造行程、POI 幻觉是全行业问题**。[TripTailor](https://aclanthology.org/2025.findings-acl.503/) 用 50 万真实 POI + 近 4,000 条真实行程做基准，结论是**最新 SOTA 大模型生成的行程达到人类水平的不到 10%**，失败集中在**可行性、合理性、个性化**。✅ ② 只当"景点清单"，不校验开门时间、通勤耗时、地理聚集度。③ 数据接入浅，没有票务/价格/天气的实时校验。④ 单轮 prompt 出全文冒充 Agent，没有工具循环与失败重试。

**值得借鉴**：结构化输出（Pydantic/JSON Schema，逐日 + 每点带坐标/时长/来源）；**独立的确定性行程校验层**（POI 是否真实存在于工具返回、时间是否够、路线是否闭环）；多 agent 分工（意图/检索/规划/校验/改写）；地图可视化 + 一键唤端（高德 MCP 原生支持）；human-in-the-loop 断点。
**空白/机会**：中文场景真实票务与价格、行程可行性自动校验、攻略 RAG 与结构化 POI 检索分离、诚实标注数据来源与时效。

## 6. 合规风险清单（公开 demo）

- **地图条款**：高德禁止 scrape / 平台外缓存 / 转存再分发 / 与非高德数据集混用 / 用于 AI 训练（[条款](https://lbs.amap.com/api/policies/terms)）✅ → 实时调用、保留署名 Logo、不导出不落库、不混图。中文条款需自行核对。
- **配额用途**：个人配额限"个人学习、非企业使用"。**公开 demo 一旦带公司主体、引流或商业化，应立即申请商业授权**（腾讯表述最明确）。
- **数据抓取**：实质替代 = 不正当竞争；绕过技术措施 = 不正当竞争（[北京知产法院](https://bjzcfy.bjcourt.gov.cn/article/detail/2023/03/id/7214062.shtml)）✅ → RAG 语料只用明确许可的数据集。
- **个人信息**：不采集不存储手机号/身份证/位置轨迹；确需则依《个人信息保护法》告知同意 + 最小必要。
- **生成内容**：面向公众的生成式 AI 服务需留意《生成式人工智能服务管理暂行办法》相关要求（备案/内容安全），内网 demo 一般不触发，**公网开放建议核实** ❓。
- **票务**：非官方数据须显著标注"非官方、可能延迟、不保证准确"，**绝不提供代抢/下单**。
- **许可传染**：ChinaTravel 是 **CC-BY-NC-SA-4.0（非商业）**、OSM 是 **ODbL**，商用前必须确认。

## 7. 推荐：最省事且能真实跑通

1. **地图/POI/路线/天气/地理编码 → 高德官方 MCP Server**。Streamable HTTP：`https://mcp.amap.com/mcp?key=<KEY>`（[控制台建 Key](https://console.amap.com/dev/key)）。LangGraph 侧用 `langchain-mcp-adapters` 的 `MultiServerMCPClient` 把 MCP 工具转成 LangChain tools，挂进 ReAct agent。备选 REST：`restapi.amap.com/v3/place/text`、`/v3/direction/driving`、`/v3/geocode/geo`、`/v3/weather/weatherInfo`（key 作 query 参数）。**POI 搜索仅 100 次/日**：先用地理编码缩小范围、少量 POI 搜索建候选池，路线规划（5,000/日）多用于校验。
2. **火车票 → 12306 社区 MCP**（`drfccv/mcp-server-12306`），只读余票 + 超时 + 缓存 + 失败降级，UI 标注来源。
3. **攻略 RAG 语料 → ChinaTravel + Wikivoyage + OSM POI 快照**，不爬马蜂窝/小红书。
4. **LLM → DeepSeek `deepseek-flash`**（OpenAI 兼容、1M 上下文、tool calls、缓存命中 0.02 元/M，跑 agent 循环最划算）；开发期用**智谱 `GLM-4.7-Flash`（免费）**压成本。
5. **Embedding → 百炼 `text-embedding-v4`**（吃 100 万 tokens 新人免费额度，90 天）或本地 `bge-m3`；**Rerank → 智谱 `Rerank`（0.8 元/M）或本地 `bge-reranker-v2-m3`**。
6. **航班 → 先不接真实数据**；需要时用 VariFlight 商务合作或 AviationStack 免费 tier 示意国际航班。

**Agent 设计要点**：意图识别只输出结构化槽位（目的地/日期/预算/偏好/同行人）；检索分两路——**结构化 POI 检索**（高德 MCP）与**非结构化攻略 RAG**（本地语料），**互不混存**；加一层**确定性行程校验器**（时间够不够、距离合不合理、POI 是否真在工具返回里）——这是对抗那"不到 10%"最有效的手段；所有 POI 必须带 `source` 字段，**只允许用工具实际返回的 POI，禁止 LLM 自由生成地名**。

## 8. 降级方案：只用假数据 / 缓存数据

适用离线演示、评测、CI，规避配额与条款风险。

1. **本地库**：TripTailor（50 万 POI + 4,000 行程）与 OSM/HOT POI 导出落成 SQLite/Parquet，检索走 SQL + 向量库（Chroma/FAISS）。
2. **路线与距离**：本地跑 **OSRM / Valhalla**（OSM 数据，Docker 即可）算真实驾车步行时间；最省的是 haversine 直线距离 × 经验系数，UI 标注"估算"。
3. **天气**：**Open-Meteo**（免费、无需 Key）或预生成 JSON 快照。
4. **火车/航班**：固定 JSON 快照（带 `as_of` 时间戳），标注"示例数据"。
5. **LLM 仍可接真实**（这一步最便宜）：保留 DeepSeek / GLM-Flash，职责收缩为「读本地检索结果 → 排序 → 自然语言成文」，**不允许引入本地库不存在的地名**。
6. **可验证性**：对 20~50 个需求跑回归，统计"POI 全来自本地库 / 时间不冲突 / 距离合理"的比例，作为可行性指标（对齐 TripTailor 的可行性、合理性维度）。
7. **切回真实数据的最小改动**：把数据访问收敛到一个 repository 接口（`search_poi / route / weather / train`），实现 `LocalDatasetRepository` 与 `AmapMcpRepository` 两份，靠环境变量切换。

## 9. 待你自己确认（❓）

1. 高德**中国站中文服务协议**中关于数据缓存、展示、非商业 demo 的条文（英文条款限制已确认较严）。
2. 高德 **MCP 是否免费、是否消耗个人配额、Key 是否需企业认证**。
3. 高德个人 POI 搜索 100 次/日的现状（镜像页数据，建议登录控制台核对）。
4. 百炼 qwen3 单价；Kimi K3/K2.6 单价；豆包价格与免费额度。
5. VariFlight / AviationStack 的具体价格与国内覆盖。
6. 各 GitHub 项目的 star 数与最近提交时间（本次未逐个打开）。
7. 对公网开放的生成式 AI demo 是否需备案。
