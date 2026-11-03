# 标讯大数据报告

一个可被本地智能体使用的 HandaaS 标讯大数据 Skill。用户只需要说"使用标讯大数据，分析中国铁建股份有限公司的招投标参与情况和采购画像"，智能体会自动连接 MCP 服务、获取原始数据并编排为结构化报告（HTML + Markdown + JSON + PDF 四件套），内嵌 ECharts 5.x 可视化图表，离线可打开。

> Skill 本身不托管用户数据或凭证。默认通过旷湖SKILL平台一键创建本 Skill 所需的在线 MCP 服务，使用本 Skill 专属 Token（`BIDDING_MCP_TOKEN`）；也支持连接本地部署的 `bidding-mcp-server`，此时凭证由 MCP Server 自己的 `.env` 持有（INTEGRATOR_ID / SECRET_ID / SECRET_KEY），与在线 Token 无关，不在 Skill 内处理。

## 目录

- [一句话安装](#一句话安装)
- [智能体安装约定](#智能体安装约定)
- [快速验证](#快速验证)
- [接入 MCP 服务](#接入-mcp-服务)
- [生成报告](#生成报告)
- [效果预览](#效果预览)
- [命令行用法](#命令行用法)
- [故障排查](#故障排查)

## 一句话安装

在**旷湖SKILL平台**为本 Skill 创建所需在线 MCP 服务后，复制下面整段发给智能体，只替换最后一行的 Token：

```text
请帮我安装并配置 bidding-skill：
1. 阅读并遵循 https://github.com/handaas/bidding-skill 的 SKILL.md 与 README.md，按当前环境规范安装到实际包含 SKILL.md 的目录；保留已有配置，不默认全局注册。
2. 使用旷湖SKILL平台在线 MCP：服务地址见本 README「接入 MCP 服务」，平台返回的地址优先。不部署本地 MCP，不索要 INTEGRATOR_ID / SECRET_ID / SECRET_KEY。
3. 将完整 handaas-token 作为环境变量 `BIDDING_MCP_TOKEN` 注入运行 Python 的进程，并设置 `BIDDING_MCP_URL`；环境变量必须真正到达该进程，只保存文件或在别的终端 export 不算完成。
4. Token 原样保留逗号等字符：不拆分、不解码、不放进 URL、不手动加 Bearer。不要把 Token 写入仓库、SKILL.md、README、示例配置、报告或终端历史；若只能使用仓库外的私有环境文件，权限设为 0600，并由启动器显式加载。不要回显 Token、请求头或原始鉴权错误；Token 注意保管，请勿泄露。
5. 正式执行真实查询：加 --live 生成 HTML / Markdown / JSON 报告；按问题范围使用默认页数预算，不为填模板扩大调用，也不重复请求。
6. 只返回脱敏结果：安装目录、私有配置位置、真实查询调用次数与数据范围、报告路径。缺少地址或 Token 时明确说明缺失项，不要把连接失败说成企业没有数据。

handaas-token：<在此粘贴本人在旷湖SKILL平台获取的完整 Token>
```

Token 只放在运行进程的环境变量或仓库外的私有配置中；用户粘贴本指引即视为授权按默认预算执行真实查询；不要擅自扩大调用范围。

### 注册并创建对接器

1. 打开 [旷湖官网](https://www.handaas.com/) 注册并登录。
2. 进入「数据管理」→「对接器」→「创建对接器」。
3. 选择本 Skill 对应的服务类型「标讯项目动态」。
4. 创建后复制完整 `handaas-token`，按上文注入 `BIDDING_MCP_TOKEN`；Token 注意保管，请勿泄露。

### 智能体安装约定

智能体按以下六步完成安装（本 Skill 为原子 Skill，单域 `bidding-mcp-server`）：

1. 先读本仓库的 SKILL.md 和 README.md，按当前智能体自身的 Skill 安装与依赖约定操作；以实际包含 SKILL.md 的目录为 skill 根目录，保留已有安装与配置，不假设克隆后还嵌套一层同名目录，不默认全局注册。
2. 使用旷湖SKILL平台为本 Skill 一键创建的在线 MCP 服务；Token 由本 Skill 专属变量 `BIDDING_MCP_TOKEN` 提供，所需服务复用同一值。在线安装不克隆 handaas-mcp-server、不启动本地服务、不索要 INTEGRATOR_ID / SECRET_ID / SECRET_KEY。
3. 把完整 Token 保存到本机智能体的私有密钥/环境配置中，并作为 `BIDDING_MCP_TOKEN` 注入运行 Python 脚本的进程；同时把下文服务地址注入 `BIDDING_MCP_URL`。不要只注册智能体原生 MCP 而漏配 Python 进程；不要声称脚本会自动加载 `.env` 或读取 `config.json` 的 `remote_mcp`（当前实现不会）。若宿主没有持久环境机制，可用仓库外的私有环境文件配合宿主启动器显式加载（POSIX 权限 0600，Windows 限当前用户）；无法安全持久化时要明确报告，不要宣称配置完成。
4. Token 是不透明字符串，逗号等字符要完整保留：不拆分、不解码、不写进 URL、不重复添加 Bearer 前缀（客户端自行添加 `Authorization: Bearer`）。只设置本 Skill 专属的 `BIDDING_MCP_TOKEN`；不要配置共享 Token 变量。
5. 先确认所需连接都为 remote（缺少 URL 时脚本可能回退本地，在线流程不得回退）。用 `python scripts/validate_config.py --allow-placeholders`、`python scripts/mcp_client.py ping`、`python scripts/mcp_client.py list-tools` 做验证，只做 initialize / list_tools 元数据握手，不 call_tool；ping 与工具数只证明握手成功，还要把 list-tools 返回的工具名与 SKILL.md / 脚本实际需要的工具对照，空工具列表或缺少所需工具不得宣称业务可用。再按本页"快速验证"与"命令行用法"中的命令，用显式 `--dry-run` 生成离线报告验收。dry-run 只证明本地编排，不证明在线连接与权限；未验证的项写"未验证"，不能伪称可用。若用户的一键指引明确要求正式执行，则完成元数据检查后直接运行不带 `--dry-run` 的报告命令并生成报告。 还须用 `list-tools` 对照 `SKILL.md` 或脚本核对所需工具名，空列表或工具缺失时不得宣称业务可用。
6. 完成后只报告安装位置、配置文件位置、所需服务的脱敏连接信息与工具数、离线报告路径。真实 Token 不得出现在命令参数、日志、回复、仓库、README、SKILL.md、config.example.json、报告或共享配置中。普通安装不等于授权付费数据调用。

## 快速验证

不需要配置 MCP 也能先跑起来，验证报告骨架和图表渲染：

```bash
cd bidding-skill
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/compose_report.py \
  --enterprise "中国铁建股份有限公司" \
  --dry-run \
  --output output/report.json \
  --report-output output/report.html
```

打开 `output/report.html` 即可看到完整报告效果。

## 接入 MCP 服务

`bidding-mcp-server` 是数据接入层。Skill 会自动优先使用 MCP 连接。

### 方式一：使用旷湖SKILL平台在线 MCP（推荐）

在旷湖SKILL平台为本 Skill 一键创建所需的在线 MCP 服务（选择 `标讯大数据`），获取平台 Token，并保存为本 Skill 专属的 `BIDDING_MCP_TOKEN`；同一值供所需服务复用，服务地址以平台提供为准。

设置环境变量（token 配置一次即可）：

macOS / Linux：

```bash
export BIDDING_MCP_TOKEN="<平台完整Token>"
export BIDDING_MCP_URL="https://mcp.handaas.com/bidding/bidding_bigdata"
```

Windows PowerShell：

```powershell
$env:BIDDING_MCP_TOKEN = "<平台完整Token>"
$env:BIDDING_MCP_URL = "https://mcp.handaas.com/bidding/bidding_bigdata"
```

将 `<平台完整Token>` 替换为你在旷湖SKILL平台获取的完整 token。token 由 `BIDDING_MCP_TOKEN` 统一携带，URL 中无需重复填写。

> 上面的示例只配置当前 shell；智能体持久使用必须遵循"智能体安装约定"，把 `BIDDING_MCP_TOKEN` 与 `BIDDING_MCP_URL` 注入实际运行 Python 脚本的进程环境、确保子进程继承，而不是只把值写进文件就以为已生效。

### 方式二：连接本地部署的 MCP 服务

```bash
git clone https://github.com/handaas/handaas-mcp-server
cd handaas-mcp-server/bidding-mcp-server
python3 -m venv mcp_env
source mcp_env/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 填入 INTEGRATOR_ID / SECRET_ID / SECRET_KEY
./start_mcp_server.sh
```

在使用 Skill 的 shell 中指定本地 MCP 地址：

macOS / Linux：

```bash
export BIDDING_MCP_URL="http://127.0.0.1:8000/mcp"
```

Windows PowerShell：

```powershell
$env:BIDDING_MCP_URL = "http://127.0.0.1:8000/mcp"
```

本地 MCP 由你自己的 `.env` 持有凭证，Skill 侧只需要 `BIDDING_MCP_URL`。

### MCP 连接验证

```bash
python scripts/mcp_client.py ping
python scripts/mcp_client.py list-tools
```

以上只做 MCP 元数据握手（initialize / list_tools），不 call_tool，也不代表已授权付费数据调用；ping 与工具数只证明握手成功，还需对照 SKILL.md / 脚本所需工具名。`--dry-run` 只验证本地编排，不能证明在线连接与权限。

## 生成报告

### 真实查询 + 渲染

配置好 MCP 连接后，一条命令生成报告：

```bash
python scripts/compose_report.py \
  --enterprise "中国铁建股份有限公司" \
  --output output/report.json \
  --report-output output/report.html \
  --pdf-output output/report.pdf
```

同时产出四个文件：

| 文件 | 说明 |
| --- | --- |
| `output/report.html` | 浏览器直接打开，含 ECharts 交互图表 |
| `output/report.md` | Markdown 格式，适合放入 Wiki / 文档系统 |
| `output/report.json` | 结构化原始数据，适合二次处理 |
| `output/report.pdf` | 打印友好版，需安装 Playwright |

### 重渲染已有 JSON

不重新调用 MCP，直接从已有 JSON 重渲染：

```bash
python scripts/render_report.py \
  --input output/report.json \
  --output output/report.html
```

## 效果预览

> 以下文件来自当前真实验收通过案例；`examples/` 只收录完全通过的公开示例。

| 文件 | 说明 | 链接 |
| --- | --- | --- |
| HTML 报告 | 浏览器直接打开，含离线图表 | [查看](examples/live-replaced-20261027/reports/01-contractor-bid-profile/report.html) |
| Markdown 报告 | 纯文本格式，适合 Git / 文档系统 | [查看](examples/live-replaced-20261027/reports/01-contractor-bid-profile/report.md) |
| JSON 原始数据 | 结构化数据，适合二次处理 | [查看](examples/live-replaced-20261027/reports/01-contractor-bid-profile/report.json) |
| 全部已验收案例 | 本 skill 当前全部完全通过示例 | [查看](examples/README.md) |

完整的 8 场景测试、未完全通过案例和历史运行保存在 [test-records](test-records/README.md)，不作为公开示例。

## 命令行用法

### 配置校验

```bash
python scripts/validate_config.py --allow-placeholders
```

### 模拟运行（不调真实 API）

```bash
python scripts/compose_report.py \
  --enterprise "中国铁建股份有限公司" \
  --dry-run \
  --output output/report.json \
  --report-output output/report.html
```

### 真实查询

```bash
python scripts/compose_report.py \
  --enterprise "中国铁建股份有限公司" \
  --output output/report.json \
  --report-output output/report.html
```

### 关键词模糊补全

输入简称或关键词，自动模糊搜索匹配企业全称：

```bash
python scripts/compose_report.py \
  --enterprise "探迹" \
  --report-output output/report.html
```

## 故障排查

### 1. MCP 客户端依赖缺失

```bash
pip install 'mcp>=1.12.0' httpx
```

### 2. 在线 MCP token 不可用

检查环境变量是否生效（不打印 token 本身）：

```bash
echo "$BIDDING_MCP_URL"
[ -n "$BIDDING_MCP_TOKEN" ] && echo "BIDDING_MCP_TOKEN 已设置" || echo "BIDDING_MCP_TOKEN 未设置"
python scripts/mcp_client.py ping
```

不要把 token 提交到 Git。

### 3. 本地 MCP 连不上

确认服务已启动，Skill 侧指向 `/mcp` 路径：

```bash
curl http://127.0.0.1:8000/mcp
python scripts/mcp_client.py ping
```

### 4. 报告内容为空

使用 `--dry-run` 验证报告骨架是否正常，再逐步排查 MCP 返回数据。

### 5. PDF 导出不可用

PDF 导出需要 Playwright + Chromium：

```bash
pip install playwright
playwright install chromium
```

## 相关文档

- [SKILL.md](SKILL.md) — Skill 契约（触发描述、意图路由、Golden Path）
- [references/report-output.md](references/report-output.md) — 报告结构规范与数据格式约束
- [references/mcp-tools-reference.md](references/mcp-tools-reference.md) — MCP 工具清单
