# MCP 查询配方（知了标讯 zhiliaobiaoxun）

目标：为参与投标的每一家单位建立**折扣率证据链**（项目名 + 报价 + 限价 + 折扣率 + 时间 + 来源）。
计费提示：以下配方按"先便宜后贵"排序，免费/低价调用优先；每次调用前先确认
`get_account_balance`（免费）余额充足。

## A. 找同类项目（项目名 → 后续取详情）

**A1 按品类+运营商搜中标结果**（一次拿到候选列表，优先用）：
```
search_bids(keywords=["培训", "师资"], match_modes=["sm"],
            bid_process=[7], begin_date="2024-01-01", end_date="2026-12-31",
            page_size=20)
```
- `match_modes=["sm"]` 搜标的物；搜公司用 `["winner"]`/`["caller"]`；搜标题用 `["title"]`。
- 多关键词 AND：`keywords="电信 培训"`（空格）或 `keyword_groups`。

**A2 精确复刻某历史项目**（用户给了项目名/链接）：
```
query_bids_advanced(keywords="<项目全名>", match_modes=["title"],
                    need_fulltext=True, page_size=10)
```

**A3 查某项目的完整生命周期**（招标限价 → 中标价配对）：
```
get_bid_timeline(bid_url="https://www.zhiliaobiaoxun.com/content/{bid_id}/b{bid_type}")
```
招标公告（bid_process=4）里找**最高限价/最高投标限价**，中标公告（bid_process=7）
里找**中标价** → 两者相除 = 折扣率。这是折扣率最可靠的算法。

## B. 取详情算折扣率

```
get_bid_detail(bid_id=<id>, bid_type=<1|2>)
```
- 从 `source`（公告正文 HTML）里抓：限价表（分档单价限价要**合计**）、
  中标价/投标报价、含税口径；
- 正文没有限价 → 查该项目招标公告（timeline 回溯）或标段最高限价表附件
  （`attachment_urls`）；
- 换算：`折扣率 = 中标价 ÷ 同口径限价合计`；含税/不含税、全费用/师资费口径必须一致，
  口径不同先剥离差额（食宿车班等）再算，见 methodology.md。

## C. 按单位查（核心：每家参与单位跑一遍）

**C1 公司消歧**（简称 → 确定主体）：
```
search_company(company_name="<简称>")
```
拿到 `company_id` / `url` 后再做 C2/C3。

**C2 该公司的业务关键词与主要甲方**（判断业务集中省份/客户）：
```
get_company_business_keywords(company="<company_id>", limit=30)
```
→ `top_callers` 判断"同客户稳定性"，`top_provinces` 判断"客情强弱区域"。

**C3 该公司的中标记录 → 逐个算折扣**：
```
search_bids(keywords="<公司全称>", match_modes=["winner"],
            bid_process=[7], begin_date="2024-01-01", end_date="2026-12-31")
```
→ 对命中的项目跑 A3+B 配折扣率；同客户（如"中国电信甘肃"）的记录**单独打标**，
权重最高。

**C4 交叉验证：竞争对手一起投标名单**（补充漏掉的参与方/其报价习惯）：
```
find_competitors(company="<company_id>", limit=20)
```

## D. 行业/地区锚（第一步的下限锚、第二步的验证）

**D1 全国同类中标折扣分布**（找"历史最低折扣"行业底线）：
```
get_top_suppliers(keywords=["培训"], match_modes=["sm"],
                  begin_date="2024-01-01", end_date="2026-12-31", limit=20)
get_top_purchasers(keywords=["培训","师资"], match_modes=["sm"],
                   begin_date="2024-01-01", end_date="2026-12-31", limit=20)
```
对 Top 项目逐个 B 步换折扣，最低者 = 行业底线候选。

**D2 同省报价习惯**（甲方所在省）：
```
search_bids(keywords=["培训"], match_modes=["sm"], provinces=["甘肃"],
            bid_process=[7], begin_date="2024-01-01", end_date="2026-12-31")
```

**D3 聚合统计**（量大时先看盘子）：
```
aggregate_bids_advanced(group_by=["province"], metrics=["count","sum_amount"],
  filters={"keyword_groups":[{"keywords":["培训","师资"],"match_mode":"sm"}],
           "begin_date":"2024-01-01","end_date":"2026-12-31"})
```

## E. 评分方法一致性核验（每个关键证据项目必做）

同一甲方不同标的价格分算法可能不同（低价基准 / 平均基准(去极值) / 次低价 / 随机系数），
不同算法下历史折扣不可直接外推。对每个**将进入证据链的关键项目**执行：

**E1 抓公告正文搜算法关键词**：
```
get_bid_detail(bid_id=<该项目id>, bid_type=1)   # 招标公告
```
在返回的 `source`（HTML 正文）中搜：`评标基准价`、`价格评分方法`、`最低价`、
`算术平均`、`去掉一个最高`、`下浮`、`随机`。

**E2 判定三态并记录**：
- 正文命中"算术平均 / 去掉最高最低"→ **平均基准(去极值)**；
- 命中"最低价为基准价 / 经评审的最低投标价"→ **低价基准**；
- 命中"次低 / 随机 / 下浮系数"→ 对应算法；
- 正文没有评标办法（常见于中标结果公示）→ **未核验**，回查该项目招标公告或标书全文；
- 判定结果记入 meta.json `consistency.projects[].match`：true/false/null。

**E3 使用规则**：同口径→正常作证据；异口径→只作边界参考、按算法差异方向修正后使用
（低价基准历史折扣 → 外推到平均基准时上修）；未核验→显式声明，保守使用。
写入报告 `consistency.note` 说明处理方式。

## F. 兜底

- MCP 无记录 / 限价缺失 → `WebSearch`：`"<项目名> 中标 公告 限价"`、
  `"<运营商> <年份> 培训 中标 折扣"`；
- 仍查不到 → 该单位标"无数据"，按行业中性区间估计并在报告显式声明，
  **禁止编造折扣率**。

## 产出物格式（写进 input JSON 的 competitors 字段）

```json
{"name": "华为技术服务", "low": 0.75, "high": 0.80, "bid": 0.75,
 "evidence": "2023-2024甘肃电信同类项目综合折扣83.49%，剥离食宿车班后师资约79.46%；连云港/北京记录交叉验证75-80%"}
```
- `bid` = 三档情景的基准报价（通常取区间下限，与低价情景对齐）；
- `evidence` 必须含具体项目与数字，能溯源。
