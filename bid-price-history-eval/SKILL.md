---
name: bid-price-history-eval
description: 历史数据评估法报价测算（历史评估法）：先从招标文件提取价格评分方法，再用 MCP（知了标讯 zhiliaobiaoxun）与网络收集各投标单位的近期同类报价、历史同类报价、同省报价折扣率（并校验各历史标的价格分算法是否与本次同口径——低价基准/平均基准不可混用），按"历史中标锚+行业底线定基础区间 → 对手报价习惯验证 → 甲方需求/评分风险/专家建议收缩目标区间 → 情景得分模拟锁定最优折扣"四步圈定报价区间，生成折扣×折扣矩阵热力图、区间收敛图、得分模拟图，最终渲染手机版式 PDF 测算报告与微信分享长图（含目标报价金额、折扣率、推理链与计算过程）。Use when 用户提到"历史数据评估法""历史评估法""按历史数据估报价""圈定报价区间""折扣乘折扣图/表""估各家报价折扣率""给出目标折扣率和目标报价"，或提供参与投标单位名单+最高限价/招标文件并要求报价测算。Do NOT use for 开标后的现场算分明细复核，或需要蒙特卡洛随机基准价模拟的场景（那用 bid-price-calc 技能）。
---

# 历史数据评估法报价测算（bid-price-history-eval）

把"历史中标折扣 + 对手报价习惯 + 评分规则"变成 **区间圈定 → 情景模拟 → 手机版式报告** 的
可复算链路。计算引擎 `scripts/history_eval.py`，渲染引擎 `render_report.py`（PDF 主交付）
与 `render_infographic.py`（分享长图），报告版式与交付纪律对齐 bid-price-calc 技能。

`<SKILL>` 指本技能目录（`~/.agents/skills/bid-price-history-eval`）。

## 依赖检查（每次任务开始）

```bash
python -c "import matplotlib, numpy; print('ok')"            # 区间测算引擎
python -c "from playwright.sync_api import sync_playwright; print('ok')"   # 报告 PDF + 信息图
```
缺 matplotlib/numpy → `python -m pip install matplotlib numpy`；
缺 playwright → 按降级流程：交付 `report.md` + `matrix.csv` + 三张 matplotlib 图，并在回复中说明缺 PDF。

需要的外部输入（缺哪个先问用户）：
1. **招标文件**（PDF/Word）——提取价格评分方法原文与最高限价；
2. **本次参与投标单位名单**（含"上次中标单位"）；
3. **我方历史中标折扣**（上次同类项目折扣率）——定区间上限的锚。

## Instructions

### Step 1：提取评分方法原文（必须先做）
- PDF 用 pdf 技能/pypdf/fitz 提取文本，定位"评标办法/价格评审/报价评分"章节；
- 抄录**原文**：基准价公式、高于/低于基准价扣分系数、去极值规则（≤5家是否去极值）、
  异常价上下限（如 50%/200%）、价格权重、最高投标限价（分档单价限价需合计）；
- 识别结果必须给章节/页码/原句依据（写入 meta.json 的 `scoring_evidence`）。

### Step 2：收集历史折扣数据 + 评分方法一致性校验（MCP 优先）
按 `<SKILL>/references/mcp-recipes.md` 配方，对**每一家**参与单位建立证据链：
1. 上次同类项目（同客户）中标折扣 → 最高权重；2. 近 1-2 年同类项目折扣 → 次高；
3. 同省份/同行业折扣 → 交叉验证；4. 每条证据记录：项目名、报价、限价、折扣率、时间、来源。

**【重要】同一甲方不同标的价格分算法可能不同**（低价基准 / 平均基准(去极值) /
次低价 / 随机系数…），不同算法下投标人的报价行为不同——低价基准的标折扣会被打得更低，
不能直接外推到平均基准的本次项目：
- 对每个**关键证据项目**回查其招标文件评标办法（MCP `get_bid_detail` 抓正文搜
  "评标基准价/价格评分方法"，见 mcp-recipes E 节），标注 同口径 / 异口径 / 未核验；
- **同口径证据权重最高**；异口径证据只作边界参考、估计时需按算法差异修正；
  未核验证据显式标注，禁止当作同口径使用；
- 核验结论写入 meta.json 的 `consistency`（报告有专门卡片展示）。

