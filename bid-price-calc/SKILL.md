---
name: bid-price-calc
description: 投标报价测算：读取招标文件/标书，自动识别评标基准价方法与算分规则，调用本地"统计工具"（投镜 BidMirror，57 种基准价规则 + 15 种算分规则）做蒙特卡洛模拟，输出手机版式 PDF 测算报告（含概率分布图、家数敏感性）与最终报价目标范围，另可出信息分享长图。Use when 用户提到"帮我算报价""根据标书测算投标报价""识别评标办法/基准价计算方法""报价概率/中标概率测算""给出最终报价目标范围""投标报价策略"，或提供标书并要求报价分析。Do NOT use for 开标后的现场算分明细复核（引导原工具 Live 页）。
---

# 投标报价测算（bid-price-calc）

把标书变成"方法识别 → 无头测算 → 报告+图表"的完整链路。计算引擎是本地原工具
（`D:\32 投标研究\01 报价测算\统计工具`）的无头运行时，结果与网页版一致且可用 seed 复现。

## 依赖检查（每次任务开始）

```bash
node --version     # 需要 Node ≥ 18
python -c "from playwright.sync_api import sync_playwright; print('ok')"   # 必需：报告 PDF + 信息图
```
缺 Node → 无法测算，直接告知用户；
缺 playwright → 报告降级为 Markdown + `render_chart.py` 基础直方图，并在交付时说明。

`<SKILL>` 下文指本 skill 目录（`~/.agents/skills/bid-price-calc`）。
工具目录（toolRoot）按 `<SKILL>/config.json` → `--tool-root` → `BID_TOOL_ROOT` 顺序解析。

## Instructions

### Step 1：提取标书文本
- PDF → 用 pdf 相关工具提取；Word → docx 相关工具；已有纯文本直接用。
- 只要能定位"评标办法/价格评审"章节即可，不必全文精读。

### Step 2：识别报价方法（核心）
严格按 `<SKILL>/references/method-map.md` 执行：
1. 定位评标办法章节，提取字段清单（控制价、基准价公式、随机系数区间、去极值/入围、
   下浮率、报价得分公式、投标家数）；
2. 先判省份圈定候选组，再用"公式特征信号表"精确匹配 `benchmarkRule`；
3. 匹配 `scoringRule`（算分规则）；
4. 无法唯一确定 → 列 2~3 个候选，向用户确认，或全部测算后在报告中对比。

**识别结果必须给出原文依据（章节/页码/原句）**，不允许只写方法名。

### Step 3：构造 input.json
按 `<SKILL>/references/inputs.md`：
- 必填：`benchmarkRule`、`scoringRule`、`ceilingPrice`（万元纯数字）；
- 估计值（`maxPrice`/`minPrice`/`participantCount`）要写明依据；
- 标书写明的随机区间/系数**必须覆盖默认池**；
- 正式测算固定 `"seed": 20260101`、`"simulationCount": "10000"`；
  快速试算可用 1000。工作文件放标书同目录或系统临时目录。

```json
{
  "page": "base",
  "seed": 20260101,
  "inputs": {
    "benchmarkRule": "threeWeightRandom",
    "scoringRule": "deviationInterpolation",
    "ceilingPrice": "1250.36",
    "maxPrice": "1225",
    "minPrice": "1030",
    "participantCount": "24",
    "simulationCount": "10000"
  }
}
```

### Step 4：运行测算
```bash
node <SKILL>/scripts/run_calc.js --input input.json --output result.json
```
- `ok=true` → 继续；`ok=false` → 看 `error` 堆栈与 `logs`（含 `[alert]` 原工具警告），
  按下方 Troubleshooting 处理，不要跳过继续编结果。

### Step 4b：命中概率（条件仿真，给出首选/备选的中标概率）
在主测算之外，**首选、备选各跑一次"固定我方报价"的条件仿真**（input 与主输入相同，
仅多一个 `fixedBid` 字段；脚本会在内存中把 `bids[0]` 固定为该报价，对手仍随机生成）：

```json
{ "fixedBid": 165500, ...其余与 input.json 相同 }
```
```bash
node <SKILL>/scripts/run_calc.js --input input_hit_primary.json   --output result_hit_primary.json
node <SKILL>/scripts/run_calc.js --input input_hit_secondary.json --output result_hit_secondary.json
```
- 结果字段 `fixedBidHit`（%）= 该报价价位在模拟中的胜出频率 = **条件中标概率**
  （对手为连续随机值，落在同一整数价位的概率≈0，故该频率即我方中标频率）；
- **必须用独立运行**：主结果的分布图/风险区间是无条件口径，不能混用；
  也不能拿无条件直方图的单点概率当命中率（被价位摊薄，量级完全不同）；
- 自检：把 `fixedBid` 设为报价区间顶部（如 maxPrice）应得到 ≈0%，否则 patch 未生效，查 `logs` 里的 `[patch]`。

