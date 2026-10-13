# 输入参数与 CLI 用法（inputs.md）

## 一、CLI 概览

```bash
# 1) 运行测算（输出结构化 JSON）
node <skill>/scripts/run_calc.js --input input.json --output result.json [--tool-root "D:\32 投标研究\01 报价测算\统计工具"]

# 2) 查看某页面全部输入项与默认值（共 298 项，用于发现规则专属参数 id）
node <skill>/scripts/run_calc.js --list-inputs --page base --output inputs.json

# 3) 渲染手机版式报告 PDF（主交付物；需 python playwright）
python <skill>/scripts/render_report.py --result result.json --meta meta.json --output 报价测算报告.pdf

# 4) 渲染信息图 PNG（可选，独立分享长图，不嵌入 PDF）
python <skill>/scripts/render_infographic.py --result result.json --meta meta.json --output 报价测算信息图.png

# 5) 渲染基础概率直方图 PNG（仅 playwright 不可用时的降级备用）
python <skill>/scripts/render_chart.py --result result.json --output chart.png --title "规则中文名"
```

工具目录（toolRoot）解析顺序：`--tool-root` > 环境变量 `BID_TOOL_ROOT` >
`<skill>/config.json` 的 `toolRoot` > 默认 `D:\32 投标研究\01 报价测算\统计工具`。
若工具被移动，改 `config.json` 即可。

## 二、input.json schema

