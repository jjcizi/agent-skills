# 逻辑图模板 · 版式索引 Schema

对模板的每一页，读图后输出**一个 JSON 对象**。所有页的 JSON 合并成数组，即为索引。

## 字段定义

| 字段 | 类型 | 说明 |
|---|---|---|
| `page` | int | 页码（1–141） |
| `page_title` | str | 页面上自带的主标题文字；无则 `""` |
| `summary` | str | ≤40 字，这页图示在表达什么 |
| `logic_type` | enum | 见下方枚举，选最贴切的一个 |
| `structure.topology` | enum | `横排` `纵排` `网格` `环形` `放射` `层叠` `混合` |
| `structure.slot_count` | int | **顶层并列项数** —— 见下方「slot_count 判定规则」 |
| `structure.ordered` | bool | 是否暗示先后顺序 |
| `structure.has_arrows` | bool | 有无箭头/指示符 |
| `structure.has_connectors` | bool | 有无连接线 |
| `structure.hierarchy_depth` | int | 层级深度，1 = 平铺 |
| `capacity.main_slots` | int | 等于 `slot_count` |
| `capacity.per_slot_chars` | int | **单个文本块**可容纳的中文字数上限（保守估） |
| `capacity.total_chars` | int | 总容量（≈ 各文本块之和） |
| `best_for` | str[] | 2–4 条，适合放什么（写到"五项并列的制度要点"这种具体度） |
| `avoid_for` | str[] | 1–3 条，不适合什么 |
| `scenes` | str[] | 适用场景，如 `工作汇报` `教学课件` `年度总结` `产品介绍` |
| `placeholders` | str[] | 页面原有占位/示例文字，**原样抄录**，≤8 条 |
| `fill_hint` | str | 填充时的注意事项 |
| `confidence` | float | 0–1，对该页判断的把握 |

## `logic_type` 枚举

`并列要点` `顺序流程` `循环闭环` `对比` `层级金字塔` `二维矩阵` `时间轴` `总分发散` `漏斗筛选` `递进阶梯` `因果链` `环形关系` `象限分布` `清单列表` `其他`

## slot_count 判定规则（消除歧义，必须遵守）

`slot_count` = **用户直觉上的顶层并列项数**，即"这页在讲几件事"。

- 有分组时，数**顶层组数**，不数组内的子项。子项数量写进 `fill_hint`，嵌套用 `hierarchy_depth` 表达。
- 中心节点（如"总分"结构的中心圆）**算 1 个**，扇出的分支算其余。
- **不算**：页面主标题、编号小圆点、图标、装饰形状、背景色块。

举例：
- 「中心圆 + 6 个扇出卡」→ `slot_count = 7`（1 中心 + 6 分支），`hierarchy_depth = 2`
- 「5 个编号列，每列 2 个子卡」→ `slot_count = 5`，`hierarchy_depth = 2`，`fill_hint` 注明"每列含 2 个子块"
- 「一排 6 张并列卡」→ `slot_count = 6`，`hierarchy_depth = 1`

## 硬性要求

1. **必须真读图**，不得凭页码或形状数量猜测。看不清就降低 `confidence` 并在 `fill_hint` 说明。
2. `slot_count` 只数可填内容的主区块 —— 装饰、图标、背景形状、纯色块不算。
3. `per_slot_chars` 保守估计：想象中文字符塞进那个框会不会溢出换行。宁可低估。
4. `placeholders` 原样抄录，不翻译、不改写、不润色。
5. 输出严格 JSON（数组），不要额外散文。

## 输出（必须增量写盘）

**不要攒到最后一次性写。** 每分析完 2–3 页，就用一次写操作把**当前累计的完整数组**覆盖写入：

`索引/batches/batch_<起>-<止>.json`

这样即使中途中断，已完成的部分也已落盘。全部完成后，回复（≤150 字）：完成页数、`logic_type` 分布、把握最低的页码。

## 工作方式（重要）

- 逐页给**结论**，不要在多套方案之间反复权衡、也不要大段复述图片内容。
- 判断依据写进字段即可，不需要在思考里展开辩论。
- 每页读图一次，看完直接落 3–5 个关键字段。宁可 `confidence` 低一点，也不要卡住。
