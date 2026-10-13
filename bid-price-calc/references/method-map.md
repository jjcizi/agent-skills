# 标书 → 测算方法识别映射表（method-map）

本文件是 skill 的领域核心：把招标文件"评标办法/价格评审"章节的原文，映射到工具的
`benchmarkRule`（基准价规则）与 `scoringRule`（算分规则）取值。

---

## 一、识别流程（按顺序执行）

### Step 1：定位评标办法章节
在标书中搜索（顺序从强到弱）：
`评标办法`、`基准价`、`评标基准价`、`价格评审`、`报价得分`、`价格分计算`、`商务标评审`、
`经评审的最低投标价`、`合理低价`、`定标标准`。通常在"第三章 评标办法"或"第四章 合同条款及格式"之前。

### Step 2：提取字段清单（缺一不可，缺的字段要单独列出并向用户确认）

| 字段 | 原文常见措辞 | 去向 |
|---|---|---|
| 最高限价/招标控制价 | "最高限价""招标控制价""预算金额""采购预算" | `ceilingPrice`（万元，纯数字） |
| 基准价计算公式 | "评标基准价=…" | → `benchmarkRule`（见第三节） |
| 随机系数及区间 | "随机数 K∈[96%,98%]""系数在 95~98 之间抽取" | 规则专属参数（如 `kValues`） |
| 去极值/入围规则 | "去掉一个最高…一个最低""G1、G2""入围 10 家" | 决定 `averageMethod2/3`、`newBasePriceRule` 等 |
| 下浮率 | "下浮 3%""让利 ×%" | 对应 float 参数 / `averageFloat` |
| 报价得分公式 | "价格分=100×(1-偏差率)…""每高 1% 扣 0.9 分" | → `scoringRule`（见第四节） |
| 投标人家数/是否公开 | "不少于 3 家""预计 20 家""公开招标" | `participantCount`：询比/邀请 3~8 家，公开招标 20~40 家常见；不确定→多档敏感性 |
| 有效报价范围 | "超过控制价 90% 的报价不参与""低于成本价废标" | 通常由规则内置；特殊时在报告中说明 |
| 暂列金/暂估价 | 仅湖北上限平均法等需要 | 规则专属参数 |

### Step 3：先判省份（最强信号）
标书封面/招标公告写明的省份（江苏、浙江、江西、辽宁、湖南、湖北、新疆、川渝、陕西、安徽）
直接圈定候选规则组。跨省项目按项目实际监管地判断。

### Step 4：用第二节"公式特征信号"精确匹配
同一省份内多个候选时，用原文公式逐条比对；仍不能确定时：
1. 列出 2~3 个最可能的 `benchmarkRule`；
2. 向用户确认，或**分别测算后对比给出**（报告中注明各候选方法的结果差异）。

### Step 5：识别算分规则（第四节），再补齐参数（inputs.md）

---

## 二、基准价公式特征 → benchmarkRule 信号表

> "→" 后为工具下拉框取值（写入 `inputs.benchmarkRule`）。同一信号有多个变体时，
> 用括号内的进一步区分点。

### 2.1 平均值族
| 原文特征 | → key |
|---|---|
| 基准价 = 全部（有效）报价算术平均 | `average` |
| 去掉 1 个最高 + 1 个最低后平均（家数>5） | `averageMethod2` |
| 按家数分档去掉若干高/低值求初均，**再对低于初均的报价求平均**（"二次平均"描述但非限价二次） | `averageMethod3` |
| 按比例去掉 a 最高、b 最低（如"各去 1/6"） | `averageMethod4` |
| 按参与家数匹配可配置去高去低规则 | `averageMethod5` |
| 有效平均值 ×(1-下浮率) | `averageFloat` |
| 平均加权（Pz/Pt 分档加权平均，α/β 系数） | `averageWeightedMethod` |
| (最高限价-暂列金-暂估价)×(1-随机下浮)+暂列金+暂估价 得上限价，再与有效平均值按 r1/r2 加权 | `upperLimitAverage`（湖北） |
| **最高限价**先平均、再对低于均值的限价二次平均 | `secondaryAverage`（最高限价二次平均法） |
| 分家数档去高去低、A/B 权重、阈值命中的"最低二次平均" | `lowestSecondaryAverage`（Base 默认规则） |
| 先全量平均，剔除偏离首均 >20% 的异常价，再平均 | `extremeValueAverage`（去极值平均+新计分法，配套专用计分） |

