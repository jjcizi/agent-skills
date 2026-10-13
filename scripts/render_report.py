#!/usr/bin/env python3
"""bid-price-calc 手机版式报告 PDF（HTML 模板 + Playwright 打印）。

用法:
  python render_report.py --result result.json --output 报价测算报告.pdf \
      [--meta meta.json] [--html debug.html]

设计稿 414×896px（手机一屏比例），单栏卡片式排版；
报告中的概率分布图为 HTML/CSS 原生绘制，与报告同风格、全文仅此一图。

meta.json 额外可选字段:
  "sensitivity": [{"n":"4家","branch":"全平均","mean":165635,"low":163317,"high":167953,"main":true}, ...]
  "limits": ["限制1", "限制2"]   # 缺省用通用限制三条
  "mean_hit": 38.5               # 胜出报价参考值的条件命中概率(%)，首屏必展示（Step 4b 的参考值 fixedBid 运行）
  "rule_formula": "评标基准价 = 最低有效投标报价"
  "scoring_formula": "价格得分 = 评标基准价 ÷ 投标报价 × 10"
                                 # 招标文件原文公式，写进"报价方法识别"章节
"""
import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path
from string import Template


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def zone_color(p: float, rz: dict) -> str:
    lo, lo_u = rz.get("lowRiskLower"), rz.get("lowRiskUpper")
    md, md_u = rz.get("mediumRiskLower"), rz.get("mediumRiskUpper")
    hi, hi_u = rz.get("highRiskLower"), rz.get("highRiskUpper")
    if lo is None:
        return "#CBD5E1"
    if lo <= p <= lo_u:
        return "#10B981"
    if md is not None and (md <= p < lo or lo_u < p <= md_u):
        return "#FBBF24"
    if hi is not None and (hi <= p < md or md_u < p <= hi_u):
        return "#F87171"
    return "#CBD5E1"


def fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    return f"{v:,}" if isinstance(v, (int, float)) else str(v)


def fmt_mean(v) -> str:
    if v is None:
        return "—"
    return f"{v:,.0f}" if abs(v) >= 10000 else f"{v:.2f}"


def fmt_int(v) -> str:
    """整数/一位小数的千分位显示"""
    if v is None:
        return "—"
    if isinstance(v, float) and not v.is_integer():
        return f"{v:,.1f}"
    return f"{float(v):,.0f}"


