---
name: bidding-report
description: Use for generating a professional bidding/tender big-data report (标讯大数据报告) from the HandaaS bidding MCP — covering 中标统计、招标统计、采购统计、拟建项目、招投标参与明细、招投标市场检索. Trigger when users ask for “标讯大数据报告”, “标讯分析报告”, “查一家公司的招投标”, “中标统计”, “招标统计”, “采购统计”, “拟建项目”, “招投标市场检索”, “投标机会”, or “采购分析”. Infer the canonical enterprise name (auto-fuzzy-completing a keyword) or market-search keywords/filters, pick the right MCP tools, and produce HTML + Markdown + JSON reports automatically.
---

# 标讯大数据报告

## 用户契约

把“标讯大数据报告”作为面向用户的调用短语。`bidding-report` 仅为内部包名。

当本 skill 处于激活状态：

1. 不要向用户索要 product_id、MCP 工具名、API 字段、内部参数或凭证信息；只接受企业名称、统一社会信用代码、注册号、企业 ID，或招投标市场检索关键词 / 过滤条件。
2. 接受两类自然目标：
   - 企业报告：“查一下某某公司的招投标”“分析这家企业的中标和招标”“给我一份某某公司的标讯报告”。
   - 市场检索：“找最近关于某某的招标公告”“检索福建省厦门市的采购意向”“找金额在 100-500 万的中标公告”。
3. 当用户只给企业关键词时，自动调用关键词模糊查询补全企业全称，再查标讯详情。
4. 优先使用 MCP 连接（`BIDDING_MCP_URL` Remote MCP 或本地 `handaas-mcp-server/bidding-mcp-server`）；不要让用户处理签名或凭证。
5. 同时产出 HTML（可分享交付）、Markdown（知识库 / wiki）、JSON（系统集成）三类产物。
6. 报告正文必须是专业研究报告风格：只见标讯事实与结构化数据，绝不出现工具名、入参、product_id、内部字段或空表。
7. 绝不打印 `secret_id`、`secret_key`、签名、token 或原始签名请求。
8. 默认 dry-run；真实付费 / 凭证调用需用户明确要求且 MCP 连接配置完整。
9. 数据为空时明确说明数据范围 / 口径，不渲染空表、不臆造事实。


- MCP 返回的嵌套 JSON 字符串（如金额 `{"coinType":"人民币","value":430000000.0}`、地址 `{"city":"杭州市",...}`）必须解析为可读文本（如"4.30 亿 人民币"、"浙江省杭州市"），绝不在报告正文、表格或指标中输出原始 JSON 字符串。
- 报告所有章节标题、指标卡标签必须用中文；`core_analysis.sections` 的 `title` 字段必须中文，不可显示英文 key（如 `holders`、`investments`）。
- 指标值必须可读化：金额格式为"X 亿/万 + 币种"，地址拼接省市区，比率显示百分号。详见 `references/report-output.md` 的「数据格式约束」。

## MCP 服务入口

- 上游 MCP 项目：`handaas-mcp-server/bidding-mcp-server`（位于 `HANDAAS_MCP_SERVER_ROOT` 或本仓库同级目录）。
- Remote MCP：设置环境变量 `BIDDING_MCP_URL`（streamable-http），可选 `BIDDING_MCP_TOKEN`。
- 本地 MCP：设置 `HANDAAS_MCP_SERVER_ROOT` 指向 `handaas-mcp-server` 仓库根目录；该 server 自己的 `.env` 提供 `INTEGRATOR_ID` / `SECRET_ID` / `SECRET_KEY`。
- 首次真实查询前，运行 `scripts/mcp_client.py ping` 与 `scripts/mcp_client.py list-tools` 验证连通。

## 按需加载 references

- 不清楚该 MCP 有哪些工具、参数、返回字段、何时调用：`references/mcp-tools-reference.md`。
- 报告结构、章节、质量底线、渲染工作流：`references/report-output.md`。

## 意图路由

| 用户意图 | 内部工作流 |
| --- | --- |
| 查一家公司的全维度标讯报告 | 调中标/招标/采购统计 + 招投标明细 + 拟建；`compose_report.py --enterprise ...` |
| 只要中标 / 招标 / 采购某一维度 | 仅调对应工具，按统一骨架组装 |
| 找投标机会 / 招投标市场检索（非企业） | `compose_report.py --search ...` + 过滤条件（类型/地区/金额/时间/单位类型） |
| 按金额区间 / 时间区间 / 地区过滤检索 | `--min-amount` / `--max-amount` / `--pub-start` / `--pub-end` / `--bidding-region` |
| 查拟建项目 | `compose_report.py --enterprise ...`（含拟建章节）或手动调 `bid_bigdata_planned_projects` |
| 只给关键词（不是全称） | 先 `bid_bigdata_fuzzy_search` 补全全称，再查详情 |
| 只要 JSON / 只要 HTML / 只要 Markdown | 用 `--output`（JSON）或 `--report-output`（HTML+MD），或 `render_report.py` 重渲染 |
| 连接 / 工具不存在 / 传参错误 | `mcp_client.py ping` / `list-tools` 排查；报脱敏后的缺失项 |