### 2.2 随机数族（单随机/限定随机）
| 原文特征 | → key |
|---|---|
| 基准价 = 评标价均值 × K，K 按家数分档抽取；低于限价 90% 不参与 | `random`（限定随机数法） |
| 基准价 = 最高限价 ×(100-D)%，D 在 [Dmin,Dmax] 随机 | `limitedRandomMethod2` |
| 评标价 = 报价-扣除1-扣除2；全部低于限价 85% 时用 3 个随机 K 均值×限价 | `randomMethod3` |
| 平均值 ×K，低价不废标 | `randomMethodNoLowDiscard` |
| ≥50 家先入评打分取前 10，再对入评报价 ×(1-X%) | `entryPlusRandom` |
| 平均值 ×(1-下浮) 且无随机 | `averageFloat`（若含"随机下浮"字样看 2.3） |
| (最高限价)×(1-下浮率) 简单下浮 | `upperLimitFloat`（上限下浮法） |
| 二次平均后再乘随机 K | `doubleAverageRandom` |
| 去极值后平均 ×(1-下浮)，去值比例可配 | `removeExtremesRandom` |
| 剔除异常价后平均 + 随机修正 | `eliminationAverageRandom` |
| 浙江口径的"平均值×(1-随机下浮 m%)" | `zhejiangRandomFloat` |

### 2.3 双随机/多随机族
| 原文特征 | → key |
|---|---|
| 基准价 = 评标均价·K·(1-K2) + 限价修正·K2（两个随机数） | `doubleRandom` |
| 基准价 = 限价修正·K1·K2 + 评标均价·(1-K2) | `doubleRandom2` |
| 基准价 = 平均值·(1-X%)·Q + 控制价·(1-1%·X-0.1%·Y)·(1-Q) | `doubleRandom3` |
| 含 Q/X 双随机抽取窗口 | `doubleRandom4` |
| Q1/K1/M/K2 **四个随机数**，去头尾后 A 值加权限价（川渝常见） | `fourRandomMethod` |
| 两个随机数 + "合理平均值"表述（陕西） | `doubleRandomReasonableAverage` |
| M 分档去 N1/N2 后随机抽 3 个均值 P×K×C（安徽） | `doubleRandomSegmented` |
| 7 个 u 随机数归一化为权重，μ/M/G/Q1/Q3 五区间加权（湖南"六随机五区间"） | `sixRandomFiveInterval` |

### 2.4 加权/分段/中值族
| 原文特征 | → key |
|---|---|
| 报价按区间分段加权（首尾段权重 0.1、中间 1.0、高价段 0.3 之类） | `segmentedWeighted`（10 区段，浙江） |
| 更细分段（15 区段）加权 | `segmentedWeighted2` |
| 首尾（低段/高段）单独降权的加权平均 | `headTailWeightedAverage` |
| 中位数 S，剔除 [0.2S,1.8S] 外报价，取正常报价最低值（江苏） | `medianLowPrice` |
| A=限价×(1-Δ)，B 从 <95%A 分段抽取，C=范围内最低价；基准价=(A·a+B·b+C·c)×K（江苏 ABC） | `threeWeightRandom` / `threeWeightRandom1` / `threeWeightRandom2` |
| 随机抽 a、b 百分比的平均 | `abAverageMethod`（a% b%平均值法，江苏） |
| 随机抽 a、b 绝对值的平均 | `abAverage`（ab平均值法） |
| 新均值入围：G1/G2 去高去低入围后求基准价（江苏） | `newBasePriceRule` / `1`（随机抽 R 家） / `2`（G1/G2 对调，≤20 家全入围） |

