# -*- coding: utf-8 -*-
"""
历史数据评估法（历史评估法）报价测算引擎
用法:
    python history_eval.py --input input.json --out ./out

输入 JSON 结构见 references/input-schema.md（含甘肃电信完整示例）。
输出:
    matrix.csv                    折扣×折扣 得分矩阵
    heatmap_折扣乘折扣.png         矩阵热力图 + 对手折扣区间 + 均分曲线 + 目标圈定区间
    interval_折扣区间收敛.png      四步区间收敛漏斗图
    simulation_候选折扣得分.png    候选折扣 × 情景 得分/排名图
    scenario_tables.csv           情景模拟明细（每个候选折扣在每个情景下的基准价/得分/排名）
    report.md                     完整测算报告（推理链 + 数据 + 计算过程 + 结论）
"""
import argparse
import csv
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

def pct(v) -> str:
    """折扣率显示：整数保留整数，半点（如98.5%）保留1位小数，避免 .0% 吞掉0.5pp。"""
    v = float(v)
    x = v * 100.0
    r = round(x)
    if abs(x - r) < 1e-6:
        return f"{r:.0f}%"
    return f"{x:.1f}%"



# ---------------------------------------------------------------- scoring ---
def score_vs_benchmark(price, benchmark, above_k=1.0, below_k=0.5, base=50.0):
    """招标文件基准价法算分（甘肃电信原文公式的通用形式）。

    price > benchmark: base - (|d|/benchmark)*100*above_k
    price < benchmark: base - (|d|/benchmark)*100*below_k
    """
    if benchmark <= 0:
        return 0.0
    dev = abs(price - benchmark) / benchmark * 100.0
    k = above_k if price > benchmark else (0.0 if price == benchmark else below_k)
    if price == benchmark:
        return base
    return base - dev * k


def score_low_basis(price, benchmark, points=10.0):
    """低价基准法：得分 = 基准价(最低有效报价) ÷ 本方报价 × 满分。"""
    if price <= 0:
        return 0.0
    return benchmark / price * points


def score_generic(our, opp, sc):
    """按评分类型计算（our/opp 可为价格或同口径折扣率，只要口径一致）。"""
    if sc.get("type") == "low_basis":
        # opp 行 = 全场最低价(对手)代理；若我方更低则我方成为基准价
        return score_low_basis(our, min(our, opp), float(sc.get("points", 10.0)))
    return score_vs_benchmark(our, opp, sc.get("above_k", 1.0),
                              sc.get("below_k", 0.5), sc.get("base", 50.0))


def anomaly_desc(sc) -> str:
    if sc.get("type") == "low_basis":
        return "异常低价审查（＜限价45% / ＜均值50% / ＜次低50%）"
    return "异常价 50%–200%"


def trimmed_mean(prices):
    """算术平均值：去掉一个最高价和一个最低价；有效价≤5家不去极值。"""
    ps = sorted(prices)
    if len(ps) > 5:
        ps = ps[1:-1]
    return sum(ps) / len(ps)


