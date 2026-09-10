# 工具怎么运作，EAR 审核怎么做

[English](HOW_IT_WORKS.md) | [中文](HOW_IT_WORKS.zh.md)

本文分两大部分：

- **第一部分**：程序内部是怎么搭的、你的数据会经过哪些环节。
- **第二部分**：现实中 EAR 审核是怎么做的，以及这个工具替你做了哪一部分。

> 这是工程技术文档与流程说明，**不是法律意见**。文中没有任何内容在判断某笔交易是否已获 EAR 授权。

---

# 第一部分 · 工具是怎么运作的

## 1.1 设计原则

| 原则 | 具体含义 |
| --- | --- |
| **不给法律结论** | 程序能给出的最强表述是"需要人工复核"，永远不会说某笔交易合法、无需许可证或违反 EAR。 |
| **先事实、后判断** | 每一步只记录你输入的事实；规则只读取事实，绝不修改事实。 |
| **规则放在 JSON 里** | 分值、阈值、红灯、队列流转都是数据而不是代码，合规团队不改 Python 也能调整。 |
| **本地优先** | 事实、报告、审核历史和 API Key 都留在本机；只有你点按钮时才会联网。 |
| **可解释** | 每一个得分点都归属于一条具名规则并附带说明，复核人可以逐项审计。 |
| **筛查不下定论** | 名单命中只会输出 `MANUAL_VERIFICATION_REQUIRED`，永远不会说"受限方"。 |

## 1.2 整体架构

```
Streamlit 界面                      服务层                             数据
────────────                       ──────                             ────
app/main.py  （审核工作台） ─┐
                             ├──►  jurisdiction_service ─┐
app/ai_main.py（AI 前端）  ─┘      deminimis_service    │
                                   fdp_service          │
                                   screening_service    ├──► rule_evaluator ──► app/rules/*.json
                                   enduse_service       │                     （白名单表达式引擎）
                                   redflag_service      │
                                   risk_service         │
                                   report_service       ┘
                                        │
                                        ├──► ear_reviews.db      （本地审核历史）
                                        ├──► HTML / PDF 报告
                                        └──► app/data/*.csv      （筛查名单）
```

服务层是纯 Python 函数，**不引入 Streamlit**，所以测试和基准测试可以在没有浏览器的情况下跑完整条审核流水线。

## 1.3 审核流水线（11 步）

| 步骤 | 服务 | 输入 | 输出 |
| --- | --- | --- | --- |
| 1 交易信息 | `models/transaction.py` | 当事方、金额、日期、目的地 | 规范化的交易事实 |
| 2 产品信息 | `models/product.py` | 名称、描述、类别、已有 ECCN | 规范化的产品事实 |
| 3 EAR 管辖权 | `jurisdiction_service` | 7 个三态问题 | `POSSIBLE_EAR_JURISDICTION` / `JURISDICTION_REVIEW_REQUIRED` / `INSUFFICIENT_INFORMATION`，附理由与缺失信息 |
| 4 De Minimis | `deminimis_service` | 组件行（原产地、受控状态、金额、是否并入物项）+ 总值 | `COMPUTED` / `NO_CONTROLLED_US_CONTENT` / `MISSING_VALUE` / `MISSING_TOTAL` / `MISSING_INPUT`，附比例、被排除项与警告 |
| 5 FDP 审查 | `fdp_service` | 使用的美国软件/技术/设备、生产链信息 | `POTENTIAL_FDP_ISSUE` / `NO_FDP_FACTS_IDENTIFIED` / `INSUFFICIENT_INFORMATION`，附依赖地图 |
| 6 当事方筛查 | `screening_service` | 当事方名称与角色、本地 CSV 名单 | 逐方 `MANUAL_VERIFICATION_REQUIRED` / `POSSIBLE_MATCH` / `NO_APPARENT_MATCH`，附相似度分数 |
| 7 最终用途 | `enduse_service` | 声明的用途、地点、行业、用途类别 | 最终用途标志（军事迹象、信息不足、业务不一致、地点不清） |
| 8 红灯引擎 | `redflag_service` | 展平后的事实上下文 | 触发的红灯，附分值与建议动作 |
| 9 风险引擎 | `risk_service` | 事实 + 红灯 | 各分类得分（分类各自封顶）、总分 0-100、风险等级 |
| 10 审查队列 | `risk_service` | 事实 + 分数 + 红灯 | 流转决定 |
| 11 报告 | `report_service` | 完整结果集 | HTML 与 PDF，并存入本地 SQLite 历史 |

