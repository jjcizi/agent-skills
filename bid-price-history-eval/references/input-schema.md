# input JSON Schema

完整可跑示例：`example-gansu.json`（甘肃电信案例真实数据）。

```jsonc
{
  "project": "项目名称（用于图标题/报告标题）",
  "ceiling_price": 564150.92,          // 最高限价合计（元，纯数字）
  "our_range": [0.65, 0.90],           // 热力图"我方折扣"轴范围
  "opp_range": [0.65, 0.90],           // 热力图"对手折扣"轴范围
  "axis_step": 0.01,                   // 轴步长

  "scoring": {                          // 必须逐条对齐招标原文
    "method_text": "价格评分方法原文全文…",  // 原文照抄，报告会引用
    "above_k": 1.0,                    // 高于基准价扣分系数
    "below_k": 0.5,                    // 低于基准价扣分系数
    "base": 50.0                       // 等于基准价得分
  },

  "base_interval": [0.70, 0.80],       // 第1步：基础区间 [下限, 上限]
  "competitor_validate": [0.70, 0.80], // 第2步：对手折扣覆盖区间（用于均分Top5与蓝框）
  "target_interval": [0.70, 0.75],     // 第3步：目标区间
  "narrow_reason": "第3步收缩的一句话依据", // 写进报告推理链
  "tie_band": 0.3,                     // 并列带宽度（分），默认 0.3
  "prefer_low": true,                  // 并列带内取偏低（默认 true）

  "candidates": [0.70, 0.72, 0.73, 0.74, 0.75],  // 第4步：候选折扣（4~6个）

  "scenarios": [                       // 市场温度情景，对每家对手报价平移
    {"name": "低价情景", "shift": 0.0},
    {"name": "中价情景", "shift": 0.03},
    {"name": "高价情景", "shift": 0.05}
  ],

  "competitors": [                     // 每家参与单位（含我方不在内）
    {
      "name": "单位简称（≤8字，热力图标签）",
      "low": 0.72,                     // 历史折扣区间下限
      "high": 0.80,                    // 历史折扣区间上限
      "bid": 0.72,                     // 情景基准报价（通常=low）
      "evidence": "证据链：项目名+折扣数+时间（可含来源）"
    }
  ]
}
```

## 校验清单（跑之前）

- [ ] `method_text` 是招标原文，`above_k/below_k` 与原文公式一致；
- [ ] `ceiling_price` 是**合计**限价（分档单价限价需先加总），与报价口径一致；
- [ ] 每家 `low ≤ bid ≤ high`；无数据单位写明"无数据"并给中性区间；
- [ ] `candidates` 全部落在 `target_interval` 内；
- [ ] `target_interval ⊆ base_interval`，`competitor_validate` 与对手 `low/high` 相容；
- [ ] 情景 `shift` 与用户确认过市场温度（冷/温/热）。

## 输出语义

- `optimal_discount`：并列带内按 `prefer_low` 选定的最终折扣；
- `target_price = ceiling_price × optimal_discount`（脚本内计算，误差≤0.01 元）；
- `tie_set`：统计并列带；报告结论表会列出，若推荐值非均分最高者必须引用它解释；
- `result.json`：结构化结果（PDF/长图渲染的唯一数字来源），含 intervals、competitors、
  simulation、avg_scores/avg_ranks、matrix_top、optimal/optimal_price、scoring 全文。

## 证据收集时的额外要求（配合 meta.json）

- 每家 `evidence` 字符串里写清项目名与折扣数字（可溯源）；
- 关键证据项目的价格分算法（低价基准/平均基准）需按 mcp-recipes E 节核验，
  结论填入 meta.json 的 `consistency`（不进 input，但报告必展示）。