**折扣率估算三原则**：近期优先于远期（有升/降趋势按时间加权）；同客户报价稳定可沿用、
跨省/客情弱地区下修；查不到数据按行业中性并标注"无数据"，**禁止编造折扣率**。
折扣率 = 报价 ÷ 同口径限价（含税/不含税、全费用/师资费口径必须一致，剥离食宿车班等差额）。
MCP 查不到 → WebSearch 兜底。

### Step 3：四步圈定折扣区间（核心方法）
严格按 `<SKILL>/references/methodology.md`，每步输出依据与结论：
1. **基础区间**：上限=我方上次同类中标折扣（历史锚）；下限=全国同类中标折扣底线（行业锚）；
2. **对手验证**：全部参与单位折扣估计是否落在基础区间 → 吻合通过，不吻合复查修正；
3. **收缩目标区间**：甲方诉求 + 评分不对称（高于基准扣分更重→偏低）+ 专家建议；
4. **得分模拟锁最优**：目标区间内 4~6 个候选 × 3 档市场情景全字段模拟。

### Step 4：构造 input JSON 并运行引擎
按 `<SKILL>/references/input-schema.md`（完整示例：`references/example-gansu.json`）：

```bash
python <SKILL>/scripts/history_eval.py --input <input.json> --out <输出目录>
```
产出：`result.json`（结构化结果，**所有报告数字的唯一来源**）、`heatmap_折扣乘折扣.png`、
`interval_折扣区间收敛.png`、`simulation_候选折扣得分.png`、`matrix.csv`、
`scenario_tables.csv`、`report.md`（文本报销底稿）。

引擎内置规则：
- 算分严格按招标原文（`above_k`/`below_k`/去极值/异常价）；
- **并列带选择**：与最高平均分差 ≤ `tie_band`（默认 0.3 分）视为统计并列，
  `prefer_low=true`（默认）取并列带内最低折扣（高报价扣分系数更大 + 甲方降本偏好）。
  甘肃案例 73%/74%/75% 分差 <0.12 → 锁定 73% = 411,830.17 元（与原案例一致）。

### Step 5：写 meta.json（报告叙事与证据）
放在 `result.json` 同目录。字段详见 `scripts/render_report.py` 模块 docstring，必填项：

```json
{
  "project": "项目名称", "date": "YYYY-MM-DD",
  "scoring_label": "基准价法（去极值算术平均；高于×1.0、低于×0.5 扣分）",
  "scoring_evidence": "章节+页码+原句（必填，可信度来源）",
  "scoring_formula": "招标原文评分公式全文（缺省用 result 的 method_text）",
  "base_reason": "第1步依据（我方上次中标折扣/行业底线出处）",
  "validate_reason": "第2步依据（各家折扣汇总）",
  "narrow_reason": "第3步依据（甲方诉求/评分不对称/专家建议）",
  "suggest_note": "报价建议理由 3~4 句",
  "consistency": {
    "current_method": "平均价基准（有效价去极值算术平均）",
    "projects": [{"project": "证据项目名", "method": "平均价基准", "match": true}],
    "note": "异口径/未核验证据的处理方式说明"
  },
  "secondary_discount": 0.75,
  "limits": ["限制1", "限制2"]
}
```
- `consistency` **强烈建议填**：`match` 取 true(同口径)/false(异口径)/null(未核验)；
- `secondary_discount` 不填则自动取并列带上限。

### Step 6：渲染报告（主交付：手机版式 PDF）
```bash
python <SKILL>/scripts/render_report.py --result result.json --meta meta.json \
    --output 历史评估法报价测算报告.pdf
```
- 页面 414×896px（手机一屏比例），深色卡片式单栏排版，手机 PDF 阅读器 fit-width 即原生浏览；
- **第一页必须一次给全决策要素**（缺一项回去补 meta/result）：
  1. 目标报价折扣率；2. 目标报价金额（=限价×折扣）；3. 模拟表现（平均分/排名/并列带）；
  4. **统计口径说明**（琥珀框：历史估计+情景假设、非最优报价、不是中标承诺）；
- 报告结构：Hero+KPI+口径备注 → 01 报价区间圈定（区间轴+对手折扣条+折扣×折扣原生矩阵表）
  → 02 评分方法识别（原文公式+依据+**价格分算法一致性校验卡**）→ 03 历史折扣证据
  → 04 四步区间推导 → 05 情景模拟表 → 06 报价建议 → 07 限制与声明；