## 1.4 事实命名空间（规则读的是什么）

在打分之前，`risk_service.assemble_review_context()` 会把所有步骤**展平成一本"事实字典"**。规则永远不去访问对象，只读具名值——这样表达式引擎才安全、规则才可读。

程序会自动计算一些派生事实，例如：

| 派生事实 | 计算方式 |
| --- | --- |
| `has_eccn` | 已填 ECCN 且不是 `unknown`/`n/a`/`none` |
| `existing_ear_status` | 归一化为 `CONTROLLED`、`EAR99`、`NOT_US_ORIGIN`、`NOT_DETERMINED` 或 `UNKNOWN` |
| `product_military_terms` | 产品名称/描述/类别中出现强军事词汇 |
| `encryption_without_classification` | 描述提到加密/密码学、未填 ECCN，且不是否定表述 |
| `destination_embargoed` | 最终目的地属于配置的 `US_EMBARGO` 组 |
| `buyer_country_embargoed` | 买方所在国属于同一组（用于捕捉转运风险） |
| `destination_special_attention` | 目的地（缺失时用买方国）属于 `SPECIAL_ATTENTION` 组 |
| `has_us_content` | 第 3 步回答外国商品含美国原产成分 |
| `de_minimis_computed` | 已算出比例（即使是 0%） |
| `fdp_potential` | 第 5 步返回 `POTENTIAL_FDP_ISSUE` |
| `screening_has_manual_verification` | 任一方相似度 ≥ 0.96 |
| `end_use_insufficient` 等 | 第 7 步触发了对应标志 |
| `red_flag_requires_legal` | 至少一条触发的红灯带 `LEGAL_REVIEW_REQUIRED` 动作 |

## 1.5 规则引擎

规则就是 JSON，例如：

```json
{
  "rule_id": "RF003",
  "name": "Destination Under Comprehensive U.S. Embargo",
  "condition": "destination_embargoed == true",
  "risk_points": 25,
  "action": "LEGAL_REVIEW_REQUIRED",
  "explanation": "The ultimate destination is a country subject to a comprehensive U.S. embargo program."
}
```

条件由**白名单表达式引擎**（`app/rule_evaluator.py`）执行：支持比较、`and`/`or`/`not`、`in`、字面量，以及一组固定的辅助函数（`lower`、`contains`、`isin`、`coalesce`、`strip` 等）。属性访问、下标、任意函数调用一律拒绝；引用了不存在字段的规则会被记录为"规则错误"，而不会执行任何代码。

## 1.6 打分、等级与流转

1. **先跑红灯**：每条红灯带分值与一个 `action`（建议动作）。
2. **风险分类各自打分且各自封顶**，各分类上限合计必须为 100（见 `app/rules/risk_rules.json`）：

   | 分类 | 上限 |
   | --- | --- |
   | EAR 管辖 | 20 |
   | 产品 | 20 |
   | 目的地 | 15 |
   | 最终用户 | 20 |
   | 最终用途 | 10 |
   | 红灯 | 15 |

3. **风险等级**：LOW 0-20、MODERATE 21-40、ELEVATED 41-60、HIGH 61-80、CRITICAL 81-100。
4. **流转**按 `app/rules/review_queue_rules.json` 顺序判断，**第一条命中即生效**：

   | 顺序 | 触发条件 | 决定 |
   | --- | --- | --- |
   | RQ-01 | HIGH / CRITICAL | 建议外部律师 |
   | RQ-02 | 有当事方需人工核验 | 建议外部律师 |
   | RQ-03 | 最终目的地为禁运国 | 建议外部律师 |
   | RQ-04 | ELEVATED | 需法律审查 |
   | RQ-05 | 管辖需审查或信息不足 | 需法律审查 |
   | RQ-06 | 存在潜在 FDP 问题 | 需法律审查 |
   | RQ-07 | 触发的红灯要求法律审查 | 需法律审查 |
   | RQ-08 | MODERATE / 有红灯 / 可能名称匹配 / 最终用途信息不足 | 需合规审查 |
   | RQ-09 | 默认 | 自动审核完成 |