## Golden path for 标讯大数据报告

### 企业报告模式

1. **解析企业全称**：若输入含“公司/集团/有限/院/厂/中心/事务所/合作社/合伙”等后缀视为全称；否则调 `bid_bigdata_fuzzy_search` 取首个命中。
2. **调用标讯工具**：`bid_bigdata_bid_win_stats`（中标统计：标的/金额/区域/趋势）、`bid_bigdata_tender_stats`（招标统计）、`bid_bigdata_procurement_stats`（采购统计）、`bid_bigdata_bidding_info`（招投标参与明细）、`bid_bigdata_planned_projects`（拟建项目）。入参为 `matchKeyword`（企业全称）+ `keywordType`。
3. **组装统一报告**：核心分析含中标标的/金额/区域分布+趋势、招标标的/金额/区域分布+趋势、采购产品/区域分布、招投标参与明细、拟建项目（每节均为表格）。
4. **渲染三件套**：`compose_report.py --enterprise ... --output ... --report-output ...` 直接产出 JSON + HTML + Markdown。

### 市场检索模式

1. **构造检索条件**：`--search <关键词>` + 可选过滤（`--bidding-type` / `--bidding-region` / `--pub-start` / `--pub-end` / `--search-mode` / `--purchasing-type` / `--min-amount` / `--max-amount`）。
2. **调用 `bid_bigdata_bid_search`**：返回命中公告明细。
3. **组装统一报告**：核心分析为招投标检索明细表。
4. **渲染三件套**。

返回：JSON、HTML、Markdown 文件路径，以及企业全称映射 / 检索条件与数据口径。

## 脚本速查

```bash
# 校验连接配置（脱敏）
python scripts/validate_config.py --allow-placeholders

# 连通性自测
python scripts/mcp_client.py ping
python scripts/mcp_client.py list-tools

# 干跑（不调真实 API，用样例数据组装报告骨架）
python scripts/compose_report.py \
  --enterprise "示例科技有限公司" \
  --dry-run \
  --output output/bidding.json \
  --report-output output/bidding.html

# 企业报告 + 渲染（需 MCP 连接就绪）
python scripts/compose_report.py \
  --enterprise "示例科技有限公司" \
  --output output/bidding.json \
  --report-output output/bidding.html

# 招投标市场检索（找投标机会）
python scripts/compose_report.py \
  --search "智慧城市" \
  --bidding-region '[["福建省","厦门市"]]' \
  --bidding-type '["招标公告","中标公告"]' \
  --pub-start "2025-01-01" \
  --pub-end "2025-12-31" \
  --min-amount 100 --max-amount 5000 \
  --report-output output/market.html

# 手动调单个工具
python scripts/mcp_client.py call-tool \
  --tool bid_bigdata_bid_win_stats \
  --arguments-json '{"matchKeyword": "示例科技有限公司", "keywordType": "name"}'

# 重渲染已有 JSON
python scripts/render_report.py --input output/bidding.json --output output/bidding.html
python scripts/render_report.py --input output/bidding.json --output output/bidding.md
```

## 输出字段

- `subject`：企业全称 / 检索关键词、匹配方式、是否自动补全。
- `abstract` / `summary`：封面摘要与详细摘要。
- `metrics`：招投标参与记录、中标标的数、招标标的数、采购产品数、拟建项目数 / 检索命中数。
- `caliber`：匹配对象、匹配方式、数据范围、产品、局限。
- `core_analysis`：中标（标的/金额/区域分布+趋势）、招标（同）、采购（产品/区域分布）、招投标参与明细、拟建项目 / 检索明细（每节均为表格，由 `core_analysis.sections` 驱动）。
- `representative_records`：代表性招投标记录 Top N。
- `insights`：结构化解读（招投标活跃度 / 中标标的集中度 / 招标需求方向 / 采购产品结构）。
- `data_source`：MCP server、数据产品、生成时间、是否 dry-run、是否市场检索模式。

若 API 调用失败，明确报出缺失的配置 / 缺失的工具 / MCP 错误 / 参数校验错误 / 上游网络错误，给出 dry-run 命令或配置步骤，绝不暴露密钥。