- 所有数字从 `result.json` 读取（渲染器自动取），**禁止手算或改写**；
- 报告以 HTML/CSS 原生绘制区间图与矩阵表，不嵌位图（与 bid-price-calc 版式纪律一致）。

### Step 7：信息分享长图（可选，微信/群聊单张长图）
```bash
python <SKILL>/scripts/render_infographic.py --result result.json --meta meta.json \
    --output 历史评估法信息图.png
```
- 1200px 宽全页截图；自动内嵌同目录 `heatmap_折扣乘折扣.png`（base64）；
- 定位是分享图，不嵌入 PDF。

### 交付与回复
把 PDF（+ 可选信息图）放到标书同目录。回复用户时给出：**目标折扣率、目标报价金额、
并列带与取舍理由、识别的评分方法与依据一句话、主要限制**；完整细节以 PDF 为准。
数字一律从 `result.json` 读取，禁止手算。不另写 Markdown 报告（report.md 仅作底稿）。

### 自检（提交前逐条过）
- [ ] `optimal_price == ceiling_price × optimal_discount`（误差 ≤0.01 元）；
- [ ] 目标折扣落在目标区间内；PDF 首屏四要素齐全、统计口径与数字同屏；
- [ ] `scoring_evidence` 有页码/原句；`consistency` 已核验或显式标注"未核验"；
- [ ] 报告中出现并列带解释（推荐值 ≠ 平均分最高时必须说明）；
- [ ] 情景模拟中候选折扣未触发异常价（<50% 或 >200% 基准）；
- [ ] 回复中的每个数字都能在 result.json / PDF 中找到出处。

## Example

用户给"招标文件 PDF + 参与单位名单 + 我方上次中标折扣 80%"，说"用历史评估法算目标报价"：
→ Step1 提取基准价法原文与限价 564,150.92 → Step2 MCP 逐家查 12 家折扣，回查关键证据
项目的评标办法标注同/异口径 → Step3 定 70-80%、验证、收缩 70-75% → Step4 引擎模拟
→ Step5 写 meta.json（含 consistency）→ Step6 渲染 PDF → Step7 出分享长图。
回复：73% / 411,830.17 元（并列带 73-75% 取偏低），PDF+PNG 路径。

## Troubleshooting
| 症状 | 原因 | 处理 |
|---|---|---|
| PDF/长图退出码 3 | 无 python playwright | 降级交付 report.md + 图并说明；或 `pip install playwright && playwright install chromium` |
| PDF 首屏缺决策要素 | meta/result 字段缺失 | 补齐后重渲染，不要手改 HTML |
| 一致性卡片显示红色"未提供" | meta 缺 `consistency` | 回查证据项目评标办法后补 `consistency.projects` 重渲染 |
| 矩阵表/中文乱码 | 环境无 Microsoft YaHei | 安装中文字体或改 SimHei（模板 font-family） |
| PDF 出现灰色粗横线 | Chromium 打印 CSS 渐变条纹 bug | 模板中不要用 CSS 渐变画打印用条纹/网格 |
| 推荐值 ≠ 平均分最高值 | 并列带规则（正常） | 报告会自动写明；确认 `tie_band`/`prefer_low` 符合用户意图 |
| 结论随情景漂移大 | shift 假设敏感 | 与用户确认市场冷/热后调整 `scenarios.shift` 重跑 |
| PDF 提取招标文件乱码 | 控制台编码 | 用 fitz 提取并以 utf-8 写文件，不走控制台默认编码 |
| MCP 查不到限价 | 公告不含限价 | 用招标公告限价表换算；都没有则用同客户历史折扣并标注口径 |

## Important
- **不承诺中标**：任何输出必须保留"不构成中标承诺"声明（PDF 首屏统计口径 + 文末声明）。
- **方法识别必须有原文依据**（`scoring_evidence` 章节+页码+原句），禁止静默猜测。
- **同一甲方 ≠ 同一算法**：价格分算法一致性必须核验并在报告展示；异口径折扣不可直接外推。
- **正式报告必须是手机版式 PDF**（414×896，首屏四要素齐全），数字全部来自 `result.json`。
- **报价建议必须带并列带解释**；折扣率与金额必须同时给出，金额 = 限价 × 折扣可复算。
- **证据禁止编造**：查不到就标"无数据"按中性区间处理。