**再跑第三次：胜出报价参考值本身**（`fixedBid = round(winningMean)`，若首选价正好等于
参考值则复用），其 `fixedBidHit` 写入 `meta.mean_hit`——报告**首屏**的"胜出报价参考值"
卡片必须同时显示这个命中概率（渲染器读 `meta.mean_hit`），不能只在文末的报价建议里出现。

### Step 5：写 meta.json（识别依据 + 报告素材）
放在 `--result` 同目录，字段：

```json
{
  "project": "项目名称（与标书一致）",
  "date": "YYYY-MM-DD",
  "rule_label": "平均值法2（≤5家全平均 / >5家去极值平均）",
  "rule_evidence": "章节+原句（可含页码）",
  "rule_formula": "评标基准价 = …（招标文件原文公式，照抄不要改写）",
  "scoring_label": "偏差率插入法（线性扣分精确复刻）",
  "scoring_evidence": "章节+原句",
  "scoring_formula": "报价得分 = …（招标文件原文算分公式，照抄不要改写）",
  "suggest_primary": "165500",
  "suggest_secondary": "167000",
  "suggest_primary_hit": 44.8,
  "suggest_secondary_hit": 42.5,
  "mean_hit": 46.2,
  "suggest_note": "首选/备选理由与风险边界（2~3 句，可给含税换算与占控制价比例）",
  "params_note": "K∈[…]（标书写明）或 采用默认随机池",
  "sensitivity": [
    {"n":"4家","branch":"全平均分支 · 主场景","mean":165635,"low":163317,"high":167953,"main":true},
    {"n":"20家","branch":"去极值分支","mean":166688,"low":165744,"high":167632}
  ],
  "sensitivity_note": "家数假设的口径说明与稳健性结论",
  "limits": ["限制1（可选，缺省用通用三条）"]
}
```
- `rule_formula` / `scoring_formula` 是**必填**：招标文件里怎么算基准价、怎么算分，照抄原文公式，
  报告"报价方法识别"章节会单独排一块"招标文件的报价测算方法（原文公式）"；缺失会显示红色提示。
- `mean_hit` 来自 Step 4b 的参考值条件仿真，是首屏命中概率的唯一来源。
- 折扣率（报价 ÷ 招标控制价）由渲染器按 `ceilingPrice` 自动算，无需手填。
- `sensitivity` 为可选：对**家数不确定**的项目，按 2~4 档家数（如 4/20/40）分别跑 `run_calc.js`
  再填入——公开招标常见 20~40 家，询比/邀请常见 3~8 家（详见 inputs.md 家数指引）。

### Step 6：渲染报告 PDF（主交付物，手机版式）
```bash
python <SKILL>/scripts/render_report.py --result result.json --meta meta.json --output 报价测算报告.pdf
```
- 页面 414×896px（手机一屏比例），深色卡片式单栏排版，手机 PDF 阅读器 fit-width 即为原生浏览体验；
- **第一页必须一次给全决策要素**（缺一项就回去补 meta）：
  1. 最终报价目标范围 + 占控制价折扣率；
  2. 胜出报价参考值 + **它的命中概率徽标**（`mean_hit`）+ 折扣率；
  3. 报价参考（首选/备选）+ 各自命中概率 + 折扣率；
  4. **统计口径说明**（琥珀色备注框）：写明结果是纯统计模拟、未纳入真实风险与偏差估计、
     不是最终/理想报价、命中概率只是模拟频率——防止首屏数字被当成"标准答案"；
- **报告中概率分布图只出现一次**：HTML/CSS 原生绘制，与报告同风格（风险三色 + 风险标尺 +
  参考值虚线）——不要往报告里再嵌任何位图；
- 输出顺序：Hero+KPI+统计口径备注 → 分布图 → 方法识别（含原文公式块）→ 测算输入 →
  家数敏感性（可选）→ 报价建议（价格+命中概率+折扣率）→ 限制与声明。

### Step 7：信息图 PNG（可选，独立分享长图）
```bash
python <SKILL>/scripts/render_infographic.py --result result.json --meta meta.json --output 报价测算信息图.png
```
定位是**微信/群聊分享的单张长图**，不嵌入 PDF（避免与报告重复出图）。
`render_chart.py`（matplotlib）仅作 playwright 不可用时的降级备用，风格与主报告不一致，默认不产出。

### 交付与回复
把 PDF（+ 可选信息图）放到标书同目录，回复用户时给出：**目标范围、胜出参考值（含命中概率）、
首选/备选价（含命中概率与占控制价折扣率）、识别出的方法与依据一句话、主要限制**；
完整细节以 PDF 为准，不再另写 Markdown 报告。

数字一律从 `result.json` 读取（`winningMean`、`targetRange`、`riskZones`），禁止手算或估算。

## Examples