## 1.7 当事方筛查

- 筛查第 1、6 步记录的所有当事方：出口商、买方、收货方、最终用户、母公司、子公司、董事、受益所有人。
- 名单是 CSV，列名必须是 `name, aliases, country, reference, source, notes`；多个别名用 `;` 分隔；以 `#` 开头的行会被忽略。
- 相似度同时考虑字符级别与词元级别，并忽略 *Ltd*、*LLC*、*GmbH* 这类公司后缀。
- 区间：**≥ 0.96** 需人工核验；**0.65-0.96** 可能匹配；**< 0.65** 未发现明显匹配。
- 命中是**线索而不是结论**：需核实法律实体、拼写、国家、地址与股权关系。

## 1.8 官方名单同步

**List & Data Center** 会下载美国国际贸易署发布的官方 **Consolidated Screening List** CSV，与本地快照对比，展示新增、移除与变更。**在你确认之前不会覆盖任何文件**；应用后写入 `app/data/ear_synced_lists.csv`，每次同步记录在 `app/data/ear_sync_updates.csv`。整个过程不需要 API Key。

## 1.9 AI 助手

AI 前端是**助手**，不是决策者：

- 支持你配置的任意供应商（OpenAI、Anthropic、DeepSeek、GLM、Qwen、Moonshot、Ollama 或自定义 OpenAI 兼容网关）；
- 文件先在**本地**抽取文本，供应商若提供 Files API 也可同时上传原文件；
- 每个审核问题都是独立接口，**一次只问一个事实问题**，答案可导出为 JSON 草稿；
- 系统提示词与核心工具遵循同一套护栏。

Key 与各供应商配置保存在 `app/data/ai_config.json`，该文件已被 git 忽略。

## 1.10 报告、存储与质量控制

- 第 11 步生成 HTML 报告（11 个章节，含免责声明）与可下载 PDF，并把审核存入本地 SQLite（`ear_reviews.db`）。
- `pytest` 覆盖所有服务、数据模型、持久化与界面（无头冒烟测试）。
- `benchmark/` 会把 99 笔手工编写的交易送进真实流水线，与"由规则推导出的期望值"比对，并做护栏断言；CI 每次 push 都会跑。

---

# 第二部分 · EAR 审核怎么做，工具对应到哪一步

EAR（15 CFR 第 730-774 部分）由美国商务部工业与安全局（BIS）执行。一次正常的审核是在回答一条问题链。下表说明这个工具帮你回答哪些问题、以及它在哪里**故意停下**。

## 2.1 这个物项到底受不受 EAR 管辖？（管辖权）

物项可能因为以下原因落入 EAR：位于美国境内；美国原产且现在境外；外国制造但含超过 de minimis 比例的受控美国成分；用美国技术或软件生产；或者有美国人参与相关活动。

**工具**：第 3 步询问"是否美国原产、是否含美国成分、金额是否已知、生产中是否使用美国软件/技术、生产链是否已知"，输出三种状态之一，**永不说"属于/不属于 EAR"**。工具不评估 ITAR 或其他机构制度；若可能涉及国防物项，审核必须转向。

## 2.2 这是什么物项、怎么分类？（ECCN / EAR99）

在商业管制清单（CCL）上的物项有 ECCN（例如 `3A001`、`5A002`，软件如 `5D002`），编码里包含类别、产品组（A 系统、B 测试设备、C 材料、D 软件、E 技术）与管制原因。不在 CCL 上的属于 EAR99。

**工具**：第 2 步记录描述、类别与已有 ECCN/状态。如果描述声称具备加密能力却没有填 ECCN，红灯 `RF011` 与风险规则 `PRD-05` 会要求先做分类。**工具从不替你分配 ECCN。**

## 2.3 是否需要许可证？

许可证要求来自"分类 + 目的地（Commerce Country Chart）+ 最终用途 + 最终用户"的组合，以及第 736 部分的十项一般禁令；实体清单、军事最终用户清单等还会叠加额外要求。

**工具**：**不判断是否需要许可证**。它把驱动判断的事实（分类状态、目的地分组、最终用途、最终用户、名单筛查）呈现出来，并把文件路由到正确的队列。