def build(result: dict, meta: dict, template_path: Path) -> str:
    if not result.get("ok"):
        raise SystemExit(f"结果 ok=false，无法出报告: {result.get('error', '')}")
    hist = result.get("histogram") or {}
    probs = hist.get("probabilities") or []
    rz = hist.get("riskZones") or {}
    if not probs or not rz:
        raise SystemExit("结果缺少 histogram / riskZones")

    min_price = hist.get("minPrice", 0)
    prices = [min_price + i for i in range(len(probs))]
    mean = result.get("winningMean")
    applied = result.get("applied") or {}
    unit = result.get("unitLabel") or "万元"
    sims = result.get("simulations", "")
    seed = result.get("seed")

    lo_l, lo_u = rz["lowRiskLower"], rz["lowRiskUpper"]
    md_l, md_u = rz["mediumRiskLower"], rz["mediumRiskUpper"]
    hi_l, hi_u = rz["highRiskLower"], rz["highRiskUpper"]
    span_l, span_h = hi_l, hi_u
    span = max(float(span_h - span_l), 1e-6)

    def pin(v: float) -> float:
        return max(0.0, min(100.0, (v - span_l) / span * 100))

    seg = {
        "seg_hl": pin(md_l) - pin(hi_l),
        "seg_ml": pin(lo_l) - pin(md_l),
        "seg_low": pin(lo_u) - pin(lo_l),
        "seg_mr": pin(md_u) - pin(lo_u),
        "seg_hr": pin(hi_u) - pin(md_u),
    }
    seg = {k: f"{max(v, 0.0):.3f}" for k, v in seg.items()}

    # 直方图：裁全零尾 ±2，降采样到 ≤90 根（414px 窄幅）
    nz = [i for i, p in enumerate(probs) if p > 1e-9]
    if nz:
        i0, i1 = max(0, nz[0] - 2), min(len(probs) - 1, nz[-1] + 2)
    else:
        i0, i1 = 0, len(probs) - 1
    view, view_prices = probs[i0:i1 + 1], prices[i0:i1 + 1]
    p_lo, p_hi = view_prices[0], view_prices[-1]
    if len(view) > 90:
        g = math.ceil(len(view) / 90)
        gp, gv = [], []
        for i in range(0, len(view), g):
            chunk = view[i:i + g]
            gp.append(view_prices[i] + (len(chunk) - 1) / 2)
            gv.append(sum(chunk))
        view_prices, view = gp, gv
    vmax = max(view) or 1.0
    bars = "".join(
        '<div class="bar zero"></div>' if p <= 1e-9 else
        f'<div class="bar" style="height:{p / vmax * 100:.2f}%;background:{zone_color(price, rz)}"></div>'
        for p, price in zip(view, view_prices)
    )
    mean_line = max(0.0, min(100.0, (mean - p_lo) / max(p_hi - p_lo, 1e-6) * 100)) if mean else 50.0

    # 参数
    def num(key, default=None):
        try:
            return float(applied.get(key, default))
        except (TypeError, ValueError):
            return None

    ceiling = num("ceilingPrice")
    max_p, min_p = num("maxPrice"), num("minPrice")
    target_width = round(lo_u - lo_l, 1)
    target_pct = f"{target_width / ceiling * 100:.1f}" if ceiling else "—"

    # 报价相对招标控制价的折扣率（占控制价百分比）
    def to_float(v):
        try:
            return float(str(v).replace(",", ""))
        except (TypeError, ValueError):
            return None

    def disc(v) -> str:
        """v 相当于控制价的百分比；无法计算返回 '—'"""
        fv = to_float(v)
        if not ceiling or fv is None:
            return "—"
        return f"{fv / ceiling * 100:.1f}%"

    target_disc = f"{disc(lo_l)} – {disc(lo_u)}" if ceiling else "—"

    # meta 兜底
    project = meta.get("project") or "投标报价测算"
    date = meta.get("date") or dt.date.today().isoformat()
    rule_label = meta.get("rule_label") or applied.get("benchmarkRule", "—")
    rule_key = applied.get("benchmarkRule", "—")
    scoring_label = meta.get("scoring_label") or applied.get("scoringRule", "—")
    scoring_key = applied.get("scoringRule", "—")
    primary = meta.get("suggest_primary") or fmt_mean(mean)
    secondary = meta.get("suggest_secondary") or str((lo_l + lo_u) // 2)
    ph = meta.get("suggest_primary_hit")
    sh = meta.get("suggest_secondary_hit")
    primary_hit_line = f'<br><span class="hit">命中概率 {float(ph):.1f}%</span>' if ph is not None else ""
    secondary_hit_line = f'<br><span class="hit">命中概率 {float(sh):.1f}%</span>' if sh is not None else ""
    note = meta.get("suggest_note") or (
        f"建议在 {lo_l}–{lo_u} {unit} 目标带内结合成本底线选点。")
    params_note = meta.get("params_note") or "标书未写明，采用默认随机池"

    # 首选/备选报价相对控制价的折扣率
    primary_disc = disc(primary)
    secondary_disc = disc(secondary)

    # 首屏：参考值命中概率（meta.mean_hit，来自参考值的 fixedBid 条件仿真）
    mh = meta.get("mean_hit")
    mean_hit_line = (
        f'<span class="hit-badge">命中概率 {float(mh):.1f}%</span>'
        if mh is not None else ""
    )
    mean_hit_sub = (
        f'固定该报价的条件仿真命中率 {float(mh):.1f}%'
        if mh is not None else
        "命中概率未测算（需按参考值补跑条件仿真）"
    )

    # 首屏三张 KPI 的副文案（折扣率 + 命中概率）
    kpi1_sub = f"胜出报价均值 ± 0.5σ · 占控制价 {target_disc} · 带宽 {target_pct}% 控制价"
    kpi2_sub = f"{sims} 次模拟最高分报价的均值 · 占控制价 {disc(mean)} · {mean_hit_sub}"
    kpi3_bits = []
    if ph is not None:
        kpi3_bits.append(f"首选命中 {float(ph):.1f}%")
    if sh is not None:
        kpi3_bits.append(f"备选命中 {float(sh):.1f}%")
    kpi3_bits.append(f"≈ 控制价的 {primary_disc} / {secondary_disc}")
    kpi3_sub = " · ".join(kpi3_bits)

    # 报价建议区：折扣率行
    primary_disc_line = f'<br><span class="dr">≈ 控制价的 {primary_disc}</span>'
    secondary_disc_line = f'<br><span class="dr">≈ 控制价的 {secondary_disc}</span>'

    # 招标文件原文公式（报价测算法）
    rule_formula = meta.get("rule_formula") or "（meta.json 缺 rule_formula：请补招标文件基准价原文公式）"
    scoring_formula = meta.get("scoring_formula") or "（meta.json 缺 scoring_formula：请补招标文件算分原文公式）"

    limits = meta.get("limits") or [
        "仅模拟价格维度得分；商务/技术/服务等非价格分未纳入，最终排序需结合非价格项评估。",
        "模拟报价区间与家数为估计值，是最敏感的输入；获得历史成交价或对手情报后应更新重算。",
        "评审口径以标书为准（如不含税报价），换算数字仅供内部决策参考。",
    ]
    limits_items = "".join(f"<li>{x}</li>" for x in limits)

    sens = meta.get("sensitivity")
    if sens:
        rows = []
        for s in sens:
            cls = ' class="sens-row main"' if s.get("main") else ' class="sens-row"'
            rows.append(
                f'<div{cls}><span class="sens-n num">{s.get("n", "—")}</span>'
                f'<span style="color:var(--faint);font-size:11px">{s.get("branch", "")}</span>'
                f'<span class="sens-band"><b class="num">{fmt_int(s.get("low"))}–{fmt_int(s.get("high"))}</b>'
                f'<span>参考值 {fmt_mean(s.get("mean"))} {unit}</span></span></div>'
            )
        sensitivity_block = (
            '<div class="sec keep"><div class="sec-head"><span class="idx">04</span>'
            '<h2>家数敏感性</h2></div><div class="sens">' + "".join(rows) +
            f'</div><div class="sens-note">{meta.get("sensitivity_note", "")}</div></div>'
        )
        advice_idx = "05"
        limits_idx = "06"
    else:
        sensitivity_block = ""
        advice_idx = "04"
        limits_idx = "05"

    mean_s = fmt_mean(mean)
    mean_fs = "40" if len(mean_s.replace(",", "")) <= 9 else "30"

    values = {
        "project": project, "date": date, "unit": unit,
        "simulations": str(sims), "seed": str(seed if seed is not None else "—"),
        "rule_label": rule_label, "rule_key": rule_key,
        "scoring_label": scoring_label, "scoring_key": scoring_key,
        "ceiling": fmt(ceiling), "participants": str(applied.get("participantCount", "—")),
        "mean": mean_s, "mean_fs": mean_fs,
        "target_low": fmt_int(lo_l), "target_high": fmt_int(lo_u),
        "target_width": fmt_int(target_width), "target_pct": target_pct,
        "target_disc": target_disc, "mean_hit_line": mean_hit_line,
        "kpi1_sub": kpi1_sub, "kpi2_sub": kpi2_sub, "kpi3_sub": kpi3_sub,
        "primary_disc_line": primary_disc_line, "secondary_disc_line": secondary_disc_line,
        "rule_formula": rule_formula, "scoring_formula": scoring_formula,
        "low_span": f"{fmt_int(lo_l)}–{fmt_int(lo_u)}",
        "medium_span": f"{fmt_int(md_l)}–{fmt_int(md_u)}",
        "high_span": f"{fmt_int(hi_l)}–{fmt_int(hi_u)}",
        "seg_hl": seg["seg_hl"], "seg_ml": seg["seg_ml"], "seg_low": seg["seg_low"],
        "seg_mr": seg["seg_mr"], "seg_hr": seg["seg_hr"],
        "mean_pin": f"{pin(mean):.2f}" if mean else "50",
        "mean_line": f"{mean_line:.2f}",
        "bars": bars,
        "axis_min": f"{p_lo:,.0f}", "axis_mid": f"{(p_lo + p_hi) // 2:,.0f}",
        "axis_max": f"{p_hi:,.0f}",
        "bid_range": f"{fmt_mean(min_p)} – {fmt_mean(max_p)}" if (max_p and min_p) else "—",
        "params_note": params_note,
        "rule_evidence": meta.get("rule_evidence") or "（未提供识别依据，请补 meta.json）",
        "scoring_evidence": meta.get("scoring_evidence") or "（未提供识别依据）",
        "suggest_primary": str(primary), "suggest_secondary": str(secondary),
        "primary_hit_line": primary_hit_line, "secondary_hit_line": secondary_hit_line,
        "suggest_note": note,
        "sensitivity_block": sensitivity_block,
        "limits_items": limits_items,
    }
    tpl_text = template_path.read_text(encoding="utf-8").replace("万元", "${unit}")
    # 章节序号联动（敏感性存在时建议/限制顺延）
    tpl_text = (tpl_text.replace('<span class="idx">04</span><h2>报价建议</h2>',
                                  f'<span class="idx">{advice_idx}</span><h2>报价建议</h2>')
                        .replace('<span class="idx">05</span><h2>限制与声明</h2>',
                                  f'<span class="idx">{limits_idx}</span><h2>限制与声明</h2>'))
    return Template(tpl_text).safe_substitute(values)


def to_pdf(html: str, output: str, html_out: str | None) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: 需要 python playwright 才能生成 PDF", file=sys.stderr)
        sys.exit(3)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    if html_out:
        Path(html_out).write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_viewport_size({"width": 414, "height": 896})
        page.set_content(html, wait_until="load")
        page.wait_for_timeout(200)
        page.pdf(
            path=str(out),
            width="414px", height="896px",
            print_background=True,
            prefer_css_page_size=True,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
        )
        browser.close()
    print(str(out))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--meta", default=None)
    ap.add_argument("--template", default=None)
    ap.add_argument("--html", default=None, help="同时保留中间 HTML（调试用）")
    args = ap.parse_args()

    result = load_json(args.result)
    meta = load_json(args.meta) if args.meta else {}
    template = Path(args.template) if args.template else (
        Path(__file__).resolve().parent.parent / "assets" / "report_page_template.html"
    )
    if not template.exists():
        raise SystemExit(f"模板不存在: {template}")
    html = build(result, meta, template)
    to_pdf(html, args.output, args.html)


if __name__ == "__main__":
    main()
