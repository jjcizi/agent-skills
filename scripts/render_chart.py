#!/usr/bin/env python3
"""bid-price-calc 概率直方图渲染（PNG）。

用法:
  python render_chart.py --result result.json --output chart.png [--title 标题]

输入 result.json 为 run_calc.js 的输出，取 histogram.probabilities /
histogram.minPrice / histogram.riskZones / winningMean / targetRange。
"""
import argparse
import json
import sys


def load_result(path: str) -> dict:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def build_chart(result: dict, output: str, title: str | None) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.patches import Patch

    # 中文字体
    for name in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "PingFang SC"):
        if any(name.lower() in f.name.lower() for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.sans-serif"] = [name]
            break
    plt.rcParams["axes.unicode_minus"] = False

    hist = result.get("histogram") or {}
    probs = hist.get("probabilities") or []
    min_price = hist.get("minPrice", 0)
    if not probs:
        raise SystemExit("结果中没有 histogram.probabilities，无法绘图")
    unit = result.get("unitLabel") or "万元"

    prices = [min_price + i for i in range(len(probs))]
    rz = hist.get("riskZones") or {}
    low_l, low_u = rz.get("lowRiskLower"), rz.get("lowRiskUpper")
    med_l, med_u = rz.get("mediumRiskLower"), rz.get("mediumRiskUpper")
    high_l, high_u = rz.get("highRiskLower"), rz.get("highRiskUpper")

    C_LOW, C_MED, C_HIGH, C_OUT = "#06D6A0", "#FFD166", "#FF6B6B", "#D9D9D9"

    def zone_color(p: float) -> str:
        if low_l is not None and low_l <= p <= low_u:
            return C_LOW
        if med_l is not None and (med_l <= p < low_l or low_u < p <= med_u):
            return C_MED
        if high_l is not None and (high_l <= p < med_l or med_u < p <= high_u):
            return C_HIGH
        return C_OUT

    # 裁掉全零尾部（两侧留 2 档），再分组降采样到 ≤400 根柱
    nz = [i for i, p in enumerate(probs) if p > 1e-9]
    if nz:
        i0, i1 = max(0, nz[0] - 2), min(len(probs) - 1, nz[-1] + 2)
    else:
        i0, i1 = 0, len(probs) - 1
    view, view_prices = probs[i0:i1 + 1], prices[i0:i1 + 1]
    if len(view) > 400:
        import math
        g = math.ceil(len(view) / 400)
        gp, gv = [], []
        for i in range(0, len(view), g):
            chunk = view[i:i + g]
            gp.append(view_prices[i] + (len(chunk) - 1) / 2)
            gv.append(sum(chunk))
        view_prices, view = gp, gv
    prices, probs = view_prices, view
    colors = [zone_color(p) for p in prices]
    step = (prices[-1] - prices[0]) / max(len(prices) - 1, 1) if len(prices) > 1 else 1.0
    bar_w = max(step * 0.9, 0.5)

    fig, ax = plt.subplots(figsize=(13, 6.2), dpi=150)
    ax.bar(prices, probs, width=bar_w, color=colors, edgecolor="none", zorder=3)

    # 低风险区间背景
    if low_l is not None:
        ax.axvspan(low_l, low_u, color=C_LOW, alpha=0.12, zorder=1)
    if med_l is not None:
        ax.axvspan(med_l, low_l, color=C_MED, alpha=0.08, zorder=1)
        ax.axvspan(low_u, med_u, color=C_MED, alpha=0.08, zorder=1)

    mean = result.get("winningMean")
    if mean is not None:
        ax.axvline(mean, color="#0D47A1", linestyle="--", linewidth=1.6, zorder=4)
        ax.annotate(
            f"胜出报价参考值 {mean:,.0f} {unit}" if abs(mean) >= 10000 else f"胜出报价参考值 {mean:.2f} {unit}",
            xy=(mean, max(probs) * 0.95),
            xytext=(8, 0), textcoords="offset points",
            color="#0D47A1", fontsize=10, fontweight="bold", va="top",
        )

    ax.set_xlabel(f"报价（{unit}）", fontsize=11)
    ax.set_ylabel("胜出概率（%）", fontsize=11)
    n = result.get("simulations", "")
    rule = title or result.get("ruleLabel") or result.get("ruleKey") or "投标报价概率模拟"
    ax.set_title(f"{rule}  ·  蒙特卡洛模拟 {n} 次", fontsize=13, fontweight="bold", pad=12)

    # 图例
    handles = [
        Patch(color=C_LOW, label=f"低风险（目标带）{low_l}-{low_u} {unit}" if low_l is not None else "低风险"),
        Patch(color=C_MED, label="中风险" + (f" ±1σ" if med_l is not None else "")),
        Patch(color=C_HIGH, label="高风险" + (f" ±1.5σ" if high_l is not None else "")),
        Patch(color=C_OUT, label="区间外"),
    ]
    ax.legend(handles=handles, loc="upper right", framealpha=0.9, fontsize=9)

    ax.set_xlim(prices[0] - step, prices[-1] + step)
    ax.set_ylim(0, max(probs) * 1.18 if max(probs) > 0 else 1)
    ax.grid(axis="y", linestyle=":", alpha=0.4, zorder=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.text(
        0.01, 0.01,
        "蒙特卡洛模拟结果，仅供报价决策参考，不构成中标承诺。"
        "最终报价请结合成本、对手情报与风险偏好在目标带内选点。",
        fontsize=8.5, color="#666666",
    )
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True, help="run_calc.js 输出的 JSON")
    ap.add_argument("--output", required=True, help="PNG 输出路径")
    ap.add_argument("--title", default=None, help="图表标题（规则名）")
    args = ap.parse_args()

    result = load_result(args.result)
    if not result.get("ok", False):
        print(f"结果 ok=false，跳过绘图: {result.get('error', '')}", file=sys.stderr)
        sys.exit(2)
    build_chart(result, args.output, args.title)
    print(args.output)


if __name__ == "__main__":
    main()