## 2.4 有没有可用的许可证例外？

第 740 部分包含多种例外（TMP、RPL、GOV、ENC 等），每种都有条件，适用与否是法律判断。

**工具**：不建模，报告中保留为待复核问题。

## 2.5 最终用途与最终用户管制（第 744 部分）

除国别表之外，EAR 还针对特定用途（扩散、744.21 军事最终用途、特定军事情报用途）和特定用户（实体清单、军事最终用户清单、未经核实清单）施加限制。

**工具**：第 7 步记录声明用途、安装地点、行业，并对军事迹象、信息不足、业务矛盾、地点含糊给出标志；第 6 步筛查当事方。**两者都不判定管制是否适用。**

## 2.6 受限方筛查

综合筛查名单包含 BIS 的**实体清单**、**被拒人员名单**、**未经核实清单**、**军事最终用户清单**，以及国务院与财政部的名单。良好做法是筛查交易中的**每一方**（含中间商），命中后必须对照官方来源核实身份，**绝不能只凭名称**。

**工具**：第 6 步用本地 CSV 名单筛查所有已记录当事方，也可一键同步官方名单；输出相似度分数，最强结论是 `MANUAL_VERIFICATION_REQUIRED`。

## 2.7 禁运目的地与制裁

全面禁运项目（如古巴、伊朗、朝鲜、叙利亚）主要由 OFAC 管理，但同样影响 EAR 分析；BIS 的许可要求与审查政策因项目而异。

**工具**：`app/data/country_data.json` 中的目的地分组驱动红灯 `RF003`（最终目的地）与风险规则 `DST-01`；针对**买方所在国**另有 `RF012` 与 `DST-04`。两组名单都可配置，且都不是法律认定。

## 2.8 De Minimis（15 CFR 734.4）

对于含受控美国成分的外国制造物项，de minimis 计算把"受控美国成分的价值"与"外国制造物项总价值"相比。有两点关键：

1. 只有**并入物项**的内容计入。用于**生产**该物项的美国软件或技术属于外国直接产品（FDP）分析，不是 de minimis。
2. 阈值不是唯一数字。常见的是 **25%**，对某些 ECCN 与目的地是 **10%**——以条文与 ECCN 为准。

**工具**：第 4 步把"原产地为美国**且**受控"的组件求和，除以总值并给出比例；每个组件可标注"已并入物项"或"仅用于生产"，后者会被排除并交给 FDP 步骤。工具对比例**分档打分**（`JUR-05` 5-10%、`JUR-06` 10-25%、`JUR-07` ≥25%），对不一致输入给出警告，并且**从不告诉你适用哪个阈值**——那是法律判断。

## 2.9 外国直接产品规则（15 CFR 734.9）

某些外国制造物项因为使用了美国技术或软件生产、或产自本身是美国技术直接产品的工厂，而同样受 EAR 管辖；不同项目（国家安全、9x515/600 系列、俄罗斯/白俄罗斯、先进计算）规则不同。

**工具**：第 5 步询问使用了哪些美国软件、技术与设备、生产链是什么样，输出 `POTENTIAL_FDP_ISSUE`、`NO_FDP_FACTS_IDENTIFIED` 或 `INSUFFICIENT_INFORMATION`，并给出依赖地图。**不判断适用哪条 FDP 规则。**

## 2.10 红灯与尽职调查

BIS 发布的红灯指引包括：异常运输路线、用途含糊、与交易无关的第三方付款、不愿提供文件等。红灯是**待解决疑点，不是结论**。

**工具**：第 8 步用 `app/rules/red_flag_rules.json` 中的可配置红灯评估已记录事实。每条命中都带分值与**建议动作**（如 `OBTAIN_DE_MINIMIS_FACTS`、`COMPLETE_CLASSIFICATION`、`MANUAL_VERIFICATION_REQUIRED`、`LEGAL_REVIEW_REQUIRED`），队列规则会读取这些动作。

## 2.11 记录与上报

EAR 审核的质量取决于记录：问了什么、答了什么、查了哪些来源、由谁决定。记录必须留存并在被要求时提供。

**工具**：每次审核都会生成包含事实、触发的规则与解释、缺失信息、队列决定与免责声明的报告，并保存在本地以便日后检索。当队列给出 `LEGAL_REVIEW_REQUIRED` 或 `EXTERNAL_COUNSEL_REVIEW_RECOMMENDED` 时，就是该交给人处理了——工具的任务到此结束。