### 2.5 浙江专项（原文通常直接出现"浙江"或当地办法名）
| 原文特征 | → key |
|---|---|
| 浙江二次平均 | `zhejiangSecondAverage` |
| 浙江动态二次平均 | `zhejiangDynamicSecondAverage` |
| 浙江中值平均 | `zhejiangMedianAverage` |
| 浙江综合系数（A、B、F 系数） | `zhejiangComprehensiveFactor` |
| 浙江随机下浮 | `zhejiangRandomFloat` |

### 2.6 合理低价法（编号必须与原文一字不差）
| 省份 | key |
|---|---|
| 新疆 | `reasonableLowPrice1` / `reasonableLowPrice3` / `reasonableLowPrice5` |
| 安徽 | `reasonableLowPrice2` |
| 江西 | `reasonableLowPrice4`、水利系列 `reasonableLowPrice9`~`13`（9 随机抽取 / 10 二次平均 / 11 随机平均 / 12 随机权重 / 13 全部平均） |
| 辽宁 | `reasonableLowPrice6`（首尾去值）/ `7`（随机步距）/ `8`（分段加权） |

> ⚠️ 合理低价法编号是地方定额口径，**不要按公式猜编号**，以原文"合理低价法 N"的编号为准；
> 原文没写编号时，按所在省份的默认编号并在报告中标注存疑。

---

## 三、算分规则识别：原文特征 → scoringRule

| 原文特征 | → key | 关键参数 |
|---|---|---|
| 价格分按"偏差率-得分"对照表插值（默认表：-7%~-3% 满分 100，两侧递减） | `deviationInterpolation`（**页面默认**） | 表格可在页面"偏差率插入法"面板改；**线性扣分条款用 `deviationAnchors` 锚点精确复刻**（见 inputs.md） |
| 评标价=报价-不可竞争费，最低有效价得满分，其余 0 分 | `reasonableLowestPrice` | 不可竞争费用 `deductionAmount1/2` |
| 每高/低 1% 扣固定分（"每上浮 1% 扣 0.9 分，每下浮 1% 扣 0.6 分"） | `traditional` | `penaltyHigh=0.9` `penaltyLow=0.6` `totalScore` `minScoreLimit` |
| 按偏差比例扣分 | `proportionalDeduction` / `proportionalDeduction1` | — |
| 低价得分规则 | `lowPriceScoring` | — |
| 基础分 + E/F 步长（低 5% 内可加分） | `base` | `baseScore=45` `baseStepE=1` `baseStepF=2` |
| 有效范围内最低价中标得满分（其余 0） | `lowPriceRanking` / `lowPriceRanking1` | — |
| ±30% 内低价排列 + 高低扣分步长 | `traditionalLowPriceRanking` / `1` | `penaltyHigh/Low` |
| 随机扣分 | `randomPenalty` | 随机池 |
| 六五赋分 / 六五赋分法1 | `sixFiveScoring` / `sixFiveScoring1` | — |
| 与最低绝对值比较 | `minAbs5th` | — |

绑定关系（选择时注意）：
- `extremeValueAverage` 基准价规则自带专用计分（≤基准按偏差折算，>基准 ×0.95），scoringRule 影响被覆盖。
- `averageMethod2` 也带专用计分分支（-5%~0% 满分）。

---

## 四、参数覆盖速查（详见 inputs.md）

- 标书写明随机区间时必须覆盖默认池，例：
  - "K 在 96~98 之间抽取" → `kValues: "96,97,98"`
  - "下浮率 3%" → 对应规则的 float 参数（用 `--list-inputs` 查 id）
  - "G1=10/15/20，G2=20/30" → `g1Values: "10,15,20"` `g2Values: "20,30"`
- 未写明的参数保持页面默认（HTML 里已有默认池，运行时自动随机抽取，与原网页行为一致）。

---

## 五、识别质量自检（报告前逐条过）

1. `benchmarkRule` 的分组（省份）与标书监管地一致吗？
2. 原文公式里的**每一个系数**（K、D、Q、下浮率、去值家数）都已映射为输入或注明"采用默认池"？
3. `scoringRule` 的扣分步长/对照表与原文一致吗？
4. `ceilingPrice` 单位换算成"万元"纯数字了吗？
5. 识别依据是否引用了原文页码/章节？（报告必须给出"识别依据"）
