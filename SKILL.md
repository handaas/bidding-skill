---
name: bidding-report
description: Use for generating a professional bidding/tender big-data report (标讯大数据报告) from the HandaaS bidding MCP — covering 中标统计、招标统计、采购统计、拟建项目、招投标参与明细、招投标市场检索. Trigger when users ask for “标讯大数据报告”, “标讯分析报告”, “查一家公司的招投标”, “中标统计”, “招标统计”, “采购统计”, “拟建项目”, “招投标市场检索”, “投标机会”, or “采购分析”. Infer the canonical enterprise name (auto-fuzzy-completing a keyword) or market-search keywords/filters, pick the right MCP tools, and produce HTML + Markdown + JSON reports automatically. MCP 服务名称触发词：标讯项目动态。
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

## 付费调用纪律（先规划后查询）

每次真实调用均按接口/页计费，必须先规划再查询，不得默认全量拉取：

1. 每一次业务/工具调用、每一页都可能收费。想算 total / 页数不是无限制取全量的授权。
2. 调用前先推导：需要哪些结论、需要哪些数据维度、工具与参数计划、必要页数与最大调用预算。total 未知时，第一个必要的明细页同时完成 total 发现并直接作为报告数据，绝不为此多付一次（首屏响应必须复用，不重复拉取）。
3. 优先用统计 / 画像 / 聚合接口回答能回答的问题（中标统计、招标统计、采购统计优先）；明细接口仅取结论、图表、代表性记录或用户明确的全量/计数需求所需的行数。只有用户明确要全面报告时才跑全面管线，绝不因为工具存在就全部调用。
4. 在 schema 允许范围内用合理的大 pageSize（≤50），取得所需证据 / 样本即停，且不超出显式预算。更多调用必须有“缺失结论”的正当理由，不能只为填满章节。不得用样本分布冒充全量结论。
5. 复用当前任务 / 报告内的相同请求（含首屏规划数据）；不要为渲染重跑 compose/MCP，用已保存 JSON 本地重渲染。不自动重试、不重复拉取同一统计或明细、不并行独立拉取相同数据。任何补充查询必须先列缺口并复用已返回记录。
6. `total_pages` / `remaining_pages` 是按请求 pageSize 的估算；短而非空页面仍有剩余记录时在预算内继续。只有稳定有效的 total 等于实际扫描条数才算完整采集；错误、提前空页、重复页、total 变化/缺失、数量溢出均视为不完整。显式预算 / 样本停止即部分采集，绝不宣称全量。
7. 预算不足以支撑用户要求的关键结论时：先说明证据缺口与预计需要追加的调用数，再请求扩大授权（提高 `--max-pages`）；不静默降级结论，也不擅自扩大计费范围。

分页收集默认一次明细调用预算 `--max-pages 1`（每明细接口）；明细接口的 total、实际取数、完整性披露写入报告 `data_source.pagination`，报告级去重统计写入 `data_source.call_usage`。

## MCP 服务入口

- MCP 服务当前名称：标讯项目动态（连接仍使用原服务目录标识）。

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
2. **调用标讯工具**：`bid_bigdata_bid_win_stats`（中标统计：标的/金额/区域/趋势）、`bid_bigdata_tender_stats`（招标统计）、`bid_bigdata_procurement_stats`（采购统计）、`bid_bigdata_bidding_info`（招投标参与明细，分页，默认 1 页预算）、`bid_bigdata_planned_projects`（拟建项目，分页，默认 1 页预算）。入参为 `matchKeyword`（企业全称）+ `keywordType`；明细按 total 驱动、在 `--max-pages`（默认 1）预算内翻页，超出预算时报告披露未纳入条数而非宣称全量。
3. **组装统一报告**：核心分析含中标标的/金额/区域分布+趋势、招标标的/金额/区域分布+趋势、采购产品/区域分布、招投标参与明细、拟建项目（每节均为表格）。
4. **渲染三件套**：`compose_report.py --enterprise ... --output ... --report-output ...` 直接产出 JSON + HTML + Markdown。

### 市场检索模式

1. **构造检索条件**：`--search <关键词>` + 可选过滤（`--bidding-type` / `--bidding-region` / `--pub-start` / `--pub-end` / `--search-mode` / `--purchasing-type` / `--min-amount` / `--max-amount`）。
2. **调用 `bid_bigdata_bid_search`**：返回命中公告明细；按 total 驱动、在 `--max-pages`（默认 1）预算内翻页，超出预算时披露未纳入条数。
3. **组装统一报告**：核心分析为招投标检索明细表。
4. **渲染三件套**。