def evaluate_field(our_price, opp_prices, sc, ceiling=None):
    """把"我方"并入全场景，按招标原文计算基准价、异常价、得分与排名。"""
    all_prices = [our_price] + list(opp_prices)
    n = len(all_prices)
    mean_all = sum(all_prices) / n
    lo, hi = mean_all * 0.5, mean_all * 2.0

    if sc.get("type") == "low_basis":
        points = float(sc.get("points", 10.0))
        second_low = sorted(all_prices)[1] if n >= 2 else all_prices[0]
        flagged = []
        for i, p in enumerate(all_prices):
            name = "我方" if i == 0 else f"对手{i}"
            if p < mean_all * 0.5 or p < second_low * 0.5 or (
                    ceiling and p < ceiling * 0.45):
                flagged.append(name)
        benchmark = min(all_prices)
        scores = {("我方" if i == 0 else f"对手{i}"): round(score_low_basis(p, benchmark, points), 2)
                  for i, p in enumerate(all_prices)}
        # 得分相同的，按投标报价由低到高排列（招标原文并列规则）
        order = sorted(scores.items(), key=lambda kv: (-kv[1], all_prices[0] if kv[0] == "我方" else 0))
        rank = [nm for nm, _ in order].index("我方") + 1
        return {
            "benchmark": round(benchmark, 2),
            "abnormal_low": round(mean_all * 0.5, 2),
            "abnormal_high": round(ceiling * 0.45, 2) if ceiling else round(mean_all * 2.0, 2),
            "our_score": scores["我方"],
            "rank": rank,
            "n": n,
            "top_score": order[0][1],
            "anomaly": "、".join(flagged),
        }

    def is_abnormal(p):
        return p < lo or p > hi

    # 评审价：异常价不纳入基准价计算，但参与价格评审（原文规则4）
    valid_for_bench = [p for p in all_prices if not is_abnormal(p)]
    benchmark = trimmed_mean(valid_for_bench)
    scores = {}
    for i, p in enumerate(all_prices):
        name = "我方" if i == 0 else f"对手{i}"
        scores[name] = round(score_vs_benchmark(
            p, benchmark, sc.get("above_k", 1.0), sc.get("below_k", 0.5), sc.get("base", 50.0)), 2)
    order = sorted(scores.items(), key=lambda kv: -kv[1])
    rank = [nm for nm, _ in order].index("我方") + 1
    return {
        "benchmark": round(benchmark, 2),
        "abnormal_low": round(lo, 2),
        "abnormal_high": round(hi, 2),
        "our_score": scores["我方"],
        "rank": rank,
        "n": n,
        "top_score": order[0][1],
        "anomaly": "",
    }


# ----------------------------------------------------------------- matrix ---
def build_matrix(our_axis, opp_axis, sc):
    M = np.zeros((len(opp_axis), len(our_axis)))
    for i, x in enumerate(opp_axis):          # 对手折扣 = 基准价代理
        for j, y in enumerate(our_axis):      # 我方折扣
            M[i, j] = score_generic(y, x, sc)
    return M


