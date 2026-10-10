# 高德官方 MCP 接线与协议原文核实（调研）

> 调研日：2026-10-10。目标：把「高德官方 MCP 能不能接、怎么接、协议允许做什么」查到可直接写代码的粒度。
> 说明：本报告只补 [2026-travel-data-sources.md](./2026-travel-data-sources.md) 与 [2026-amap-compliance-verify.md](./2026-amap-compliance-verify.md) **未答**的部分，以及已答但需推进到「可接线」粒度的部分；配额数字与协议 3.4/3.5/3.6 条原文不再重复，只做交叉引用。
> 标注：✅ 直接打开官方页面 / 官方包核实的原文 ｜ ⚠️ 推断或二手 ｜ ❓ 未确认。

---

## 0. 一句话结论

**高德官方 MCP 的接入面已经查清（Streamable HTTP 端点 + Query 传 key + 12~14 个能力），但托管端（`mcp.amap.com`）的 tool 名称、参数 JSON Schema 与真实响应体，官方文档一律没有公布，必须用一个有效 key 调 `tools/list` 才能补全；而中文服务协议里「不得直接存储、缓存或技术手段抓取」（3.5 条）与「不得……创造本服务及相关内容的衍生品（包括生成或用于数据库）」（4.12.7 条）两条原文，是这套接口用于真实实现时最硬的约束。**

---

## 1. 高德官方 MCP Server：接线细节

### 1.1 官方文档公布的能力清单与输入输出

