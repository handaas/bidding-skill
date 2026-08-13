# MCP 工具参考 — bidding-mcp-server

本 skill 连接的 MCP server：`handaas-mcp-server/bidding-mcp-server`（“标讯大数据”）。

> **重要**：标讯统计类工具（win_stats / tender_stats / procurement_stats / bidding_info / planned）入参为 `matchKeyword`（**企业全称** / 注册号 / 统一社会信用代码 / 企业 id）+ `keywordType`；
> `bid_search` 是**招投标市场检索**，`matchKeyword` 为搜索关键词（默认按最新发布时间返回全部），与企业主体无关。当用户只给企业关键词时，必须先调关键词模糊查询补全全称。

## 通用约定

- `keywordType` 枚举：`name`（企业名称）/ `nameId`（企业 id）/ `regNumber`（注册号）/ `socialCreditCode`（统一社会信用代码）。
- 分页：`pageIndex` 从 1 开始；`pageSize` 单页最多 50。

---

## 工具清单

### 1. `bid_bigdata_bid_win_stats` — 中标信息统计

用途：获取企业中标信息统计（标的分布、金额分布、区域分布、中标趋势）。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `matchKeyword` | string | 是 | 企业全称 / 注册号 / 统一社会信用代码 / 企业 id |
| `keywordType` | string | 否 | 主体类型：name / nameId / regNumber / socialCreditCode |

返回：
- `winbidAmountStatList`（中标金额分布：range/percent/count）、`winbidAreaStat`（区域分布：area/count）、`winbidStatList`（中标标的分布：subjectMatter/count）、`winbidTrend`（中标趋势：year/count）。

product_id：`6707813f7427e966078e391d`。

---

### 2. `bid_bigdata_bidding_info` — 招投标参与明细

用途：查询企业参与的招投标信息（公告类型、项目地区、公告详情、角色）。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `matchKeyword` | string | 是 | 企业全称 / 注册号 / 统一社会信用代码 / 企业 id |
| `keywordType` | string | 否 | 主体类型 |
| `pageIndex` | int | 否 | 从 1 开始 |
| `pageSize` | int | 否 | 单页最多 50（默认 10） |

返回（list + `total`）：`biddingId`、`title`（公告标题）、`infoType`（公告类型）、`role`（招投标角色：招标/中标）、`projectRegion`（项目地区 dict）、`publishDate`、`subjectMatterList`（标的物）、`projectAmount`、`winningBidderList`（中标企业）、`purchasingBidderList`（招标企业）。

product_id：`66bf124bf134a4c21b4fc2fa`。

---

### 3. `bid_bigdata_tender_stats` — 招标信息统计

用途：获取企业招标信息统计（标的分布、金额分布、区域分布、招标趋势）。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `matchKeyword` | string | 是 | 企业全称 / 注册号 / 统一社会信用代码 / 企业 id |
| `keywordType` | string | 否 | 主体类型 |

返回：`tenderAmountStatList`、`tenderAreaStat`、`tenderStatList`、`tenderTrend`（结构与中标统计对称）。

product_id：`6707813f7427e966078e392f`。

---

### 4. `bid_bigdata_procurement_stats` — 采购信息统计

用途：获取企业采购统计（采购产品分布、采购区域分布、采购数量、客户数）。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `matchKeyword` | string | 是 | 企业全称 / 注册号 / 统一社会信用代码 / 企业 id |
| `keywordType` | string | 否 | 主体类型 |

返回：`purchasingProductStatList`（采购产品分布：product/count/percent）、`purchasingAreaStatList`（采购区域分布：area/times 客户数）。

product_id：`6725e5b9ba65854594baebbc`。

---

### 5. `bid_bigdata_fuzzy_search` — 关键词模糊查询企业

