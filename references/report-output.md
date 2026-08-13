# 报告输出 — 标讯大数据报告

本文件规定 `bidding-report` skill 产出的报告结构、质量底线与渲染工作流。所有产物遵循 `AGENTS.md` 的统一 JSON 骨架与本 skill 的领域裁剪。

## 默认展示模式

- HTML：可分享 / 可交付的可视化报告；独立本地文件，内嵌 CSS，无调试 / 内部段落。
- Markdown：知识库 / wiki / PRD / 后续手工编辑。
- JSON：系统集成或二次处理。

`compose_report.py` 通过 `--report-output <path>` 同时产出 HTML + Markdown；`--output <path>` 产出 JSON。`render_report.py` 可基于已有 JSON 重渲染。

## 两种报告模式

本 skill 支持两种模式（`--enterprise` 与 `--search` 互斥）：

1. **企业标讯报告**（`--enterprise`）：以企业为主体，调用中标/招标/采购统计 + 招投标明细 + 拟建项目。
2. **招投标市场检索报告**（`--search`）：以关键词 + 过滤条件检索招投标公告，不绑定企业主体。

## 报告结构（7 章）

1. **报告摘要**：分析对象、数据覆盖范围、核心发现、关键指标卡。
2. **查询对象与口径**：企业全称 / 检索关键词、匹配方式、数据范围、产品、局限。
3. **数据总览**：招投标参与记录、中标标的数、招标标的数、采购产品数、拟建项目数 / 检索命中数等指标卡。
4. **核心分析**（标讯专属子章节，由 `core_analysis.sections` 驱动渲染）：
   - 企业模式：中标标的分布、中标金额分布、中标区域分布、中标趋势；招标（同结构）；采购产品分布、采购区域分布；招投标参与明细；拟建项目。
   - 市场检索模式：招投标检索明细（公告标题 / 类型 / 项目类型 / 地区 / 时间 / 截止时间 / 项目编号）。
5. **代表性记录**：代表性招投标记录 Top N。
6. **特征与洞察**：结构化解读（招投标活跃度 / 中标标的集中度 / 招标需求方向 / 采购产品结构），每条含 `feature` / `evidence` / `interpretation`。
7. **数据口径与来源**：MCP server、数据产品、生成时间、是否 dry-run、是否市场检索模式。

## 质量底线

- 报告脱离 Skill 上下文也可独立阅读；正文只见标讯事实与结构化数据。
- 绝不出现工具名、入参（如 `matchKeyword=...`）、product_id、内部字段名、空表、调试信息。
- HTML 采用研究报告视觉风格：A4 风、灰色顶部条纹、蓝色报告横幅、左侧目录 / 范围侧栏、深蓝章节标题、深蓝表头、浅蓝斑马行、打印友好分页。
- 数据为空时明确说明数据范围 / 口径，不渲染空表、不臆造事实。
- 绝不打印 `secret_id` / `secret_key` / 签名 / token / 原始签名请求。
- 自动补全企业全称时，在报告口径中说明“由关键词模糊查询补全”。
- 市场检索模式须在口径中明确“按检索条件命中”，与企业主体统计区分。

### 数据格式约束（铁律）

以下约束适用于 compose_report.py 组装数据与 render_report.py 渲染输出的全过程：

1. **嵌套 JSON 字符串必须解析**：MCP 返回的某些字段（如 `regCapital`、`addressValue`、`subscriptionDetail`）可能是 JSON 字符串（例：`{"coinType":"人民币","value":430000000.0}`）。compose 层必须调用 `_unwrap_json_str()` / `_parse_reg_capital()` / `_flatten_addr()` 解析为可读文本（如"4.30 亿 人民币"、"浙江省杭州市滨江区..."）。绝不在报告正文、表格单元格或指标值中输出原始 JSON 字符串。

2. **section 标题必须用中文**：`core_analysis.sections` 数组中每个 section 的 `title` 字段必须使用中文（如"企业基本信息"、"对外投资"、"股东信息"）。`key` 字段用英文 snake_case 供程序索引，但 `title` 绝不可显示英文 key。即使缺少 sections 数组，渲染器回退逻辑也内置了 `_TITLE_MAP` 映射。

3. **指标值可读化**：所有 `metrics` 的 `value` 字段必须格式化为人类可读形式：
   - 金额：`10995210218.0` → `109.95 亿 人民币`（≥1 亿用亿，≥1 万用万）
   - 地址：嵌套 dict → 省+市+区拼接 或取 `value` 字段
   - 比率：`0.8858` → `88.58%`
   - 日期：保持 `yyyy-MM-dd` 格式
   - "-" 表示字段缺失（MCP 未返回）；`0` 表示真实为零

4. **企业画像指标提取**：有 fuzzy_search 的 skill 必须从返回的 record 中提取 `regCapitalValue` / `foundTime` / `operStatus` / `enterpriseType` / `legalRepresentative`，通过 `_enrich_metrics_with_profile()` 追加为指标卡。

5. **分布派生指标**：`_derive_core_metrics()` 从 core_analysis 各 section 计算分布指标（CR3 集中度、覆盖城市/平台/类目数、价格区间、正面占比等），确保指标总数 M ≥ 6。

## 工作流

```bash
# 1. 干跑（不调真实 API，用样例数据组装报告骨架）
python scripts/compose_report.py \
  --enterprise "示例科技有限公司" \
  --dry-run \
  --output output/bidding.json \
  --report-output output/bidding.html

# 2. 企业报告 + 渲染（需 MCP 连接就绪）
python scripts/compose_report.py \
  --enterprise "示例科技有限公司" \
  --output output/bidding.json \
  --report-output output/bidding.html

# 3. 招投标市场检索
python scripts/compose_report.py \
  --search "智慧城市" \
  --bidding-region '[["福建省","厦门市"]]' \
  --bidding-type '["招标公告","中标公告"]' \
  --pub-start "2025-01-01" --pub-end "2025-12-31" \
  --min-amount 100 --max-amount 5000 \
  --report-output output/market.html

# 4. 重渲染已有 JSON
python scripts/render_report.py --input output/bidding.json --output output/bidding.html
python scripts/render_report.py --input output/bidding.json --output output/bidding.md
```

返回：JSON 路径、HTML 路径、Markdown 路径，以及企业全称映射 / 检索条件与数据口径摘要。