来源：[MCP Server 概述](https://developer.amap.com/api/mcp-server/summary)（页面标注最后更新 2026-03-17）。✅

官方以「能力介绍」表格形式给出 **14 项能力**，每项只列输入、输出两块，**没有 JSON Schema、没有参数类型、没有默认值**：

| 能力 | 官方公布的输入 | 官方公布的输出 |
|---|---|---|
| 生成专属地图 | 行程名称、行程详情（每日行程描述、行程途径点位） | 专属地图唤端链接 |
| 导航到目的地 | 目的地经纬度 | 高德导航唤端链接 |
| 打车 | `origin`（起点经纬度）、`destination`（终点经纬度） | 高德打车唤端链接 |
| 地理编码 | `address`（位置信息）、`city`（城市信息，非必须） | `location`（位置经纬度） |
| 逆地理编码 | `location`（位置经纬度） | `addressComponent`（位置信息，包括省市区等信息） |
| IP 定位 | IP | `province`（省）、`city`（城市）、`adcode`（城市编码） |
| 天气查询 | `city`（城市名称或城市 adcode） | `forecasts`（预报天气） |
| 骑行路径规划 | `origin`、`destination` | `distance`（规划距离）、`duration`（规划时间）、`steps`（规划步骤信息） |
| 步行路径规划 | `origin`、`destination` | `origin`、`destination`、`paths`（规划具体信息） |
| 驾车路径规划 | `origin`、`destination` | `origin`、`destination`、`paths`（规划具体信息） |
| 公交路径规划 | `origin`、`destination`、`city`（起点城市）、`cityd`（终点城市） | `origin`、`destination`、`distance`、`transits`（规划具体信息） |
| 距离测量 | `origin`、`destination` | `origin_id`、`dest_id`、`distance`（规划距离）、`duration`（时间） |
| 关键词搜索 | `keywords`（搜索关键词）、`city`（查询城市，非必须） | `suggestion`（搜索建议）、`pois`（地点信息列表） |
| 周边搜索 | `keywords`、`location`（中心点经度纬度）、`radius`（搜索半径，非必须） | `pois`（地点信息列表） |
| 详情搜索 | `id`（关键词搜或周边搜获取的 poiid） | 地点详情信息 `location`、`address`、`business_area`、`city`、`type` 等 |

**托管端（`mcp.amap.com`）暴露的 tool 名称、每个 tool 的 JSON Schema、以及真实响应体：官方文档未公布。** ❓ 本报告未能取得权威结论，原因见 1.4。

> 交叉印证：官方[更新日志](https://developer.amap.com/api/mcp-server/changelog)（最后更新 2026-03-17）在 2025-03-25 条目写明「高德地图 MCP Server 正式上线，覆盖 **12 大核心服务接口**」，列举为地理编码、逆地理编码、IP 定位、天气查询、骑行路径规划、步行路径规划、驾车路径规划、公交路径规划、距离测量、关键词搜索、周边搜索、详情搜索——即上表 14 项中**不含**「生成专属地图 / 导航到目的地 / 打车」的 12 项。✅
> 2025-04-25 条目另外明确「专属地图」对应的 tool 名为 **`personal_map`**：「Cursor 会调用高德 **personal_map** tools，获取专属地图链接」（[更新日志](https://developer.amap.com/api/mcp-server/changelog)）。✅

### 1.2 官方 Node 包（stdio 路径）的 12 个工具签名与返回体——这是目前唯一可照着写代码的一手材料

来源：官方 npm 包 `@amap/amap-maps-mcp-server`，本报告下载 `0.0.8` 版 tarball 后读取 `build/index.js`（841 行）。✅

包元信息（[npm registry](https://registry.npmjs.org/@amap/amap-maps-mcp-server)）：名称 `@amap/amap-maps-mcp-server`，**最新版本 0.0.8，最后发布时间 2025-04-25**，License **ISC**，依赖 `@modelcontextprotocol/sdk@1.0.1` + `node-fetch@^3.3.2`，`bin` 为 `mcp-amap`，未声明 `engines`。服务端自报名 `mcp-server/amap-maps`，自报版本 `0.1.0`。✅

**工具清单（`name` 逐字，均为 `inputSchema.type = "object"`）**：

| tool `name` | 参数（类型 / 是否必填） | 该 tool 实际返回给模型的 `text` |
|---|---|---|
| `maps_regeocode` | `location: string` 必填 | `{provice, city, district}`（**字段名 `provice` 是包内拼写，非 `province`**） |
| `maps_geo` | `address: string` 必填；`city: string` 可选 | `{return: [{country, province, city, citycode, district, street, number, adcode, location, level}]}` |
| `maps_ip_location` | `ip: string` 必填 | 透传 `/v3/ip` 返回 |
| `maps_weather` | `city: string` 必填 | `{city, forecasts: [...]}`，取自 `data.forecasts[0].casts`（请求固定带 `extensions=all`） |
| `maps_bicycling` | `origin: string`、`destination: string` 均必填（`"经度，纬度"`） | 透传 `/v4/direction/bicycling` 返回 |
| `maps_direction_walking` | `origin`、`destination` 均必填 | 透传 `/v3/direction/walking` 返回 |
| `maps_direction_driving` | `origin`、`destination` 均必填 | 透传 `/v3/direction/driving` 返回 |
| `maps_direction_transit_integrated` | `origin`、`destination`、`city`、`cityd` **四个都必填** | `{route: {origin, destination, distance, transits: [{duration, walking_distance, segments: [{walking: {origin, destination, distance, duration, steps: [{instruction, road, distance, action, assistant_action}]}, bus: {buslines: [{name, departure_stop: {name}, arrival_stop: {...}}]}}]}]}}` |
| `maps_distance` | `origins: string`（多个点用 `\|` 分隔）、`destination: string` 必填；`type: string` 可选（`1` 驾车 / `0` 直线 / `3` 步行） | 透传 `/v3/distance` |
| `maps_text_search` | `keywords: string` 必填；`city: string` 可选；`types: string` 可选 | `{suggestion: {keywords, ciytes: [{name}]}, pois: [{id, name, address, typecode, photos}]}`（**`ciytes` 是包内拼写错误，源接口字段为 `cities`**；`photos` 取首张图） |
| `maps_around_search` | `location: string` 必填；`keywords`、`radius: string` 可选 | `{pois: [{id, name, address, typecode, photos}]}` |
| `maps_search_detail` | `id: string` 必填 | `{id, name, location, address, business_area, city, type}`，其中 `city` 取自响应的 `cityname` |

**注意两处包内缺陷（照抄会踩坑）**：`maps_regeocode` 返回键拼成 `provice`；`maps_text_search` 把响应的 `suggestion.cities` 读成 `suggestion.ciytes`，导致城市建议实际为空。✅（均为包内源码直读）

> **复核更正（同日主 agent 抽验）**：本节初稿还列了第三条——「`handleSearchDetail` 成功分支的 `isError` 被写成 `true`」——**该结论不成立，已删除**。直读 `build/index.js` 第 380–407 行：`data.status !== "1"` 的**错误分支**才是 `isError: true`（正确写法），**成功分支是 `isError: false`**。原文「两处缺陷」却列了三项，本身也不自洽。此条属把「错误分支」误认成「成功分支」。

**每个工具都会在请求上附加固定参数 `source=ts_mcp`。** 这是官方埋的渠道标记。✅

### 1.3 接入方式

来源：[快速接入](https://developer.amap.com/api/mcp-server/gettingstarted)（2026-03-17）、[创建应用和 Key](https://developer.amap.com/api/mcp-server/create-project-and-key)（2026-10-10）。✅

- **支持的传输方式：官方写明「目前支持 Streamable HTTP 和 Node.js I/O 两种接入方式（推荐用户使用 Streamable HTTP）」。** ✅
- **Streamable HTTP 端点原文**（客户端配置片段逐字）：
  ```json
  {
    "mcpServers": {
      "amap-maps-streamableHTTP": {
        "url": "https://mcp.amap.com/mcp?key=您在高德官网上申请的key"
      }
    }
  }
  ```
- **鉴权方式：key 作为 URL Query 参数（`?key=`）。官方页面未给出任何 header 鉴权形式（如 `Authorization`）。** ✅
- **Node.js I/O 方式**：`command: npx`，`args: ["-y", "@amap/amap-maps-mcp-server"]`，环境变量 `AMAP_MAPS_API_KEY`。官方要求 **Node.js ≥ v22.14.0**，并检查 npm 源为 `https://registry.npmjs.org/`。✅
- **Key 创建路径**：控制台 → 我的应用 → 添加 Key → **服务平台选择【Web 服务】**（[原文步骤](https://developer.amap.com/api/mcp-server/create-project-and-key)）。✅
- **SSE 已下线**：更新日志 2026-03-17 条目为「下线 通用级 SSE 协议 MCP 服务解决方案」。✅ 不要按任何 SSE 教程接线。

### 1.4 托管端点的实测边界（本报告实际发过请求）

在**没有有效 key** 的前提下，对 `https://mcp.amap.com/mcp` 发 JSON-RPC POST（`Accept: application/json, text/event-stream`）：✅

- `POST https://mcp.amap.com/mcp`（不带 key）→ HTTP 200，响应体 `{"status":"0","info":"INVALID_USER_KEY","infocode":"10001"}`。
- `POST https://mcp.amap.com/mcp?key=bogus`（`tools/list`）→ 同上 `INVALID_USER_KEY`。

结论：**该端点确实接受标准 MCP JSON-RPC POST，且在鉴权失败时用高德自有的 `{status, info, infocode}` 结构而不是 JSON-RPC error 返回**——这对客户端错误处理有影响（拿不到标准 `error.code`）。✅
**托管端的 `tools/list` 结果、tool 命名的 `maps_*` 风格是否一致、是否有鉴权前的 `initialize` 握手——均未确认**，因为没有可用 key。❓

### 1.5 是否免费 / 是否消耗个人配额 / 建 Key 是否需企业认证

| 问题 | 结论 | 依据 |
|---|---|---|
| MCP 是否单独收费 | **官方未把 MCP 列入任何价目表**；[产品定价页](https://lbs.amap.com/upgrade) 中无 "MCP" 条目（MCP 只出现在导航里），[MCP 文档](https://developer.amap.com/api/mcp-server/summary) 全文无价格、无「免费」字样。判定为**随基础服务配额计费、无独立报价** | ⚠️ 推断（页面无记载） |
| 是否消耗个人配额 | **推断消耗同一份月配额**：MCP 用【Web 服务】Key（1.3），而[定价页](https://lbs.amap.com/upgrade) 写明「基础 LBS 服务 / 基础搜索服务」的**「配额共享平台：API、JS、Android、iOS、微信小程序」**，且「服务请求优先消耗月配额，月配额超限后可付费购买」。**官方无明文。** | ⚠️ 推断 |
| 建 Key 是否需企业认证 | **不需要企业认证，但必须完成开发者实名认证**：[《关于高德开放平台个人开发者实名认证的公告》](https://lbs.amap.com/news/developer-certify)（2021-08-06）原文——「未认证个人开发者将无法在高德地图开放平台新增 key，已删除的应用和key无法恢复」；[《未认证开发者基础接口权限关闭公告》](https://lbs.amap.com/news/permission-closed)（2022-09-19）原文——「未认证开发者各接口调用权限将逐步被关闭」。两公告均写「根据自身情况选择按个人或企业身份进行开发者认证」，且**个人认证账号不能购买配额**（「未认证个人开发者将无法在高德地图开放平台官网购买配额、商用授权等相关服务」） | ✅ |
| 个人认证能不能买流量包 | [协议 3.1 条](https://developer.amap.com/pages/terms/) 原文：「您以**个人研究学习目的**使用本服务的，在您认证成为个人认证开发者且签署本协议后，针对基础服务……您可享有每月一定额度内的、免费的服务配额，**超出免费额度后您需付费购买**……若您以非前述目的使用本服务的，您可以创建工单联系我们办理付费许可事宜。」→ 协议允许个人认证超限付费；公告只说不**认证**的不能买。两者不冲突，但**个人账号实际能否下单流量包，本报告未登录控制台验证** | ⚠️ / ❓ |

**配额数字（个人认证，月）再确认**：[定价页](https://lbs.amap.com/upgrade) 原始表头为「月配额 ｜ 个人认证开发者 ｜ 企业认证开发者 ｜ 企业认证开发者（技术服务许可）」——基础 LBS 服务 150,000 / 3,000,000 / 9,000,000；**基础搜索服务 5,000 / 50,000 / 500,000**；天气预报 5,000 / 5,000 / 9,000,000；智能硬件定位 0 / 5,000 / 9,000,000。✅（与既有报告的更正一致；此前「100 次/日」为错。）

---

## 2. 高德中文服务协议原文摘录（与本题相关的五类事项）

来源：[《高德地图开放平台服务协议》](https://developer.amap.com/pages/terms/)，页面标注**更新时间：2025年12月03日**。以下全部为**逐字引用**，括注条款号。✅

### 2.1 数据缓存 / 存储 / 落库

**3.5 条**：

> 您只可使用在平台网站相应官方文档中所列明和开放的本服务的功能来对相关服务数据的结果进行展示，但是您**不得直接存储、缓存或技术手段抓取、使用本服务内部数据、图片等相关内容**。在接受本协议约束的情况下，您可以在向最终用户提供其他信息的同时，使用本服务获得相关服务数据。若您有脱离本服务使用服务数据等相关内容的需求，可以提交工单进行咨询，我们将评估是否可以开展合作。

**4.12.3 条**：

> 您不得使用任何漫游器、网络蜘蛛、网络爬虫、抓取工具、网站搜索/检索应用程序或其他工具访问、**抓取、爬取、预读取、存储、缓存、截图、检索或索引**本服务及相关内容的任何一部分……

**7.3 条**：

> 未经高德事先书面同意，您不得为任何目的超出我们提供的授权范围使用本服务及相关内容，更不得对本服务及相关内容进行包括但不限于**爬取、存储、缓存、下载、镜像、复制、截图、修改、改编、汇编、编撰、翻译、二次包装、制作衍生品、传播、出版、发行、转让、转售、销售、许诺销售、出借、出租、转授权、再许可、分许可**等任何侵害高德依据国家法律法规和其他规范性文件所享有的合法权利及相关权益的行为。

### 2.2 数据展示与署名要求

**4.10.7 条**（禁止性规定，逐字）：

> **删除或遮挡本服务中包含的任何版权声明、商标声明或其他所有权声明**；

**4.10 条引语**（该禁止项的前置约束，逐字）：

> 您应确保您的应用以及对本服务、相关内容、许可书、**审图号及高德标志**的使用行为和目的不违反所有适用的法律、法规、规章、规范、政策、行政命令、监管要求、国家强制性标准以及具有法律约束力的其他标准……

**7.4 条**（署名许可的范围，逐字）：

> 在本协议中，"标志"是指各方使用和拥有的名称、字号、商号、商标、logo、品牌、服务标记、徽标、域名，以及其他明显的标志。根据本协议，高德在此授予您一项**不可转让的、不可转授的、非排他性的，在您使用本服务期限内在您的应用中使用"高德地图"字样标志的许可**，并且该使用许可的**唯一目的是用以说明在您的应用中使用了本服务**。

**7.7 条（这一条是中文协议里唯一的「正向署名义务」，此前两份文档都未摘到）**：

> 通过本服务提供给您的服务页面、地图图片、搜索结果等中可能包含法律法规要求必须标明显示的审图号、出版号、经营许可证号等信息，以及高德、其关联公司及其合作伙伴的版权标识、标志，您不得以任何方式对前述内容进行删除、掩藏、修改或替换，如因您违反上述约定的不当使用行为导致高德承担相关法律责任的，高德有权向您追偿，包括但不限于提起相关司法诉讼程序。同时，**您应确保，在您的应用展示通过本服务调用的地图页面时在适当位置显示本服务来源于"高德地图"**，并要求您的客户使用您的应用时仍然满足前述要求。

**7.4 条第二段（标志使用的边界，逐字）**：

> 除此之外，**您不得以任何方式和目的包括但不限于以商业宣传、产品宣传、企业经营等方式使用高德标志**。在您按前述约定使用高德标志时，您不得：

（同条 7.4.1–7.4.6 进一步禁止暗示关联/赞助、诋毁高德、把高德标志当最大标记、与色情赌博等非法内容并列等情形。）

**7.8 条（专有权利声明与「不得披露合作关系」，逐字）**：

> 您不得以任何方式删除、掩藏、修改或替换本服务及相关内容中所附的或包含的**任何专有权利声明**（包含但不限于著作权、商标权、专利权、所有权声明等）、法律协议、其他法律声明、以及其他任何链接或公告，**不得未经高德同意向第三方披露使用高德产品及服务和相关内容的情况、双方合作的事实及内容**……

**结论：中文协议确有「正向署名」要求——7.7 条明文要求「在您的应用展示通过本服务调用的地图页面时在适当位置显示本服务来源于"高德地图"」；同时 7.4/7.8 对标志用法与「披露合作关系」都设了额外限制。** ✅

### 2.3 非商业 / 个人学习用途的边界

**3.1 条**：

> 若您是自然人：您以**个人研究学习目的**使用本服务的，在您认证成为个人认证开发者且签署本协议后，针对基础服务……您可享有每月一定额度内的、免费的服务配额，超出免费额度后您需付费购买……**若您以非前述目的使用本服务的，您可以创建工单联系我们办理付费许可事宜。**

**3.2.1 条（「商业目的 1」的定义与后果）**：

> 如您自行使用本服务（包括但不限于**向第三方或公众用户收费、参与第三方项目投标、用于内部管理系统或后台管理系统、以及任何其他直接或间接获取收益或利益的目的或用途**等使用场景，统称为"商业目的1"），则您需要事先从高德购买技术服务许可

**3.2.5 条**：

> 若您以**非商业目的**使用本服务，您可**创建工单并提交相关证明，由我们评估合作事宜**。

**3.6 条（仅限自用）**：

> **原则上仅限于您自己使用本服务**；对于SDK产品，您可以允许自然人用户通过您的应用而使用相应服务。如果您经我们同意或认可，您将您的开发者账号下所申请开通的服务交由第三方实际使用的，**您有义务事先告知我们并要求该等第三方遵守本协议的全部内容**……

**4.12.5 条**：

> 您不得将本服务**以收费或其他获利的方式进行提供，无论是否为直接经济或金钱收益**；

**4.11 条中的一句**（对「只给自己看」的进一步收紧）：

> 您**不得将仅供您自行预览的任何内容以任何方式向您之外的任何方提供**。

**4.6 条（数据归属）**：

> 您理解并同意，对于您及您的用户使用本服务的过程中与高德服务器交互产生的所有相关数据**归高德所有**。

### 2.4 个人认证配额的用途限制

与 2.3 同一组条文：免费配额的条件是 **「个人研究学习目的」+「个人认证开发者」+「已签署协议」**（3.1 条）；一旦落入「商业目的 1/2」定义（含「任何其他直接或间接获取收益或利益的目的或用途」），「您需要事先从高德购买技术服务许可」（3.2.1 / 3.2.2 条）。另 4.8.3 条：

> 如果您认证为个人认证开发者，但是您的应用是**非自然人运营**的、或有其他信息表明您将本服务用于法人或非法人组织需求的，我们有权**要求您变更开发者认证类型**，并且我们有权要求您**以企业开发者的收费标准**向我们支付服务费用……

4.9 条另有一句与配额直接相关：

> 您不得**通过注册多个个人或企业账号为您的应用获取更高的本服务使用配额**或享受更多服务权益。

**说明**：本节「个人认证账号不能购买配额」这一条来自[公告原文](https://lbs.amap.com/news/developer-certify)，公告的措辞是「**未认证**个人开发者将无法……购买配额」，**并非「个人认证开发者不能购买」**；协议 3.1 条则明确个人认证可「超出免费额度后……付费购买」。两者不冲突，但个人认证账号实际能否自助下单流量包，本报告未登录控制台验证（见第 7 节）。⚠️

### 2.5 是否禁止与其它数据集混用

**中文协议中未检索到直接禁止「与非高德数据集混用」或「制作竞品」的条文**（检索词包括 实质/替代/相似/竞品/竞争/第三方数据/混用）。✅ 与之最接近的是三条边界性禁止：

**4.12.4 条**：

> 您**不能脱离本服务单独使用或展示相关内容**，或擅自修改本服务的名称、展示方式，或以任何方式侵犯本服务的完整性；

**4.12.7 条**：

> 除非本协议明确许可，您不能复制、模仿、翻译、改变、修改传播本服务及相关内容的全部或部分、或**创造本服务及相关内容的衍生品（包括生成或用于数据库）**，或以任何方式传播、公开展示本服务及相关内容的全部或任何一部分；

**4.12.9 条**：

> 您**不能为本服务创造或提供封装**。例如，您不得进行如下行为：（1）在您向其他人提供的**任何应用接口中使用或提供本服务或相关内容的任何部分**；或（2）开发或创造一个 API、SDK、网站或应用程序等产品或服务以**重现或复制**高德地图应用程序或本服务的全部或部分；

**3.4 条**（训练与数据集，此前已核实，此处仅作对照）：

> 除非我们专门授予您明确清晰的的书面许可，您不得将本服务及相关内容应用于车载场景……**不得将本服务及相关内容用于模型或算法训练及相关数据集构建**……

---

## 3. 中文协议 vs 英文条款：差异清单

英文来源：[Map Platform Terms of Service](https://lbs.amap.com/api/policies/terms)，页面同为**最后更新时间 2025年12月03日**。以下英文为逐字引用。✅

| 事项 | 英文条款（逐字） | 中文协议 | 差异判定 |
|---|---|---|---|
| 与非高德数据/底图混用 | **1.2(j)**：「Customer will not use the Services with or near a non-Company map services in Customer Application(s). For example, Customer will not (i) display or use Places content on a non-Company Map, (ii) link Company Content and Services to non-Company Content or a non-Company Map, **(iii) combine non-Company datasets or map with Company Content**」 | 无对应条文 | **实质差异：英文明文禁止混用，中文没有。** ⚠️ |
| 竞品/可替代产品 | **1.2(i)**：「Use the Services to create a product or service with features that are substantially similar to or replaceable with or competitive to products or services of Company…」 | 无「竞品」表述；4.12.9 禁「封装/复制 API」 | **实质差异：英文范围更宽。** ⚠️ |
| 缓存/存储 | **1.2(g)(i)**：「pre-fetch, index, store, reshare, or rehost Company Content outside the Services and the Platform」；**1.2(h)**：「Cache or store Company Content outside of the Platform and Services」 | 3.5 条「不得直接存储、缓存或技术手段抓取」；4.12.3 条 | **一致（中文侧同等严格）。** ✅ |
| 批量下载 | **1.2(g)(ii)**：「bulk download Company's map tiles, images, geocodes, directions, distance matrix results, roads information, places information…」；(iii)「copy and save business names, addresses, time, contact information or user reviews」 | 7.3 条含「下载、汇编、编撰」，但无「批量下载 geocodes/directions」这种逐项列举 | **英文更细。** ⚠️ |
| AI 训练 | **1.2.2(c)**：「use the Services for a machine learning, or artificial intelligence ("AI") system optimization and training, including but not limited to, algorithm and/or model optimization and training, machine learning, deep learning and data extrapolation」 | 3.4 条「不得用于模型或算法训练及相关数据集构建」 | **一致。** ✅ |
| 署名 / 标志 | **6.1**：「Customer may not remove or obfuscate any Company Marks or copyright notices affixed to or included in the Services. You will ensure that all Company Marks and copyright notices are present in the Services.」；**1.2(k)**：「Use incorrect attribution of any information derived from the Platform or Services」 | 4.10.7、**7.7**（明文要求「在适当位置显示本服务来源于"高德地图"」）、7.8、7.4 | **语义一致（禁止删除/遮挡 + 正向保证存在）。** 两版都有「必须保留/存在」这层；中文 7.4 额外限制「不得用于商业宣传、产品宣传、企业经营」，7.8 额外禁止未经同意披露合作关系。✅ |
| 商业化前提 | 1.1 条以「payment of applicable fees」为许可前提，无「个人研究学习」免费配额概念 | 3.1 / 3.2 条有明确的「个人研究学习目的 + 个人认证 = 月免费配额」 | **中文侧多出一档个人免费额度，英文条款无此机制。** ⚠️ |
| 自用范围 | 1.1.2 允许「distribute Customer Application(s) directly or indirectly to End Users」 | 3.6 条「原则上仅限于您自己使用」 | **中文侧更严（这也是既有报告把中文站当更硬约束的理由）。** ⚠️ |
| 广告 | 无对应条文 | 6.1 条「您使用本服务时**不得以任何形式**在本平台、本服务、本服务页面、本服务相关内容、服务数据中**关联或展示任何广告**」 | **中文侧多出禁止展示广告的条文**（对做流量变现的 demo 有直接影响）。✅ |
| 审计 | **5.1 / 5.2**：保留 3 年记录、高德可提前 30 天书面通知后进场检查 | 无对应条文 | **英文侧多出审计权。** ✅ |

**给合规判断的净结论**：两版在「缓存/存储」「AI 训练」「署名」三条上口径一致且严格；**「混用」「竞品」只写在英文版**，「个人免费配额 + 禁止广告 + 仅限自用」只写在中文版。做中文站业务时**应按两版并集的约束从严执行**。⚠️

---

## 4. Python 侧怎么接

### 4.1 本项目实测版本环境

- 项目声明依赖（[requirements.txt](../../requirements.txt)）：`langgraph>=1.2,<2`、`openai>=1.40`、`pydantic>=2.7`、`python-dotenv>=1.0`。
- 虚拟环境实测（`.venv/bin/python` + `importlib.metadata`）：**langgraph 1.2.14、langchain-core 1.6.9、langgraph-prebuilt 1.1.0 已安装；`mcp`、`langchain`、`langchain-mcp-adapters` 均未安装**（`pip` 可执行文件不在 venv 内，版本经 `importlib.metadata.version()` 读取）。✅
- PyPI 口径：[langgraph 1.2.14](https://pypi.org/pypi/langgraph/json) 的依赖为 `langchain-core<2,>=1.4.7`、`langgraph-prebuilt<1.2.0,>=1.1.0`、`langgraph-checkpoint<5.0.0,>=4.1.0`、`langgraph-sdk<0.5.0,>=0.4.6`、`pydantic>=2.7.4`、`xxhash>=3.5.0`，`requires_python >=3.10`。✅
- [langchain-core 1.6.9](https://pypi.org/pypi/langchain-core/json) 的依赖：`httpx<1.0.0,>=0.23.0`、`pydantic<3.0.0,>=2.7.4`、`langchain-protocol>=0.0.17`、`langsmith<1.0.0,>=0.3.45` 等。✅

### 4.2 `langchain-mcp-adapters` 是否存在、最新版本、传输支持、兼容性

存在。✅ 来源：[PyPI JSON API](https://pypi.org/pypi/langchain-mcp-adapters/json)、[GitHub 仓库](https://github.com/langchain-ai/langchain-mcp-adapters)。✅

| 项 | 事实 |
|---|---|
| 最新版本 | **0.3.2**，发布 **2026-08-06**（其前：0.3.1 2026-07-27、0.3.0 2026-06-10、0.2.2 2026-03-16） |
| `requires_python` | `>=3.10`（本项目 3.12 满足） |
| 依赖声明（0.3.2） | `langchain-core<2.0.0,>=1.3.3`、`mcp<2.0.0,>=1.24.0`、`typing-extensions>=4.14.0` |
| **与 `langchain-core 1.6.9` 的兼容性** | **满足**：1.6.9 落在 `>=1.3.3,<2.0.0` 内 |
| **与 `langgraph 1.2.14` 的兼容性** | **无法从依赖声明判定**：该包**不声明 langgraph 依赖**（只用 langchain-core）；其官方描述为「Make MCP tools compatible with LangChain and LangGraph agents」。**未见任何形式的版本矩阵**。❓ |
| 是否支持 Streamable HTTP | **支持**。连接配置用 `"transport": "http"`（别名 `"streamable_http"` / `"streamable-http"`），底层调 `mcp.client.streamable_http`；README 有专门 [Streamable HTTP 章节](https://github.com/langchain-ai/langchain-mcp-adapters#streamable-http)；源码 `sessions.py` 的分支为 `if transport == "sse"` / `elif transport in {"streamable_http", "streamable-http", "http"}` / `"stdio"` / `"websocket"` |
| 是否支持自定义 header | 支持，`headers` 字段对 `http`（或 `streamable_http`）与 `sse` 生效（[README](https://github.com/langchain-ai/langchain-mcp-adapters#headers)）。**对高德托管端无用**——其鉴权在 URL query |
| License / 活跃度 | MIT；3,654 stars；`pushed_at` 2026-09-16 |

### 4.3 ⚠️ 关键：该包已被官方标记为「迁移中」

`langchain-mcp-adapters` 的 [README 顶部公告](https://github.com/langchain-ai/langchain-mcp-adapters)逐字：

> MCP support has moved into LangChain under the [`langchain.mcp`](https://github.com/langchain-ai/langchain/tree/master/libs/langchain_v1/langchain/mcp) namespace. Please migrate to `langchain[mcp]` for ongoing development, fixes, and support.

### 4.4 LangChain / LangGraph 侧接 MCP 的官方推荐路径（官方文档原文）

来源：[LangChain 官方文档《Model Context Protocol (MCP)》](https://docs.langchain.com/oss/python/langchain/mcp)（Python 版）。✅ 逐字要点：

> LangChain agents call tools defined on MCP servers through **`MCPAdapter`**, which discovers a server's tools and adapts them into LangChain tools you can pass straight to `create_agent`.
> `MCPAdapter` is built on **FastMCP**, which handles transport inference, protocol negotiation, connection management, and authentication.
> The `langchain.mcp` namespace requires **`langchain[mcp]>=1.4.0`** and is **in beta**. Importing from it raises a `LangChainBetaWarning` once per process. The API may change.

安装方式原文：`pip install "langchain[mcp]"`（该 extra 拉入 FastMCP）。
迁移指引原文指向：《Migrate from `langchain-mcp-adapters`》（文档内链，路径 `/oss/python/migrate/langchain-mcp-adapters`）。
最小用法原文（文档 Quickstart）：

```python
from langchain.agents import create_agent
from langchain.mcp import MCPAdapter

async def main():
    async with MCPAdapter("https://example.com/mcp") as adapter:
        ...
```

**依赖实测（PyPI）**：[langchain 1.4.4](https://pypi.org/pypi/langchain/json)（最新）声明 `langchain-core<2.0.0,>=1.6.9`、**`langgraph<1.3.0,>=1.2.11`**、`pydantic<3.0.0,>=2.7.4`，并含 `fastmcp<5.0.0,>=4.0.11; extra == "mcp"`。✅
→ 即：本项目 `langgraph 1.2.14` + `langchain-core 1.6.9` + `langchain 1.4.4` **三者互不冲突**（langgraph 1.2.14 在 `>=1.2.11,<1.3.0` 内；langchain-core 1.6.9 同时满足 langchain 与 langgraph 的下界）。✅
**注意：这会引入 `langchain` 本体的额外依赖（含 langsmith 等），而 `langchain[mcp]` 额外引入 `fastmcp`。** 与现有 requirements 的差异属实施范畴，本报告不展开。

### 4.5 若不走 MCP

本报告不涉及；既有两份文档已讨论 REST 直连方案，其接口形状见第 5 节。→ [2026-travel-data-sources.md](./2026-travel-data-sources.md) 第 7 节。

---

## 5. 备选 REST 接口的形状（官方文档，可照着写代码）

全部来自 `developer.amap.com` 官方 API 文档页，均已直接打开核实。✅

### 5.1 关键字搜索 `GET https://restapi.amap.com/v3/place/text`

来源：[搜索 POI](https://developer.amap.com/api/webservice/guide/api/search)（最后更新 2026-07-15）。✅ 官方提示原文：「目前搜索是不支持返回全量数据的，同请求参数翻页查询最多支持获取 **200 条**数据」。

**请求参数**（必填 `key`；`keywords` 与 `types` 二选一必填）：

| 参数 | 含义 | 必填 | 默认 |
|---|---|---|---|
| `key` | Web 服务 API 类型 KEY | 必填 | 无 |
| `keywords` | 查询关键字，**只支持一个关键字** | 必填（与 `types` 二选一） | 无 |
| `types` | POI 类型：六位分类代码或汉字，多个用 `\|` 分割 | 必填（二选一） | 无 |
| `city` | 城市中文 / `citycode` / `adcode`（强烈建议用 adcode，可到区县） | 可选 | 全国 |
| `citylimit` | `true`/`false`，仅返回指定城市数据 | 可选 | `false` |
| `children` | `0`/`1`，是否按层级展示子 POI | 可选 | `0` |
| `offset` | 每页记录数，**官方「强烈建议不超过 25」** | 可选 | `20` |
| `page` | 当前页数 | 可选 | `1` |
| `extensions` | `base`（默认）/`all`（含附近 POI、道路、交叉口、`pcode/citycode/adcode` 等） | 可选 | `base` |
| `langCode` | `zh`/`en`（多语言为**高级服务**，需工单） | 可选 | `zh` |
| `sig` / `output` / `callback` | 数字签名 / JSON\|XML / 回调 | 可选 | JSON |

**响应关键字段（逐字取自文档表）**：顶层 `status`（`1` 成功）、`info`、`count`、`suggestion`（`keywords`、`cities[]`：`name`、`num`、`citycode`、`adcode`）、`pois[]`：`id`、`parent`、`name`、`type`（如「餐饮服务;中餐厅;特色/地方风味餐厅」）、`typecode`、`biz_type`、`address`、`location`（`X,Y`）、`distance`（仅周边搜索有值，米）、`tel`、`postcode`、`website`、`email`、`pcode`、`pname`、`citycode`、`cityname`、`adcode`、`adname`、`entr_location`、`exit_location`、`navi_poiid`、`gridcode`、`alias`、`tag`、`indoor_map`、`indoor_data`、`parking_type`、`photos`。
**`postcode`/`website`/`email`/`pcode`/`citycode`/`adcode`/`entr_location`/`navi_poiid`/`gridcode`/`alias`/`tag`/`indoor_*` 都需要 `extensions=all` 才返回**——这条对「城市/adcode 字段必须能取到」的场景是决定性的。✅

**周边搜索** `GET /v3/place/around`：必填 `key` + `location`，可选 `keywords`、`types`、`radius`（文档中围绕 0–50000）、`sortrule`（`distance` 按距离 / `weight` 综合）、`offset`、`page`、`extensions`；**返回结构与关键字搜索一致**（文档原文：「周边搜索搜索的响应结果的格式由请求参数 output 指定，返回结果见 关键字搜索」）。✅
**ID 查询** `GET /v3/place/detail`：必填 `key` + `id`（单个 POI ID，如 `B0FFFAB6J2`），返回结构同关键字搜索；官方注「如果未能获取到POI详情，请联系商务并提交工单申请高级权限」。✅

### 5.2 驾车路径规划 `GET https://restapi.amap.com/v3/direction/driving`

来源：[路径规划](https://developer.amap.com/api/webservice/guide/api/direction)。✅

**请求参数**：`key`（是）、`origin`（是，`x,y`，**最多 3 个坐标对用 `|` 分隔**，用于算车头角度）、`destination`（是）、`extensions`（文档表中标 **是**，`base`/`all`）、`originid`、`destinationid`、`destinationtype`、`strategy`（默认 `0`；`10~20` 会返回多条路径，其中 **10 = 躲避拥堵+路程较短（对齐高德 APP 默认）**）、`waypoints`（最多 16 点，`;` 分隔）、`avoidpolygons`（最多 32 区域，单区域 ≤81 km²）、`province`+`number`+`cartype`（限行判断 / `0` 普通汽车 `1` 纯电 `2` 插混）、`ferry`、`roadaggregation`、`nosteps`、`sig`、`output`、`callback`。✅
**响应关键字段**：`status`、`info`、`count`、`route.origin`、`route.destination`、`route.taxi_cost`（`extensions=all` 才返回）、`route.paths[]`：`distance`（米）、`duration`（秒）、`strategy`、`tolls`（元）、`restriction`（`0` 已规避限行 / `1` 无法规避）、`traffic_lights`、`toll_distance`、`steps[]`：`instruction`、`orientation`、`road`、`distance`、`tolls`（另含 `polyline`、`action`、`assistant_action` 等路段字段）。✅

### 5.3 地理编码 `GET https://restapi.amap.com/v3/geocode/geo`

来源：[地理/逆地理编码](https://developer.amap.com/api/webservice/guide/api/georegeo)。✅

**请求参数**：`key`（必填）、`address`（必填，规则「国家、省份、城市、区县、城镇、乡村、街道、门牌号码、屋邨、大厦」）、`city`（可选，中文/全拼/citycode/adcode，**不支持县级市**）、`sig`、`output`、`callback`。✅
**响应关键字段**：`status`、`count`、`info`、`geocodes[]`：`country`、`province`、`city`、`citycode`、`district`、`street`、`number`、`adcode`、`location`、`level`（匹配级别）。官方提示：「部分返回值当返回值存在时，将以字符串类型返回；当返回值不存在时，则以数组类型返回。」——**这是一条必须写进解析代码的类型陷阱**。✅
**逆地理编码** `GET /v3/geocode/regeo`：必填 `key` + `location`（经度在前，**小数点后不超过 6 位**），可选 `poitype`、`radius`（0~3000，默认 1000，米）、`extensions`（`base`/`all`）、`roadlevel`、`homeorcorp`（`0/1/2`）、`sig`、`output`、`callback`。响应：`status`、`info`、`regeocode.addressComponent`：`country`、`province`、`city`（**直辖市与省直辖县该字段返回为空**）、`citycode`、`district`、`adcode`、`township`、`towncode`、`neighborhood` 等。✅

### 5.4 天气查询 `GET https://restapi.amap.com/v3/weather/weatherInfo`

来源：[天气查询](https://developer.amap.com/api/webservice/guide/api/weatherinfo)（最后更新 2025-03-18）。✅

**请求参数**：`key`（必填）、`city`（必填，**只能传 adcode**，「输入城市的 adcode」）、`extensions`（`base` 实况 / `all` 预报）、`output`。官方提示原文：「实况天气每小时更新多次，预报天气每天更新 3 次，分别在 8、11、18 点左右更新……请以接口返回数据的 **reporttime** 字段为准。」
**响应关键字段**：顶层 `status`、`count`、`info`、`infocode`（`10000` 代表正确）；实况 `lives[]`：`province`、`city`、`adcode`、`weather`、`temperature`、`winddirection`、`windpower`、`humidity`、`reporttime`；预报 `forecast[]`：`city`、`adcode`、`province`、`reporttime`、`casts[]`：`date`、`week`、`dayweather`、`nightweather`、`daytemp`、`nighttemp`、`daywind`、`nightwind`、`daypower`、`nightpower`。✅

### 5.5 官方 Node MCP 包实际调用的 REST 端点（交叉验证，逐字取自包内源码）

| tool | 端点 | 额外固定参数 |
|---|---|---|
| `maps_regeocode` | `https://restapi.amap.com/v3/geocode/regeo` | `source=ts_mcp` |
| `maps_geo` | `https://restapi.amap.com/v3/geocode/geo` | `source=ts_mcp` |
| `maps_ip_location` | `https://restapi.amap.com/v3/ip` | `source=ts_mcp` |
| `maps_weather` | `https://restapi.amap.com/v3/weather/weatherInfo` | `extensions=all`、`source=ts_mcp` |
| `maps_search_detail` | `https://restapi.amap.com/v3/place/detail` | `source=ts_mcp` |
| `maps_bicycling` | `https://restapi.amap.com/v4/direction/bicycling` | `source=ts_mcp` |
| `maps_direction_walking` | `https://restapi.amap.com/v3/direction/walking` | `source=ts_mcp` |
| `maps_direction_driving` | `https://restapi.amap.com/v3/direction/driving` | `source=ts_mcp` |
| `maps_direction_transit_integrated` | `https://restapi.amap.com/v3/direction/transit/integrated` | `source=ts_mcp` |
| `maps_distance` | `https://restapi.amap.com/v3/distance` | `source=ts_mcp` |
| `maps_text_search` | `https://restapi.amap.com/v3/place/text` | `citylimit`、`source=ts_mcp` |
| `maps_around_search` | `https://restapi.amap.com/v3/place/around` | `source=ts_mcp` |

✅（`@amap/amap-maps-mcp-server@0.0.8` → `build/index.js` 第 249–760 行逐处核对）

---

## 6. 火车数据：`drfccv/mcp-server-12306`

本报告**只读仓库与文档，未运行该项目**。数据取时点 2026-10-10。✅

### 6.1 仓库现状

| 项 | 值 |
|---|---|
| 仓库 | [drfccv/mcp-server-12306](https://github.com/drfccv/mcp-server-12306) |
| 最后提交 | **2026-09-30**（`chore: 更新车站数据20260930`，签名已验证） |
| 近 8 次提交 | 2026-09-30 / 09-26（车站数据 + 全量升级依赖）/ 08-22 / 08-22 / 08-07（`feat: upgrade to MCP SDK v2, extract shared core module, engineering refactor`）/ 08-01 / 07-17（`fix: 修正query_transfer的url`） |
| stars / forks / open issues | 406 / 59 / **1** |
| License | **MIT**（`LICENSE` 文件，MIT，`Copyright (c) 2026 drfccv`） |
| 语言 / 归档 | Python / 未归档 |
| 分发 | PyPI 包名为 `mcp-server-12306`（README badge 指向 [pypi.org/project/mcp-server-12306](https://pypi.org/project/mcp-server-12306)），另有 Docker Hub 镜像 `drfccv/mcp-server-12306` |

### 6.2 open issues 里有没有人报告「接口失效 / 风控」

**当前 open issue 只有 1 个（#8「mcp服务连接dify出错」，2026-03-16，0 评论），不是失效报告。** ✅ 但**历史上有明确的风控/失效报告**，且都已被关闭：✅

| # | 状态 | 日期 | 标题 | 关键内容 |
|---|---|---|---|---|
| **13** | closed | 2026-07-07 | `query_transfer` 无法正常使用 | 报告原文：「一直弹"**12306反爬拦截或数据异常**，请稍后重试"，稍等重试也不行。**其他接口没这个情况**」；作者 2026-07-17 回复：「**请求格式被修改导致的，已更新**」 |
| **5** | closed | 2025-09-19 | 12306接口返回异常 | 用户贴图并问「这个是我自身的网络问题吗，一直是这样的」；作者 2025-09-26 回复：「现在拉取更新看看有没有恢复」 |
| 10 / 9 / 2 / 7 等 | closed | 2026-05 / 2025-06 | 「出错了」「.result」等 | 均为调用/解析类报错，已关闭 |

→ 事实层面：**该项目的失败模式是「12306 变更 + 反爬拦截」，作者靠跟着改请求格式修复；一次集中修复窗口在 2026-07-17。** 社区侧对「接口可能随时失效」的判断成立。✅

### 6.3 实际请求的 endpoint（逐字取自源码）

来源：`src/mcp_12306/services/ticket_service.py`（1031 行）顶部端点表。✅

```python
"init":                "https://kyfw.12306.cn/otn/leftTicket/init",
"query_left_ticket":   "https://kyfw.12306.cn/otn/leftTicket/queryI",
"query_transfer":      "https://kyfw.12306.cn/lcquery/queryG",
"query_price":         "https://kyfw.12306.cn/otn/leftTicketPrice/queryAllPublicPrice",
"query_route_stations":"https://kyfw.12306.cn/otn/czxx/queryByTrainNo",
```

请求头中固定带 `Referer: https://kyfw.12306.cn/otn/leftTicket/init` 与 `Origin: https://kyfw.12306.cn`。✅
注意 `queryI` 这个 `I` 后缀——[Joooook/12306-mcp 在 2026-07-30 的修复](https://api.github.com/repos/Joooook/12306-mcp/commits) 是「改为**动态获取查询 url**」，说明 12306 会轮换该后缀（`queryA`/`queryB`/…）。**硬编码 `queryI` 是一个已知的失效点。** ✅

### 6.4 工具清单与必填参数（README 表格逐字）

| 工具名 | 功能 | 必填参数 |
|---|---|---|
| `query-tickets` | 余票 / 车次 / 座席 / 时刻一站式查询 | `from_station`、`to_station`、`train_date` |
| `query-ticket-price` | 实时查询车次票价 | `from_station`、`to_station`、`train_date` |
| `search-stations` | 车站模糊搜索（中文 / 拼音 / 简拼 / 三字码） | `query` |
| `query-transfer` | 中转换乘方案查询 | `from_station`、`to_station`、`train_date` |
| `get-train-route-stations` | 查询列车经停站及时刻表 | `train_no`、`from_station`、`to_station`、`train_date` |
| `get-train-no-by-train-code` | 车次号 → 官方唯一编号 | `train_code`、`from_station`、`to_station`、`train_date` |
| `get-current-time` | 当前时间与相对日期 | 无 |

✅ 另：项目支持 **Stdio 与 Streamable HTTP 双传输**，HTTP 默认 `0.0.0.0:8000`、路径 `/mcp`（环境变量 `SERVER_HOST` / `SERVER_PORT`），并暴露 `/schema/tools`（GET，全部工具 JSON Schema）；README 自称「基于 MCP SDK v2，自动兼容握手时代（2025-11-25）与现代协议（2026-07-28）」。✅

### 6.5 其它更活跃的 12306 只读实现

| 仓库 | stars | 最后推送 | License | 性质 |
|---|---|---|---|---|
| [drfccv/mcp-server-12306](https://github.com/drfccv/mcp-server-12306) | 406 | **2026-09-30** | MIT | Python MCP（MCP SDK v2），双传输；**本次对比中「有实质维护动作」最晚的一个** |
| [Joooook/12306-mcp](https://github.com/Joooook/12306-mcp) | **2332** | 2026-07-31 | MIT | 关注度最高的 12306 MCP（Node/TS），7 个 tool；open issues 10 个 |
| [zanedonkey/dsh-tool-12306](https://github.com/zanedonkey/dsh-tool-12306) | 13 | **2026-10-09** | MIT | TypeScript，DeepSeek Harness 原生查询工具（非 MCP）；描述为 "Native China Railway 12306 query tools for DeepSeek Harness" |
| [boy-373/12306-train-mcp](https://github.com/boy-373/12306-train-mcp) | 0 | 2026-09-09 | MIT | 只读余票 MCP |
| [TakeruF/china-rail-mcp](https://github.com/TakeruF/china-rail-mcp) | 0 | 2026-09-03 | MIT | 自称「只读型 MCP 服务器」 |
| [php737/train-12306](https://github.com/php737/train-12306) | 1 | 2026-10-06 | NOASSERTION | CLI（「只查不卖，不碰账号和支付」） |
| [boy-373/train-query-mcp](https://github.com/boy-373/train-query-mcp) | 0 | 2026-08-30 | 无 | 免费远程 MCP（URL 直连） |

✅ 检索方式：[GitHub Search API `12306 in:name,description` sort=updated](https://api.github.com/search/repositories?q=12306+in:name,description&sort=updated&order=desc)，共 3,175 个结果，上表取前 25 中的只读查询实现。
**结论：只读查询这一档里，`drfccv` 与 `Joooook` 是两个主要实现，前者仍在小步维护（车站数据 + 依赖），后者功能面更被认可但 2026-07-31 后无提交。** ✅

### 6.6 `Joooook/12306-mcp` 的失效证据（对照参考）

- issue #64（closed，2026-07-30）：「**get-tickets 持续返回 "get tickets data failed"**……其他所有工具（6个）均正常工作」；作者同日回复「[v0.3.10] 已修复」。
- issue #57（closed，2026-06-24）：「Error: **get cookie failed. Check your network.**」；作者回复「检查 mcp 所在环境的网络情况，我这边测试是能够正常获取的」（即社区环境侧被 12306 拒）。
- 2026-07-30 提交「fix: 修复 `get-tickets`，改为**动态获取查询 url**」。
✅ 这三条与 6.2 共同说明：**12306 侧的 URL 轮换与 cookie/风控是这类项目的主要故障源，而非代码质量。**

### 6.7 12306 官方口径

本次未新增核实，沿用 [2026-travel-data-sources.md](./2026-travel-data-sources.md) 第 2 节结论（官方从未向第三方开放接口）。✅

---

## 7. 本次未能确认的事项（❓ 汇总）

1. **托管端 `https://mcp.amap.com/mcp` 的 `tools/list` 结果**：tool 名称、每个 tool 的 JSON Schema、是否有 `maps_*` 之外的 `personal_map` / 导航 / 打车 tool。需要有效 key 实测。
2. **托管端是否支持 header 传 key**（官方只给 URL query 形式）。
3. **MCP 调用消耗配额的官方口径**：现为推断（Web 服务 Key + 「配额共享平台：API」+ 无独立报价）。需控制台计费说明实测。
4. **个人认证账号能否自助购买流量包**：协议 3.1 允诺，公告只说「未认证」不能买；未登录控制台验证。
5. **`langchain-mcp-adapters` 与 `langgraph 1.2.14` 的兼容性**：该包不声明 langgraph 依赖，官方无数值化兼容矩阵，仅描述性声称可用于 LangGraph agents。
6. **中文协议第 5 章及以后**是否另有与数据使用相关的条文：本次逐条检索到 1–4、6、7、8、9、10 章相关关键词，未逐行通读全文其余部分。
