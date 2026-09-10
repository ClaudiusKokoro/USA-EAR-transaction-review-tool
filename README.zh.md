# EAR 交易审核工具

[English](README.md) | [中文](README.zh.md)

![Tests](https://github.com/ClaudiusKokoro/USA-EAR-transaction-review-tool/actions/workflows/tests.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)

EAR 交易审核工具是一个**本地优先（local-first）的 Web 应用**，帮助律师与出口合规人员对可能受美国《出口管理条例》（EAR）管辖的交易做**初步**审核。

> **法律设计原则：** 本工具**永远不会**给出确定性法律结论，例如"这笔交易合法""不需要许可证""违反 EAR"。它只负责收集交易事实、识别缺失信息、套用可配置规则、计算初步风险分数、标出需要人工法律复核的问题，并生成结构化审核报告。

## 界面截图

| 审核工作台 | 当事方筛查 |
| --- | --- |
| ![步骤 1 交易信息录入](docs/images/01-workbench.png) | ![步骤 6 当事方筛查](docs/images/02-screening.png) |

| 名录中心 | AI 助手 |
| --- | --- |
| ![同步官方名单](docs/images/03-list-sync.png) | ![多供应商 AI 助手](docs/images/04-ai-assistant.png) |

---

## 环境要求

- Python 3.10+
- Streamlit
- SQLite（Python 内置）
- Pydantic v2
- ReportLab（生成 PDF）
- Requests（调用大模型接口）
- pandas / openpyxl / xlrd（表格类文件解析）
- pytest（开发与测试）

全部 Python 依赖见 [requirements.txt](requirements.txt)。本项目**不依赖任何付费 API**；只有当你点击"同步名录"按钮时才会向美国政府官网发起一次 HTTPS 请求。

---

## 快速开始

### 0. 最省事的方式：双击启动脚本

**Windows** —— 在项目文件夹里双击：

- `install-dependencies.bat` —— 首次运行：创建 `.venv` 并安装依赖
- `start-windows.bat` —— 打开审核工作台 http://localhost:8501
- `start-ai-frontend.bat` —— 打开 AI 助手 http://localhost:8502
- `start-all.bat` —— 同时启动两个工具

原先中文名的启动脚本（`启动-*.bat`）仍然保留，内部会自动转发到上面的英文脚本。

**macOS / Linux** —— 先执行一次安装，再启动：

```bash
chmod +x *.sh *.command     # clone 之后执行一次
./install-dependencies.sh
./start.sh                  # 审核工作台，http://localhost:8501
./start-ai-frontend.sh      # AI 助手，    http://localhost:8502
```

macOS 上也可以直接在访达里双击 `start.command`（或 `start-ai-frontend.command`）。如果系统拒绝打开，先在终端执行一次 `chmod +x start.command`，或者用 `bash start.command` 启动。

启动脚本会开一个本地 Web 服务并自动打开浏览器。**使用期间请不要关闭那个命令行窗口**，关掉即停止服务。

> **本版本要点：** 界面为纯英文；AI 前端支持 GPT / Claude / DeepSeek / GLM / Qwen / Moonshot / Ollama / 自定义 OpenAI 兼容网关；侧边栏的 **List & Data Center** 里有 **"Sync latest EAR content"** 按钮（见下文"同步官方 EAR 名录"）。

### 1. 手动创建并激活虚拟环境

**Windows（PowerShell）：**

```powershell
cd ear_transaction_review_tool
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux：**

```bash
cd ear_transaction_review_tool
python3 -m venv .venv
source .venv/bin/activate
```

### 2. 安装依赖

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. 启动审核工作台

```bash
streamlit run app/main.py
```

打开终端里显示的地址（通常是 http://localhost:8501）。

### 3b. 启动多供应商 AI 助手

```bash
streamlit run app/ai_main.py
```

英文界面的 AI 前端提供三块功能：

1. **供应商与接口配置** —— 选择供应商、粘贴 API Key、填写任意模型名，也可以覆盖 Base URL、对话路径、上传地址。Key 与每个供应商的模型选择都保存在本地 `app/data/ai_config.json`（已被 git 忽略），不会进入仓库。
2. **文件分析** —— 上传 TXT、Markdown、CSV、JSON、PDF、DOCX、XLSX、HTML、XML、LOG 等文件。文本始终在本地先抽取；如果该供应商提供 OpenAI 风格的 Files 接口，原始文件也会一并上传。两条路径都会进入对话请求，由模型总结与 EAR 相关的事实、缺失信息和需要追问的问题。
3. **独立的问题接口** —— 审核中应当逐条询问的问题，全部定义在 `app/rules/ear_question_interfaces.json`。每个接口有稳定的 `interface_id`、映射的 EAR 字段、英文提示词（同时保留可选中文字段，便于本地化部署），并可以单独触发"提问 → 作答 → 保存到草稿 → 导出 JSON"。

#### 支持的供应商

| 供应商 | 接口风格 | 默认地址 | 说明 |
| --- | --- | --- | --- |
| OpenAI (GPT) | OpenAI 兼容 | `https://api.openai.com/v1` | 支持 Files API 上传 |
| Anthropic (Claude) | Anthropic Messages | `https://api.anthropic.com/v1` | 使用 `x-api-key` + `anthropic-version` |
| DeepSeek | OpenAI 兼容 | `https://api.deepseek.com/v1` | 文件走本地文本抽取 |
| Zhipu GLM | OpenAI 兼容 | `https://open.bigmodel.cn/api/paas/v4` | 文件走本地文本抽取 |
| Qwen (DashScope) | OpenAI 兼容 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 文件走本地文本抽取 |
| Moonshot (Kimi) | OpenAI 兼容 | `https://api.moonshot.cn/v1` | 文件走本地文本抽取 |
| Ollama (本地) | OpenAI 兼容 | `http://localhost:11434/v1` | 无需 API Key |
| 自定义 | OpenAI 兼容 | 自行填写 | 任意网关或企业代理 |

下拉里的供应商与模型列表只是**建议值**，模型字段接受任意标识符，Base URL 和对话路径也可以按网关/代理情况覆盖。要长期新增供应商，直接扩展 `app/ai_frontend/providers.py` 即可。

调用模型时，系统提示词与核心工具遵循同一套限制：不判断交易是否合法、是否需要许可证、是否违反 EAR。

> 隐私提示：调用 AI 时，会把 API Key、抽取出的文件文本和你填写的审核摘要发送给你所配置的供应商。请只上传你有权共享的资料。

### 4. 运行测试

```bash
pytest
```

### 5. 生成示例审核报告

```bash
python examples/sample_transaction.py
```

输出文件位于 `reports/sample_report.html` 与 `reports/sample_report.pdf`。示例覆盖：中国出口商（CN）、新加坡买方（SG）、外国生产的电子产品、生产环节中可能使用美国原产软件、最终用户信息不完整等情况。

---

## 同步官方 EAR 名录

侧边栏的 **List & Data Center** 视图提供 **"Sync latest EAR content"** 按钮，点击后会下载美国国际贸易署（ITA）每日发布的官方：

- **Consolidated Screening List（CSL）** CSV 文件
- 官方下载地址：`https://data.trade.gov/downloadable_consolidated_screening_list/v1/consolidated.csv`
- 人工查看页面：https://www.trade.gov/consolidated-screening-list

CSL 每天刷新，默认包含美国商务部 BIS 的**实体清单（EL）**、**被拒人员名单（DPL）**、**未核实名单（UVL）**和**军事最终用户名单（MEU）**；也可以切换为"全部 CSL 名单"，把国务院、财政部的名单（含 OFAC SDN）一并纳入。

按钮**不会擅自改动任何文件**，它的流程是：

1. 下载最新官方文件；
2. 与本地快照对比，展示**新增 / 移除 / 变更**的数量与预览；
3. 允许你下载本次差异 CSV 或完整新名单 CSV；
4. 只有在你勾选确认框并点击应用后，才会把结果写入本地快照 `app/data/ear_synced_lists.csv`。

应用之后，第 6 步的当事方筛查会在内置示例名单之外，自动使用这份同步名单。每次同步的差异会追加记录在 `app/data/ear_sync_updates.csv`，元信息写在 `app/data/ear_sync_meta.json`。

> **重要：** 名单来自美国政府官网，仅供初步筛查参考。名称命中并不能证明某方就是受限方；请务必对照 Federal Register 与各机构官网的正式文本。也正因为如此，工具即便在完全匹配时，最高结论仍是 `MANUAL VERIFICATION REQUIRED`。

全程不需要 API Key。如果所在网络需要代理或镜像，可以设置环境变量 `EAR_CSL_URL`，或修改 `app/rules/ear_sync_sources.json` 里的 `url`。

---

## 工具是怎么运作的

两份长文文档解释内部实现与业务模型：

- **[工具怎么运作，EAR 审核怎么做](docs/HOW_IT_WORKS.zh.md)**：
  第一部分讲架构、11 步流水线、展平后的事实命名空间、安全规则引擎、打分与等级、
  队列流转、当事方筛查、名单同步、AI 助手、报告与基准测试；
  第二部分完整走一遍真实的 EAR 审核——管辖权、分类、许可证要求与例外、最终用途与
  最终用户管制、受限方筛查、禁运目的地、De Minimis、外国直接产品规则、红灯与上报——
  并明确说明工具做了哪些、只为哪些判断提供事实、以及**从不**做什么。
- **[English edition](docs/HOW_IT_WORKS.md)**：英文版本。

---

## 11 步审核流程

| 步骤 | 模块 | 作用 |
| --- | --- | --- |
| 1 | `models/transaction.py`、`main.py` | 交易信息录入（当事方、金额、日期、目的地） |
| 2 | `models/product.py`、`main.py` | 产品信息与已有分类 |
| 3 | `services/jurisdiction_service.py` | 保守的管辖判断状态（可能属 EAR / 需审查 / 信息不足） |
| 4 | `services/deminimis_service.py` | 受控美国成分价值占外国生产商品总价值的比例 |
| 5 | `services/fdp_service.py` | 生产依赖地图与 FDP 标识 |
| 6 | `services/screening_service.py` | 本地 CSV 当事方筛查（精确匹配、模糊匹配、相似度评分） |
|   | `services/ear_list_sync_service.py` | "同步最新 EAR 内容"：下载官方 CSL 并对比写入本地 CSV |
| 7 | `services/enduse_service.py` | 最终用途标识（信息不足、业务不一致、军事迹象、地点不明） |
| 8 | `services/redflag_service.py` | JSON 配置的红灯规则 |
| 9 | `services/risk_service.py` | JSON 配置的分类评分（0-100），每个得分点都有说明 |
| 10 | `services/risk_service.py` + `rules/review_queue_rules.json` | 法律审查队列流转 |
| 11 | `services/report_service.py` | 生成 HTML 报告与可下载 PDF，含全部 11 个章节 |

---

## 项目结构

```
ear_transaction_review_tool/
│
├── app/
│   ├── main.py                  # 审核工作台界面
│   ├── ai_main.py               # 多供应商 AI 助手界面
│   ├── db.py                    # 本地 SQLite 审核历史
│   ├── paths.py                 # 与启动目录无关的路径处理
│   ├── rule_evaluator.py        # JSON 规则条件的安全求值器
│   │
│   ├── ai_frontend/
│   │   ├── providers.py         # 供应商注册表（GPT/Claude/DeepSeek/GLM/Qwen/...）
│   │   ├── config_store.py      # 本地多供应商配置（含旧配置迁移）
│   │   ├── llm_client.py        # OpenAI 兼容 + Anthropic 对话/文件客户端
│   │   ├── deepseek_client.py   # 兼容旧代码的别名模块
│   │   ├── file_utils.py        # 上传文件的本地文本抽取
│   │   └── question_registry.py # EAR 问题接口注册表
│   │
│   ├── models/                  # Pydantic 数据模型
│   ├── services/                # 管辖、De Minimis、FDP、筛查、名录同步、
│   │                            # 最终用途、红灯、风险、队列、报告
│   ├── rules/                   # JSON 规则与 EAR 问题接口定义
│   ├── data/                    # 示例名单与本地运行数据（已被忽略）
│   └── templates/               # 报告模板
│
├── examples/                    # 示例交易
├── tests/                       # 单元测试、集成测试、界面冒烟测试
│
├── start-windows.bat            # Windows 启动脚本
├── start-ai-frontend.bat
├── start-all.bat
├── install-dependencies.bat
├── start.sh                     # macOS / Linux 启动脚本
├── start-ai-frontend.sh
├── start.command                # macOS 双击启动
├── start-ai-frontend.command
├── install-dependencies.sh
├── requirements.txt
├── pytest.ini
└── README.md
```

---

## 配置（改 JSON 即可，无需改 Python）

### 红灯规则 —— `app/rules/red_flag_rules.json`

每条规则包含：

```json
{
  "rule_id": "RF001",
  "name": "Unknown Ultimate End User",
  "condition": "ultimate_end_user == null",
  "risk_points": 15,
  "action": "ENHANCED_DUE_DILIGENCE",
  "explanation": "The ultimate end user was not identified. Verify the end user before proceeding."
}
```

### 风险规则 —— `app/rules/risk_rules.json`

定义每个分类的上限、0-100 的分数区间，以及各分类下的规则。例如：

```json
{
  "rule_id": "EUS-03",
  "name": "Ultimate end user not identified",
  "condition": "ultimate_end_user == null or strip(str(ultimate_end_user)) == ''",
  "points": 12,
  "explanation": "The ultimate end user has not been identified, so end-user risk cannot be assessed."
}
```

引擎会把每个分类限制在配置的上限内，并且**每一个得分点都来自某条规则**，因此报告能够解释总分来源。

### 队列流转规则 —— `app/rules/review_queue_rules.json`

一个有序规则列表，第一条命中的规则决定队列：

- `AUTO_REVIEW_COMPLETE`
- `COMPLIANCE_REVIEW_REQUIRED`
- `LEGAL_REVIEW_REQUIRED`
- `EXTERNAL_COUNSEL_REVIEW_RECOMMENDED`

### 目的地数据 —— `app/data/country_data.json`

包含 `US_EMBARGO`（美国禁运）与 `SPECIAL_ATTENTION`（特别关注）目的地分组，以及各国备注。风险规则会读取 `destination_embargoed`、`destination_special_attention` 等派生布尔值。

### 当事方筛查名单 —— `app/data/restricted_parties.csv`

仓库自带的文件**只是示例数据**，并已明确标注。生产环境请替换为最新的官方名单（列名：`name, aliases, country, reference, source, notes`；以 `#` 开头的行会被忽略）。你也可以在第 6 步界面上传额外的 CSV。

比起手工维护 CSV，更推荐用 **List & Data Center** 的同步按钮直接下载官方 BIS 名单。同步后的文件使用完全相同的六列格式，因此也可以导出、上传到任何接受该格式的地方。

---

## 规则表达式语言

JSON 条件由 `app/rule_evaluator.py` 用白名单安全求值器执行，可用元素包括：

- 字段：所有规范化后的事实名（见 `risk_service.py` 中的 `assemble_review_context`），例如 `ultimate_end_user`、`destination_embargoed`、`de_minimis_ratio`、`risk_level`
- 比较：`==`、`!=`、`<`、`<=`、`>`、`>=`、`in`
- 布尔运算：`and`、`or`、`not`
- 字面量：数字、字符串、`true`、`false`、`null`
- 辅助函数：`str()`、`int()`、`float()`、`num()`、`len()`、`lower()`、`upper()`、`strip()`、`title()`、`contains(a, b)`、`startswith()`、`endswith()`、`isin(item, collection)`、`coalesce(*values)`

示例：

```text
ultimate_end_user == null
destination_embargoed == true and risk_level == 'HIGH'
contains(product_description, 'military') or contains(product_description, 'defense')
de_minimis_computed == true and de_minimis_ratio >= 0.10
```

未知字段、属性访问、下标访问和任意函数调用都会抛出配置错误，而不会执行任意 Python 代码。

---

## 数据持久化

审核历史保存在项目根目录的 SQLite 文件 `ear_reviews.db` 中（可用环境变量 `EAR_REVIEW_DB` 覆盖路径）。历史记录可在侧边栏中加载或删除。

---

## 工具如何在设计上守住法律边界

1. **事实收集与规则计算分离** —— 每一步只存储事实，规则不会修改用户输入。
2. **管辖结论受限** —— 只输出 `POSSIBLE EAR JURISDICTION`、`JURISDICTION REVIEW REQUIRED`、`INSUFFICIENT INFORMATION`。
3. **筛查永不输出"受限方"** —— 即使名称完全匹配，最高也只是 `MANUAL VERIFICATION REQUIRED`。
4. **De Minimis** 只报告比例，并提示适用阈值需要法律复核。
5. **风险分数明确是初步结果**，且每一分都有解释。
6. **每份报告都包含免责声明：**

> This tool provides a preliminary compliance risk assessment based on user-provided information and configurable rules. It does not constitute legal advice and does not determine whether an export, reexport, or transfer is authorized under the EAR.

---

## 测试

测试覆盖所有引擎：条件求值器、管辖、De Minimis、FDP、筛查、最终用途、红灯、风险评分、队列流转、数据模型、SQLite 持久化、完整示例交易，以及名录同步与 AI 前端（含界面冒烟测试）。

```bash
pytest
```

CI 会在每次 push / PR 时，于 Ubuntu、Windows、macOS 上分别用 Python 3.10 与 3.12 运行全部测试（见 `.github/workflows/tests.yml`）。

---

## 基准测试（Benchmark）

`benchmark/` 目录包含一份人工编写的测试集，把 **99 笔交易**真正送进审核流水线，
用来验证程序是否会按它自己的规则把该报警的交易标出来。

```bash
python benchmark/run_benchmark.py
python benchmark/run_benchmark.py --family screening --verbose
```

覆盖范围包括：管辖、**分档的 De Minimis 边界值**（低于 5%、4.9% / 5.0% / 10% /
25% / 超过 100%）、软件场景（商业软件、加密软件、含美国 SDK 的外国软件、仅用于生产的
美国软件、电子交付、关键词陷阱）、FDP、当事方筛查（完全匹配、别名、近似名、英式拼写）、
最终用途、禁运目的地、多维叠加的高危案例，以及 6 个"必须不报警"的对照案例。每个用例还会做
**护栏检查**：筛查状态必须落在三个枚举值内、任何当事方都不会被标为受限方、生成的文本里
不能出现法律结论性措辞。

整个跑分约 1 秒、不需要联网；有检查失败时退出码非 0，因此 CI 会在每次 push 时自动运行。
用例家族、跑分发现的 8 个标定问题（均已修复并有对应用例锁定）以及仍存在的限制，详见
[benchmark/README.md](benchmark/README.md)。

---

## 故障排查

**提示 `streamlit` 不是命令** —— 先激活虚拟环境，再执行 `pip install -r requirements.txt`。

**8501 端口被占用** —— 换端口，例如 `PORT=8503 ./start.sh`，或 `streamlit run app/main.py --server.port 8503`。

**PDF 里的中文显示不出来** —— `report_service.py` 已注册 ReportLab 的 CID 字体 `STSong-Light`；请确认 PDF 阅读器支持标准中文 CID 字体。

**macOS 拒绝打开 `start.command`** —— 在终端执行一次 `chmod +x start.command start-ai-frontend.command start.sh start-ai-frontend.sh install-dependencies.sh`，或改用 `bash start.command`。

**AI 接口返回 HTTP 401/403** —— Key 缺失、过期，或没有所选模型的权限。到 *1 - Provider & API* 重新保存，并点 *Test chat endpoint* 验证。

**提示 "model not found"** —— 下拉里的模型只是建议值，请按供应商文档填写准确的模型标识符。

**名录同步在企业网络里失败** —— 工具需要 HTTPS 访问 `data.trade.gov`。请配置系统代理，或把环境变量 `EAR_CSL_URL`、`app/rules/ear_sync_sources.json` 中的 `url` 指向已获批准的镜像。

---

## 克隆与贡献

```bash
git clone https://github.com/ClaudiusKokoro/USA-EAR-transaction-review-tool.git
cd USA-EAR-transaction-review-tool

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

pytest
streamlit run app/main.py
```

完整的开发指南见 [CONTRIBUTING.md](CONTRIBUTING.md)，漏洞上报见
[SECURITY.md](SECURITY.md)，版本变更见 [CHANGELOG.md](CHANGELOG.md)。

提交 PR 之前，请确认：

- `pytest` 全部通过；
- 不要把 `app/data/ai_config.json`、同步下来的名单 CSV、`*.db` 或任何 API Key 提交进仓库（`.gitignore` 已经覆盖这些路径）；
- 规则类改动尽量只改 `app/rules/*.json`，便于他人复用。

---

## 免责声明

本工具基于用户提供的信息与可配置规则，给出初步合规风险评估。**它不构成法律意见，也不判断某笔出口、再出口或转让是否已获 EAR 授权。** 名单匹配结果仅供参考——在依赖任何筛查结果之前，请务必对照 Federal Register 与各机构官方名单核实当事方。

---

## 许可证

本项目基于 [MIT License](LICENSE) 发布。