用途：根据企业名称 / 人名 / 品牌 / 产品 / 岗位等关键词模糊查询企业列表，用于补全企业全称。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `matchKeyword` | string | 是 | 匹配关键词 |
| `pageIndex` | int | 否 | 默认 1 |
| `pageSize` | int | 否 | 单页最多 50 |

返回：`total` + 企业列表。

product_id：`675cea1f0e009a9ea37edaa1`。

---

### 6. `bid_bigdata_bid_search` — 招投标市场检索（复杂多过滤条件）

用途：按类型/地区/金额/时间/招标单位类型等过滤条件检索招投标公告。适合政府采购找项目、企业找投标机会、招投标市场分析。**与企业主体无关**。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `matchKeyword` | string | 否 | 搜索关键词（默认按最新发布时间返回全部） |
| `biddingType` | list of string | 否 | 信息类型枚举（招标预告/招标公告/变更补充/中标公告/采购意向/废标终止），可多选。格式：`["招标公告","中标公告"]` |
| `biddingRegion` | list of list of string | 否 | 项目地区（省、市），多选。格式：`[["福建省","厦门市"]]` |
| `biddingAnncPubStartTime` | string | 否 | 发布开始日期，如 `2024-08-01` |
| `biddingAnncPubEndTime` | string | 否 | 发布结束日期，如 `2024-11-01` |
| `searchMode` | string | 否 | 搜索模式：标题匹配 / 标的物匹配 / 全文匹配 |
| `biddingProjectMaxAmount` | float | 否 | 项目金额最大值（万） |
| `biddingProjectMinAmount` | float | 否 | 项目金额最小值（万） |
| `biddingPurchasingType` | string | 否 | 招标单位类型（政府/学校/医院/公安/部队/企业），多个用英文逗号分隔，如 `政府,学校` |
| `pageIndex` | int | 否 | 默认 1 |
| `pageSize` | int | 否 | 单页最多 50 |

> 注意：上游 MCP 对 `biddingType` / `biddingRegion` 期望 list 字符串（JSON 字符串）。compose_report.py 的 `--bidding-type` / `--bidding-region` 传入字符串即可，MCP 端会 `json.loads`。

返回（list + `total`）：`biddingId`、`biddingInfoType`（公告类型）、`biddingProjectType`（项目类型）、`biddingPublishTime`、`biddingEndTime`、`biddingProjectID`、`biddingRegion`、`biddingAnncTitle`、`biddingContent`、`biddingAgentInfoList`、`biddingPurchasingInfoList`、`biddingWinningInfoList`、`hasFile`。

product_id：`66bf124bf134a4c21b4fc34c`。

---

### 7. `bid_bigdata_planned_projects` — 拟建项目

用途：查询企业拟建公告信息（建设地点、内容、待采设备、发布/评审时间）。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `matchKeyword` | string | 是 | 企业全称 / 注册号 / 统一社会信用代码 / 企业 id |
| `pageIndex` | int | 否 | 默认 1 |
| `pageSize` | int | 否 | 单页最多 50（默认 10） |
| `keywordType` | string | 否 | 主体类型 |

返回（list + `total`）：`ppId`、`ppTitle`（项目名称）、`ppContent`（项目内容）、`ppRegion`（建设地点 dict）、`ppPublishTime`、`ppApprovalTime`、`deviceList`（待采设备 list）。

product_id：`66f3d8c064bd2be52d68a134`。

---

## 推荐调用顺序（企业报告编排）

1. （若仅有关键词）`bid_bigdata_fuzzy_search` → 取 `name` 作为全称。
2. `bid_bigdata_bid_win_stats` → 中标统计。
3. `bid_bigdata_tender_stats` → 招标统计。
4. `bid_bigdata_procurement_stats` → 采购统计。
5. `bid_bigdata_bidding_info` → 招投标参与明细。
6. `bid_bigdata_planned_projects` → 拟建项目。

## 市场检索编排

`bid_bigdata_bid_search`（独立流程，非企业主体）→ 检索明细。