# ------------------------------------------------------------------ plots ---
def plot_heatmap(cfg, M, our_axis, opp_axis, out_path):
    t_lo, t_hi = cfg["target_interval"]
    c_lo = min(c["low"] for c in cfg["competitors"])
    c_hi = max(c["high"] for c in cfg["competitors"])

    fig, ax = plt.subplots(figsize=(14, 9))
    im = ax.imshow(M, origin="lower", cmap="RdYlGn", aspect="auto",
                   extent=[our_axis[-1], our_axis[0], opp_axis[0], opp_axis[-1]])
    dec = 2 if cfg.get("scoring", {}).get("type") == "low_basis" else 1

    for i, x in enumerate(opp_axis):
        for j, y in enumerate(our_axis):
            v = M[i, j]
            ax.text(y, x, f"{v:.{dec}f}", ha="center", va="center", fontsize=6.5,
                    color="black")

    # 对手报价区间（历史数据圈定）
    ax.add_patch(Rectangle((c_lo, opp_axis[0]), c_hi - c_lo, opp_axis[-1] - opp_axis[0],
                           fill=False, edgecolor="#1f77b4", lw=2.0, ls="--"))
    # 目标报价区间（我方）
    ax.add_patch(Rectangle((t_lo, opp_axis[0]), t_hi - t_lo, opp_axis[-1] - opp_axis[0],
                           fill=False, edgecolor="#d62728", lw=2.5))
    # 交集：最终圈定的报价窗口
    x0, x1 = max(t_lo, c_lo), min(t_hi, c_hi)
    ax.add_patch(Rectangle((x0, c_lo), x1 - x0, c_hi - c_lo,
                           facecolor="red", alpha=0.18, edgecolor="#d62728", lw=1.5))

    # 每个对手的折扣估计（打点，分4层错开避免标签重叠）
    span = opp_axis[-1] - opp_axis[0]
    for idx, c in enumerate(sorted(cfg["competitors"],
                                   key=lambda k: (k["low"] + k["high"]) / 2)):
        mid = (c["low"] + c["high"]) / 2
        lvl = idx % 4
        y_top = opp_axis[-1] + span * (0.035 + 0.045 * lvl)
        ax.plot([mid], [opp_axis[-1] + span * 0.035], marker="v", color="black", ms=6)
        ax.annotate(c["name"][:7], (mid, y_top), fontsize=6.5, ha="center")

    ax.set_xlabel("我方报价折扣率")
    ax.set_ylabel("对手报价折扣率（=基准价代理）")
    ax.set_title(f"折扣×折扣 得分矩阵（{cfg['project']} 报价区间测算图）\n"
                 "红框=目标区间 | 蓝虚框=对手历史折扣区间 | 红色阴影=最终圈定报价窗口", fontsize=12)
    ax.set_xticks(our_axis)
    ax.set_xticklabels([pct(v) for v in our_axis], rotation=45, fontsize=8)
    ax.set_yticks(opp_axis)
    ax.set_yticklabels([pct(v) for v in opp_axis], fontsize=8)
    pad = (our_axis[0] - our_axis[-1]) * 0.01
    ax.set_xlim(our_axis[-1] - pad, our_axis[0] + pad)
    ax.set_ylim(opp_axis[0] - pad, opp_axis[-1] + span * 0.30)
    fig.colorbar(im, label="我方价格得分")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_interval_funnel(cfg, optimal, out_path):
    steps = [
        ("① 基础区间\n(历史中标上限/行业底线)", cfg["base_interval"], "#4c78a8"),
        ("② 对手报价习惯验证\n(竞争对手历史折扣)", cfg["competitor_validate"], "#59a14f"),
        ("③ 收缩目标区间\n(甲方需求+评分风险+专家建议)", cfg["target_interval"], "#e15759"),
        ("④ 最优值锁定\n(得分模拟)", (optimal, optimal), "#f28e2b"),
    ]
    fig, ax = plt.subplots(figsize=(12, 5.5))
    for i, (label, (lo, hi), color) in enumerate(steps):
        y = len(steps) - i - 1
        if hi - lo < 1e-9:
            ax.plot([lo], [y], marker="D", color=color, ms=14, zorder=3)
            ax.annotate(pct(lo), (lo, y), textcoords="offset points",
                        xytext=(12, 6), fontsize=11, fontweight="bold", color=color)
        else:
            ax.add_patch(Rectangle((lo, y - 0.28), hi - lo, 0.56, color=color, alpha=0.75))
            ax.annotate(f"{pct(lo)}–{pct(hi)}", ((lo + hi) / 2, y), ha="center", va="center",
                        fontsize=11, fontweight="bold", color="white")
    ax.set_yticks(range(len(steps)))
    ax.set_yticklabels([s[0] for s in steps][::-1], fontsize=9)
    ax.set_xlabel("报价折扣率")
    ax.set_xlim(min(s[1][0] for s in steps) - 0.03, max(s[1][1] for s in steps) + 0.03)
    ax.set_ylim(-0.6, len(steps) - 0.4)
    ax.set_title("历史数据评估法：折扣率区间四步收敛过程", fontsize=12)
    ax.grid(axis="x", ls=":", alpha=0.5)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_simulation(candidates, scenarios, results, optimal, tie_set, out_path, prefer_low=True):
    """柱状图：每个候选折扣在各情景下的得分（分组柱）。"""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))
    width = 0.8 / len(scenarios)
    xs = np.arange(len(candidates))
    for si, sc in enumerate(scenarios):
        scores = [results[(c, sc["name"])]["our_score"] for c in candidates]
        ranks = [results[(c, sc["name"])]["rank"] for c in candidates]
        ax1.bar(xs + si * width - 0.4 + width / 2, scores, width,
                label=sc["name"], alpha=0.85)
        for xi, (s, r) in enumerate(zip(scores, ranks)):
            ax1.text(xi + si * width - 0.4 + width / 2, s + 0.1, f"第{r}名",
                     ha="center", fontsize=7, rotation=0)
    ax1.set_xticks(xs)
    ax1.set_xticklabels([pct(c) for c in candidates])
    ax1.set_ylabel("我方价格得分")
    ax1.set_title("候选折扣 × 情景 → 得分与排名", fontsize=11)
    ax1.legend(fontsize=8)
    ax1.grid(axis="y", ls=":", alpha=0.5)

    # 平均得分曲线（标注并列带与最终选定值）
    avg = [np.mean([results[(c, s["name"])]["our_score"] for s in scenarios])
           for c in candidates]
    xs_lab = [pct(c) for c in candidates]
    for idx, c in enumerate(candidates):
        if c in tie_set:
            ax2.axvspan(idx - 0.35, idx + 0.35, color="orange", alpha=0.12)
    ax2.plot(xs_lab, avg, marker="o", lw=2, color="#d62728")
    ax2.annotate(f"选定: {pct(optimal)}\n(并列带 {'/'.join(pct(c) for c in tie_set)} 内取{'偏低' if prefer_low else '偏高'})",
                 (xs_lab[candidates.index(optimal)], avg[candidates.index(optimal)]),
                 textcoords="offset points", xytext=(-60, -45),
                 fontsize=10, fontweight="bold", color="#d62728",
                 arrowprops=dict(arrowstyle="->", color="#d62728"))
    ax2.set_xlabel("候选折扣")
    ax2.set_ylabel("三情景平均得分")
    ax2.set_title("候选折扣平均得分曲线（并列带内按偏低偏好锁定最优值）", fontsize=11)
    ax2.grid(ls=":", alpha=0.5)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------- report ---