- 用户："这是 xx 项目的招标文件，帮我算一下我们报多少合适"
  → Step 1~6 全流程，产出报告 + PNG。
- 用户："标书里写的是 ABC 值法，参数都给我填上"（附参数）
  → 直接构造 input.json 测算，识别环节以用户给的信息为准。
- 用户："再跑一下，把 K 改成 96~98"
  → 覆盖 `kValues`，同 seed 重跑并更新报告（seed 不变保证可比性）。

## Troubleshooting

| 症状 | 原因 | 处理 |
|---|---|---|
| `找不到工具目录` | config.json 的 toolRoot 失效 | 用 `--tool-root` 或改 `<SKILL>/config.json` |
| `ok=false` + `至少需要一条去高去低规则` 等 alert | 该规则需要的参数未命中（家数/阈值配置） | `--list-inputs` 查参数 id，按标书补齐 |
| `winningMean` 缺失但 ok=true | 结果 HTML 解析异常 | 查 `resultsHtml` 是否为空；空则查 `logs` 中 `[script-error]` |
| 日志里大量 `[alert]` | 原工具参数校验未通过 | 按 alert 文案修正 inputs 后重跑 |
| 图表中文乱码/字体警告 | 环境无 Microsoft YaHei | 安装中文字体或改用 SimHei，其余输出不受影响 |
| `render_report.py` / `render_infographic.py` 退出码 3 | 无 python playwright | 按降级流程：Markdown + `render_chart.py` 并说明 |
| 报告里出现两张分布图 | 误把位图嵌入 PDF | 报告只允许原生分布图一张；信息图是独立分享长图，不嵌 PDF |
| 打印出的 PDF 出现灰色粗横线 | Chromium 打印 `repeating-linear-gradient` 条纹 bug | 已改为实体 `.gridlines i` 线；模板中**不要用 CSS 渐变画打印用的条纹/网格** |
| 信息图里 evidence/suggest 是兜底文案 | meta.json 没填 | 补齐 meta.json 重渲染（识别依据与建议是报告可信度来源） |
| 首屏"胜出报价参考值"旁没有命中概率徽标 | meta 缺 `mean_hit` | 按 `round(winningMean)` 跑一次 `fixedBid` 条件仿真，把 `fixedBidHit` 写进 `meta.mean_hit` |
| 方法识别章节出现"缺 rule_formula/scoring_formula"红字 | meta 没抄原文公式 | 从标书评标办法照抄基准价公式与算分公式填入 meta 后重渲染 |
| 统计口径备注被挤到第二页 | 首屏纵向占位超标（项目名过长/模板 padding 被改） | 恢复 `report_page_template.html` 的 hero/kpi/stat-note 压缩尺寸，保证四要素同屏 |
| 想确认与网页版一致 | — | 同参数在网页点"开始智能模拟"，对比胜出参考值与风险区间 |
| 用户要开标现场按真实报价算分 | 属 Live 页场景 | 本 skill 只做事前模拟；引导用户打开原工具 `frontend/报价现场计算.html` |

## Important

- **不修改原工具任何文件**（runner 只做内存修补，见 inputs.md 第七节）。
- **不承诺中标**：任何输出必须保留"不构成中标承诺"声明。
- **方法识别必须有原文依据**；识别不确定时先问用户或跑候选对比，禁止静默猜测。
- 正式报告必须：固定 seed + 10000 次模拟 + **手机版式 PDF**（内含唯一一张原生分布图）+ 目标范围；
  meta.json 的 `rule_evidence`/`scoring_evidence`/`suggest_*` 必须认真填写。
- **家数不能拍脑袋**：按标书口径取值（询比/邀请 3~8 家，公开招标 20~40 家常见），
  不确定时至少跑 2 档家数敏感性并写进报告。
- **报价建议必须带命中概率**：首选/备选各跑一次 `fixedBid` 条件仿真取 `fixedBidHit`，
  写入 meta 的 `suggest_primary_hit`/`suggest_secondary_hit` 后渲染；禁止用无条件直方图单点概率冒充。
- **命中概率必须上第一页**：胜出报价参考值的命中概率来自按 `round(winningMean)` 的第三次
  `fixedBid` 仿真（写 `meta.mean_hit`），与目标范围、首选/备选同屏展示；只写在文末等于没写。
- **首屏必须带统计口径备注**：报价是纯统计模拟结果、未纳入真实风险与偏差估计、不是最终/理想报价，
  这句话要和数字同屏出现，不能只藏在文末"限制与声明"里。
- **报告必须抄招标文件的测算法**：`rule_formula`/`scoring_formula` 照抄原文公式，并给出章节+原句
  的 `rule_evidence`/`scoring_evidence`；**报价占控制价的折扣率**由渲染器自动算并显示在
  目标范围、参考值、首选/备选四处，缺折扣率说明 meta 的 `ceilingPrice` 没取对。