```json
{
  "page": "base",
  "seed": 20260101,
  "inputs": {
    "benchmarkRule": "lowestSecondaryAverage",
    "scoringRule": "deviationInterpolation",
    "ceilingPrice": "898.977807",
    "maxPrice": "890",
    "minPrice": "760",
    "participantCount": "20",
    "simulationCount": "10000"
  }
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `page` | 否 | `base`（单一报价区间，默认）或 `pro`（主标+多组对手区间） |
| `seed` | 建议 | 随机种子；同 seed 结果完全可复现（已验证）。正式报告固定一个 seed |
| `unitLabel` | 否 | 结果展示单位（默认 `万元`）。小金额项目（如 18 万）应**按"元"仿真**（ceilingPrice/maxPrice/minPrice 全部用元），再设 `"unitLabel": "元"`——否则整数万元分箱会毁掉分辨率；runner 会把结果文案里的"万元"一并替换 |
| `deviationAnchors` | 否 | 偏差率插入法自定义锚点 `[[偏差%, 分数], ...]`，覆盖引擎默认规则表。**线性扣分规则的精确复刻手段**：如"满分40、高于每1%扣0.2、低于每1%扣0.1、扣完为止" → `[[−400,0],[−100,30],[−10,39],[0,40],[10,38],[50,30],[100,20],[200,0]]`（锚点间线性插值，外侧被引擎钳制在端点分 = 扣完为止）。注意配合 `benchmarkRule=averageMethod2` 时必须用 `scoringRule=deviationInterpolation`（它在计分链中最先匹配，可绕开 averageMethod2 绑定的专用计分） |
| `inputs` | 是 | key = 页面 DOM id，value 一律**字符串**；未给的用页面默认值 |
| `fixedBid` | 否 | **条件命中仿真**：把我方报价固定为该数值（bids[0]），对手仍随机。结果字段 `fixedBidHit`（%）= 条件中标概率。与主测算分开跑（主结果的分布/区间是无条件口径）；自检：设为区间顶部应 ≈0% |

### page=pro 时的差异输入
- `mainMaxPrice` / `mainMinPrice`：主标报价区间上下界
- 对手分组：Pro 页用 `.competitor-range` 动态行，当前 CLI 只覆盖主标字段；
  多对手分组请用 `page=base` 的 `maxPrice/minPrice/participantCount` 近似，
  或在报告中注明"未建模对手分组"。

## 三、通用参数（所有规则都会读）

| id | 含义 | 默认 | 取值建议 |
|---|---|---|---|
| `ceilingPrice` | 最高限价/招标控制价（万元） | 898.977807 | **必须**取标书原文，纯数字 |
| `maxPrice` / `minPrice` | 模拟报价分布上下界（万元） | 890 / 760 | 依据控制价与市场行情估计（如控制价×0.98 与×0.80），报告中说明估计依据 |
| `participantCount` | 模拟投标家数 | 20 | **按标书口径取值**：询比/邀请竞争性磋商常见 3~8 家（明文"不足 3 家失败"的下限即 3）；公开招标/电子商城常见 20~40 家。不确定时跑 2~4 档敏感性（如 4/20/40）填入 meta.json 的 `sensitivity`。家数越大基准价越稳、目标带越窄（40 家时可窄至 ±0.4%），**不要默认个位数** |
| `simulationCount` | 蒙特卡洛次数 | 10000 | 快速试算 1000~2000，正式报告 10000 |
| `totalScore` | 价格分满分 | 100 | 标书评分表 |
| `scoringRule` / `benchmarkRule` | 规则选择 | deviationInterpolation / lowestSecondaryAverage | 见 method-map.md |

## 四、常见规则专属参数（默认即标书常见的池）

| id | 默认 | 含义 |
|---|---|---|
| `kValues` | 95,96,97,98 | 单随机 K 池（%） |
| `k1Values` / `k2Value` | 95,96,97,98 / 95 | 双随机 K1 池 / K2 |
| `q1Values` | 65,70,75,80,85 | 随机权重 Q1 池（%） |
| `randomFactors` | 0.95 | 限定随机数系数池 |
| `secondRandomFactors` | （空） | 第二随机数池（双随机用） |
| `g1Values` / `g2Values` | 10,15,20 / 10,15,20,25,30 | 新均值入围 G1/G2 池 |
| `floatRate` | 0.03 | 下浮率（0.03 = 3%） |
| `penaltyHigh` / `penaltyLow` | 0.9 / 0.6 | 传统计分：高/低 1% 扣分步长 |
| `minScoreLimit` | 0 | 扣分后最低分 |
| `baseScore` / `baseStepE` / `baseStepF` | 45 / 1 / 2 | 基础分规则 |
| `deductionAmount1/2` | 0 | 合理最低价：评标价扣除项 |
| `averageMethod4ARatio/BRatio` | 1/6 | 平均值法4 去高/去低比例 |
| `aboveAverageCount` / `belowAverageCount` | 7 / 8 | 新均值入围上下家数 |

**不确定某规则读哪些 id 时：**
1. `--list-inputs` 拿全量 298 个 id 及默认值；
2. `rg -n "<规则中文名>" "<toolRoot>/frontend/投标报价概率计算.html"` 定位该规则的参数面板，
   面板里 input 的 `id` 就是可覆盖的 key；
3. 标书没写明的参数**保持默认**（与网页行为一致，运行时自动随机抽取）。

## 五、result.json 关键字段

| 字段 | 含义 |
|---|---|
| `ok` | false 时看 `error`（含堆栈）与 `logs` |
| `seed` | 本次随机种子（与 input.json 一致，供信息图展示） |
| `fixedBid` / `fixedBidHit` | 条件仿真的固定报价（元/万元）与其**条件中标概率（%）**——报告"命中概率"的数据来源 |
| `winningMean` | **胜出报价参考值（万元）**——报告核心数字 |
| `targetRange` | **最终报价目标范围** = 低风险区间（均值 ±0.5σ，向下/上取整），`{lower, upper}` |
| `riskZones.low/medium/high` | 三档风险区间边界（low ⊂ medium ⊂ high） |
| `histogram.probabilities` + `histogram.minPrice` | 各价位胜出概率（%），供绘图 |
| `simulations` | 实际模拟次数 |
| `applied` | 本次实际覆盖的输入 |
| `resultsHtml` | 原页面结果区 HTML（含规则随机参数回显，可摘录进报告） |
| `logs` | 页面 console 日志（排错用，含 `[alert]` 原工具警告） |

## 六、输出解读（给用户的"最终报价目标范围"）

- **目标带（低风险）** = `targetRange`：胜出报价均值 ±0.5σ。落在这里的历史模拟胜出频率最高。
- **中风险** = ±1σ 内除去低风险的两侧：可博更高利润或更稳中标，但偏差开始放大。
- **高风险** = ±1.5σ 内除去中风险的两侧：明显偏离模拟最优。
- 报价建议永远是**区间 + 选点逻辑**，不是单点承诺；必须保留"不构成中标承诺"的表述。

## 七、已知原工具问题（runner 已自动处理）

1. `enhanced_script(.pro).js` 中 `const scoringRule` 作用域 bug（循环内声明、函数级使用）
   → runner 在内存中降级为 `var`，不改原文件，`logs` 中会记录 `[patch]`。
2. 原页面依赖 CDN Chart.js → runner 用桩替代，不影响数值。
3. 重复触发：页面初始化会额外跑 1~2 次模拟（DOMContentLoaded/load/change），最终结果以
   最后一次为准，数值与网页单次点击一致的逻辑相同。