def write_matrix_csv(path, our_axis, opp_axis, M):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["对手\\我方"] + [pct(v) for v in our_axis])
        for i, x in enumerate(opp_axis):
            w.writerow([pct(x)] + [f"{M[i, j]:.2f}" for j in range(len(our_axis))])


def write_scenario_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["候选折扣", "情景", "基准价", "我方报价",
                                          "我方得分", "排名", "第一名得分", "家数", "异常低价"])
        w.writeheader()
        for r in rows:
            w.writerow(r)


def write_report(cfg, M, our_axis, opp_axis, results, candidates, avg_scores,
                 optimal, tie_set, out_path, deliverable_price):
    sc = cfg["scoring"]
    lines = []
    A = lines.append
    A(f"# {cfg['project']} —— 历史数据评估法报价测算报告\n")
    A(f"- 最高限价（合计）：**{cfg['ceiling_price']:,.2f} 元**")
    A(f"- 价格评分方法：{sc.get('method_text', '基准价法')}\n")

    A("## 一、评分方法原文依据\n")
    A("```\n" + sc.get("method_text", "").strip() + "\n```\n")
    if sc.get("type") == "low_basis":
        A(f"本报告按此公式实现：基准价=最低有效投标报价，我方得分 = 基准价 ÷ 我方报价 × "
          f"{sc.get('points', 10)} 分（价格满分 {sc.get('points', 10)} 分）；"
          f"{anomaly_desc(sc)}。\n")
    else:
        A(f"本报告按此公式实现：高于基准价按系数 {sc.get('above_k', 1)} 扣分、"
          f"低于基准价按系数 {sc.get('below_k', 0.5)} 扣分，基准价=有效报价去极值算术平均。\n")

    A("## 二、历史数据与折扣率证据（数据来源：中标公告/限价换算）\n")
    A("| 投标单位 | 历史折扣区间 | 估计报价 | 历史同类/近期同类证据 |")
    A("|---|---|---|---|")
    for c in cfg["competitors"]:
        ev = c.get("evidence", "").replace("\n", "；").replace("|", "／")
        A(f"| {c['name']} | {pct(c['low'])}–{pct(c['high'])} | {pct(c.get('bid', (c['low']+c['high'])/2))} | {ev[:120]} |")
    A("")
    A("> 折扣率估算原则：**近期同类报价优先于远期历史报价**；同一客户（如甘肃电信）的报价"
      "相对稳定可直接沿用；跨省份/客情弱地区按下修处理；不同时期报价有升/降趋势时按时间加权。\n")

    A("## 三、四步区间推导（推理链）\n")
    A(f"**第1步 定基础区间 {pct(cfg['base_interval'][0])}–{pct(cfg['base_interval'][1])}**："
      f"上限=价格上限锚（预算/限价硬约束或我方历史中标折扣），下限=行业锚"
      f"（同类项目中标折扣历史数据中未见低于 {pct(cfg['base_interval'][0])} 的案例）。\n")
    A(f"**第2步 对手报价习惯验证**：{len(cfg['competitors'])} 家参与/潜在单位近两年同类项目"
      f"中标折扣集中在 {pct(cfg['competitor_validate'][0])}–{pct(cfg['competitor_validate'][1])}，"
      f"与基础区间吻合，区间符合市场竞争常态。\n")
    A(f"**第3步 收缩至目标区间 {pct(cfg['target_interval'][0])}–{pct(cfg['target_interval'][1])}**："
      f"{cfg.get('narrow_reason', '甲方降本需求 + 高报价扣分风险更大 + 专家建议偏低报价') }。\n")
    bench_desc = ("基准价=最低有效报价" if sc.get("type") == "low_basis"
                  else "基准价=有效价去极值算术平均")
    A(f"**第4步 得分模拟锁定最优值 {pct(optimal)}**：对目标区间内候选折扣在"
      f"{len(cfg['scenarios'])} 个市场情景下全字段模拟（{bench_desc}，{anomaly_desc(sc)}）。"
      f"平均得分最高 {max(avg_scores.values()):.2f} 分，并列带（差距≤{cfg.get('tie_band', 0.3)} 分）内 "
      + "、".join(pct(c) for c in tie_set)
      + f" 内按{'偏低优先' if cfg.get('prefer_low', True) else '偏高优先'}取 **{pct(optimal)}**。\n")

    A("## 四、折扣×折扣得分矩阵（圈定报价区间）\n")
    A("热力图：`heatmap_折扣乘折扣.png`；数据：`matrix.csv`\n")
    cv = cfg["competitor_validate"]
    opp_in_cv = [x for x in opp_axis if cv[0] - 1e-9 <= x <= cv[1] + 1e-9]
    avg_row = {y: float(np.mean([score_generic(y, x, sc)
                                 for x in opp_in_cv])) for y in our_axis}
    top = sorted(avg_row.items(), key=lambda kv: -kv[1])[:5]
    cv = cfg["competitor_validate"]
    A(f"对手折扣 {pct(cv[0])}–{pct(cv[1])} 区间内各我方折扣的平均得分 Top5：\n")
    for y, v in top:
        A(f"- {pct(y)} → {v:.2f} 分")
    A("")

    A("## 五、候选折扣情景模拟（计算过程）\n")
    A("| 候选折扣 | 情景 | 我方报价(元) | 基准价(元) | 我方得分 | 排名 |")
    A("|---|---|---|---|---|---|")
    for c in candidates:
        for s in cfg["scenarios"]:
            r = results[(c, s["name"])]
            A(f"| {pct(c)} | {s['name']} | {c*cfg['ceiling_price']:,.2f} | "
              f"{r['benchmark']:,.2f} | {r['our_score']:.2f} | 第{r['rank']}/{r['n']} |")
    A("")

    A("## 六、结论\n")
    A(f"| 项目 | 结果 |")
    A(f"|---|---|")
    A(f"| 基础区间 | {pct(cfg['base_interval'][0])} – {pct(cfg['base_interval'][1])} |")
    A(f"| 目标区间 | {pct(cfg['target_interval'][0])} – {pct(cfg['target_interval'][1])} |")
    A(f"| **目标报价折扣率** | **{pct(optimal)}** |")
    A(f"| **目标报价金额** | **{deliverable_price:,.2f} 元**（= 限价 {cfg['ceiling_price']:,.2f} × {pct(optimal)}） |")
    A(f"| 三情景平均得分 | {avg_scores[optimal]:.2f} 分 |")
    avg_rank = float(np.mean([results[(optimal, s["name"])]["rank"] for s in cfg["scenarios"]]))
    A(f"| 三情景平均排名 | 第 {avg_rank:.1f} 名 |")
    A(f"| 统计并列带 | {'、'.join(pct(c) for c in tie_set)}（差异≤{cfg.get('tie_band', 0.3)} 分） |")
    A(f"| 图表 | heatmap_折扣乘折扣.png / interval_折扣区间收敛.png / simulation_候选折扣得分.png |")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ------------------------------------------------------------------ main ---
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.input, encoding="utf-8") as f:
        cfg = json.load(f)
    os.makedirs(args.out, exist_ok=True)

    step = cfg.get("axis_step", 0.01)
    our_axis = np.round(np.arange(cfg["our_range"][0], cfg["our_range"][1] + 1e-9, step), 4)
    opp_axis = np.round(np.arange(cfg["opp_range"][0], cfg["opp_range"][1] + 1e-9, step), 4)

    M = build_matrix(our_axis, opp_axis, cfg["scoring"])
    write_matrix_csv(os.path.join(args.out, "matrix.csv"), our_axis, opp_axis, M)
    plot_heatmap(cfg, M, our_axis, opp_axis,
                 os.path.join(args.out, "heatmap_折扣乘折扣.png"))

    # 情景模拟
    candidates = cfg["candidates"]
    results, rows = {}, []
    for c in candidates:
        our_price = round(c * cfg["ceiling_price"], 2)
        for s in cfg["scenarios"]:
            opp_prices = [round((comp.get("bid", (comp["low"] + comp["high"]) / 2)
                                 + s["shift"]) * cfg["ceiling_price"], 2)
                          for comp in cfg["competitors"]]
            r = evaluate_field(our_price, opp_prices, cfg["scoring"],
                               ceiling=cfg["ceiling_price"])
            results[(c, s["name"])] = r
            rows.append({"候选折扣": pct(c), "情景": s["name"],
                         "基准价": r["benchmark"], "我方报价": our_price,
                         "我方得分": r["our_score"], "排名": f"{r['rank']}/{r['n']}",
                         "第一名得分": r["top_score"], "家数": r["n"],
                         "异常低价": r.get("anomaly", "")})
    write_scenario_csv(os.path.join(args.out, "scenario_tables.csv"), rows)

    avg_scores = {c: float(np.mean([results[(c, s["name"])]["our_score"]
                                    for s in cfg["scenarios"]]))
                  for c in candidates}
    # 并列带选择规则：与最高平均分差 ≤ tie_band 的候选视为统计并列；
    # prefer_low=True（默认，源于高于基准价扣分系数更大 + 甲方降本偏好）时取并列带内最低折扣。
    tie_band = cfg.get("tie_band", 0.3)
    best = max(avg_scores.values())
    tie_set = sorted([c for c in candidates if best - avg_scores[c] <= tie_band])
    if cfg.get("prefer_low", True):
        optimal = tie_set[0]
    else:
        optimal = tie_set[-1]
    price = round(optimal * cfg["ceiling_price"], 2)

    plot_interval_funnel(cfg, optimal, os.path.join(args.out, "interval_折扣区间收敛.png"))
    plot_simulation(candidates, cfg["scenarios"], results, optimal, tie_set,
                    os.path.join(args.out, "simulation_候选折扣得分.png"),
                    prefer_low=cfg.get("prefer_low", True))
    write_report(cfg, M, our_axis, opp_axis, results, candidates, avg_scores,
                 optimal, tie_set, os.path.join(args.out, "report.md"), price)

    # 结构化结果（供 render_report.py / render_infographic.py 渲染手机报告）
    cv = cfg["competitor_validate"]
    opp_in_cv = [x for x in opp_axis if cv[0] - 1e-9 <= x <= cv[1] + 1e-9]
    matrix_top = sorted(
        ({"discount": float(y),
          "avg": float(np.mean([score_generic(y, x, cfg["scoring"])
                                for x in opp_in_cv]))}
         for y in our_axis), key=lambda d: -d["avg"])[:5]
    avg_ranks = {f"{c:.2f}": float(np.mean(
        [results[(c, s["name"])]["rank"] for s in cfg["scenarios"]]))
        for c in candidates}
    result = {
        "ok": True,
        "project": cfg["project"],
        "ceiling_price": cfg["ceiling_price"],
        "scoring": cfg["scoring"],
        "axis": {"lo": min(cfg["our_range"][0], cfg["opp_range"][0]),
                 "hi": max(cfg["our_range"][1], cfg["opp_range"][1])},
        "axis_step": step,
        "base_interval": cfg["base_interval"],
        "competitor_validate": cv,
        "target_interval": cfg["target_interval"],
        "narrow_reason": cfg.get("narrow_reason", ""),
        "tie_band": tie_band,
        "prefer_low": cfg.get("prefer_low", True),
        "optimal": optimal,
        "optimal_price": price,
        "tie_set": tie_set,
        "avg_score": round(avg_scores[optimal], 2),
        "avg_rank": round(avg_ranks[f"{optimal:.2f}"], 1),
        "competitors": cfg["competitors"],
        "scenarios": cfg["scenarios"],
        "candidates": candidates,
        "simulation": rows,
        "avg_scores": {f"{c:.2f}": round(avg_scores[c], 2) for c in candidates},
        "avg_ranks": avg_ranks,
        "matrix_top": matrix_top,
        "inputs_file": os.path.abspath(args.input),
    }
    with open(os.path.join(args.out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "ok": True,
        "optimal_discount": pct(optimal),
        "target_price": price,
        "avg_score": round(avg_scores[optimal], 2),
        "tie_set": [pct(c) for c in tie_set],
        "outputs": sorted(os.listdir(args.out)),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())