---

# 第三部分 · 怎么读输出

| 输出 | 取值 | 含义 | 你要做什么 |
| --- | --- | --- | --- |
| 管辖权 | `POSSIBLE_EAR_JURISDICTION` | 记录了美国联系，无法排除管辖 | 继续，做分类 |
| | `JURISDICTION_REVIEW_REQUIRED` | 事实指向正式的管辖问题 | 交专家确认 |
| | `INSUFFICIENT_INFORMATION` | 关键问题未回答 | 补齐缺失事实 |
| De Minimis | `COMPUTED` | 已算出比例 | 就适用阈值寻求法律复核 |
| | `NO_CONTROLLED_US_CONTENT` | 分子为 0 | 确认组件数据 |
| | `MISSING_VALUE` / `MISSING_TOTAL` / `MISSING_INPUT` | 输入缺失（触发 `RF010`） | 完成计算 |
| FDP | `POTENTIAL_FDP_ISSUE` | 记录了美国输入与生产链 | 就适用 FDP 规则寻求法律复核 |
| | `NO_FDP_FACTS_IDENTIFIED` | 未记录美国生产输入 | 确认生产链 |
| | `INSUFFICIENT_INFORMATION` | 有美国输入但缺生产事实 | 补充设施、设备、工艺 |
| 筛查 | `MANUAL_VERIFICATION_REQUIRED`（≥0.96） | 名称高度相似 | 对照官方名单核实身份 |
| | `POSSIBLE_MATCH`（0.65-0.96） | 相似度较弱 | 核对拼写、实体与股权 |
| | `NO_APPARENT_MATCH`（<0.65） | 低于阈值 | 留存记录 |
| 风险 | LOW / MODERATE / ELEVATED / HIGH / CRITICAL | 由封顶后的分类得分得到的初步等级 | 重点看逐项得分，不要只看数字 |
| 队列 | `AUTO_REVIEW_COMPLETE` | 未触发任何阈值 | 留存记录 |
| | `COMPLIANCE_REVIEW_REQUIRED` | 有红灯或缺口待处理 | 合规审查 |
| | `LEGAL_REVIEW_REQUIRED` | 识别出法律问题 | 出口管制律师或专员 |
| | `EXTERNAL_COUNSEL_REVIEW_RECOMMENDED` | 高风险、名单命中、禁运或带法律动作的红灯 | 外部律师 |

---

# 第四部分 · 工具**不**做什么

1. 不判断**管辖权、分类、许可证要求、许可证例外、de minimis 阈值、FDP 适用性**。
2. 不替代**官方名单**。筛查分数只是线索，以 Federal Register 与各机构官方发布为准。
3. 除提供可配置的目的地与制裁名单数据外，不覆盖 **ITAR、OFAC 许可或其他机构制度**。
4. 不区分**电子交付**与实物发运。
5. 军事与加密识别是**基于关键词**的，且刻意偏向"多报"——目的是让人复核，而不是下结论。
6. **不能替代律师**。所有输出都只是初步工作底稿。

---

# 第五部分 · 术语表

| 术语 | 含义 |
| --- | --- |
| **BIS** | 美国商务部工业与安全局 |
| **CCL / ECCN** | 商业管制清单 / 出口管制分类编号 |
| **CSL** | 综合筛查名单（美国各筛查名单的合并） |
| **De minimis** | 外国制造物项中受控美国成分的比例测试 |
| **DPL** | 被拒人员名单 |
| **EAR99** | 受 EAR 管辖但不在 CCL 上的物项 |
| **实体清单** | 需额外许可要求的当事方（第 744 部分） |
| **FDP** | 外国直接产品规则 |
| **MEU** | 军事最终用户（清单与最终用途管制） |
| **OFAC** | 美国财政部海外资产控制办公室 |
| **UVL** | 未经核实清单 |

## 官方来源

- BIS：https://www.bis.gov/
- eCFR（15 CFR 730-774）：https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C
- 综合筛查名单：https://www.trade.gov/consolidated-screening-list
- Federal Register（BIS 公告）：https://www.federalregister.gov/agencies/industry-and-security-bureau
