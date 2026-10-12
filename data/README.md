# 离线数据目录

**这里的东西不入库。** `.gitignore` 排除了 `data/*`，只留这个说明文件。

## 为什么需要它

离线实现（`src/data/local.py`）读一份本地 SQLite 快照，用于开发、回归评测、CI 与断网。
它让「评测结果能代表线上行为」这句话有依据——演示与评测走的是同一条代码路径。

## 怎么生成

```bash
python -m scripts.fetch_offline_data              # 全量，约 76 万个要素
python -m scripts.fetch_offline_data --limit 400  # 只取前若干条，够开发用
```

默认写到 `data/offline/places.sqlite`。

## 数据来源与许可

- **来源**：HOT 的中国 POI 导出（上游为 Geofabrik 的 CHN extract），S3 直链公开可下。
- **许可**：ODbL-1.0。义务是**署名**（数据 © OpenStreetMap 贡献者）与**相同方式共享**
  （若对外分发衍生数据库，须同样以 ODbL 授权）。所以快照不入库、不分发。
- 快照的 `meta` 表里记着 `source` / `as_of` / `license`，每条记录都带着它们出去。

## 离线侧的已知缺口

抓取脚本会把缺失率打出来，这些数决定了哪几条红线离线能断言：

| 字段 | 情况 | 后果 |
|---|---|---|
| `opening_hours` | 缺失约 **98%** | **红线 A3（停靠点在营业时间内）在离线侧做不了** |
| `id` | **不唯一** | 抓取时加 `#2` 后缀消歧并报数；否则主键会静默丢约三万行 |
| `name` | 缺失约 **52%** | 近半数要素无法进候选池——方案里展示不出一个没名字的地点 |
| `adm2_name` | 是**罗马音**（`Harbin`） | **按中文城市名检索取不到结果** |
| `adm2_pcode` | 有（缺失 1.4%） | 但它是 OCHA/HDX 的编码，**不是高德 adcode**，两套不混用 |
| 行政区划 | 无许可明确的来源 | `areas` 表为空，`lookup_area` 返回 `None` |

`RouteResult.basis` 在离线侧恒为 `STRAIGHT_LINE_ESTIMATE`：离线只能给直线距离乘未标定
系数，**那不是路网耗时**。A4 只能用真实实现的 `ROAD_NETWORK` 结果断言，离线值可以跑通
流程、不能当证据。

完整核实过程见 [`docs/research/2026-osm-ecosystem-for-offline-poi.md`](../docs/research/2026-osm-ecosystem-for-offline-poi.md)。