返回：JSON、HTML、Markdown 文件路径，以及企业全称映射 / 检索条件与数据口径。

## 内容整理与交付审校

1. **先读实际明细**：打开本次 `report.json` 的 `core_analysis` 与 `metrics`，逐条核对标的、金额、地区、客户与日期；`quality_report.coverage_pct` 只是章节填充率，不能代替内容检查。
2. **集中度基准**：上游标的分布常只返回前 5 项且 `占比` 是全体占比。不得用“前 5 项数量合计”当分母重算 CR3（会把 1% 的标的写成 30%）；有 `占比` 时按占比合计，无占比时明确写“返回项内 CR3，基准为返回项合计”。
3. **样本与全量**：`招投标参与记录` 用上游 total；金额、信息类型、客户、角色只统计当前展示记录时必须写明“本次展示 N 条中”，缺失金额保留缺失，不按 0 计。
4. **角色冲突**：`公告类型` 与 `招投标角色` 可能不一致（如“中标公告”配“招标”）。保留上游值并提示回看原文，不按类型改写角色，也不据此判断供应/采购身份。
5. **拟建项目**：同一项目可能有多条审批/备案公告（项目名称相同、时间不同），记录数不等于项目数；按项目名称 + 项目代码归组核对，不删除旧公告。`项目内容` 是上游原文摘录，已截断时标注“原文摘录”。
6. **趋势**：年份序列按年排序后再比较；最新年度未满全年时排除同比，不得拿最老两个年度当“近年趋势”。峰值并列时列出全部年份。
7. **检索相关性**：市场检索的命中数不是项目数或成交数。标题未含关键词的记录保留但标为“需核对正文”；同题公告可能对应不同地区/采购包，不按标题去重后冒充项目数。
8. **内容整理（正常生成 + 离线修订）**：正常 `build_payload` / `build_search_payload` 与 `--dry-run` 样例生成在写 JSON/HTML/MD 前自动调用 `apply_content_review(report)`；同一函数也可基于已有 JSON 重算上述口径文案与集中度基准，不调用 MCP、不改原始记录字段。离线修订件另存 `output/content-quality-review/<case>/`。

```bash
# 离线重放（不查 MCP；source_sha256 由调用方对原文件计算）
python - <<'PY'
import hashlib, json, sys
from pathlib import Path
sys.path.insert(0, "scripts")
import compose_report as cr
src = Path("examples/01-contractor-bid-profile/report.json")
raw = src.read_bytes()
report = cr.apply_content_review(json.loads(raw), source_sha256=hashlib.sha256(raw).hexdigest())
out = Path("output/content-quality-review/01-contractor-bid-profile")
out.mkdir(parents=True, exist_ok=True)
(out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
PY
```

- **渲染前置检查**：执行会产出含图表 HTML / PDF 的报告命令前，先验证 `node --version` 与本 skill 自带 `assets/vendor/echarts.min.js` 存在；内嵌静态 SVG 的生成需要 Node.js（推荐当前 LTS，无需 npm 包），缺失时报告生成明确报错。查看已生成的 HTML 与 Markdown 输出不需要 Node。

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

# 明确授权扩大明细预算（先按 total 估算页数，确认必要后提高）
python scripts/compose_report.py \
  --enterprise "示例科技有限公司" \
  --max-pages 5 \
  --output output/bidding.json \
  --report-output output/bidding.html

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
- `metrics`：招投标参与记录（上游总量）、中标/招标标的类型数（分布项数，不是项目数）、采购产品类型数、展示记录中标金额合计/单笔均值、展示记录主要类型/采购方数、拟建项目数、中标地区项数 / 检索命中数。
- `caliber`：匹配对象、匹配方式、数据范围、产品、局限。
- `core_analysis`：中标（标的/金额/区域分布+趋势）、招标（同）、采购（产品/区域分布）、招投标参与明细、拟建项目 / 检索明细（每节均为表格，由 `core_analysis.sections` 驱动）。
- `representative_records`：代表性招投标记录 Top N。
- `insights`：结构化解读（招投标活跃度 / 中标标的集中度 / 招标需求方向 / 采购产品结构）。
- `data_source`：MCP server、数据产品、生成时间、是否 dry-run、是否市场检索模式；分页接口的 `pagination`（每接口上游 total / 请求页数 / 取得条数 / 未纳入条数 / 完整性与停止原因）与 `call_usage`（本报告实际执行与复用的请求数）。

若 API 调用失败，明确报出缺失的配置 / 缺失的工具 / MCP 错误 / 参数校验错误 / 上游网络错误，给出 dry-run 命令或配置步骤，绝不暴露密钥。
