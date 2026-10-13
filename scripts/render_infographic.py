#!/usr/bin/env python3
"""bid-price-calc 高级信息图渲染（HTML 模板 + Playwright 截图 → PNG）。

用法:
  python render_infographic.py --result result.json --output infographic.png \
      [--meta meta.json] [--template assets/report_template.html]

meta.json（可选，由 agent 填写，缺失时用兜底值）:
{
  "project": "项目名称",
  "date": "2026-01-01",
  "rule_label": "ABC值法", "rule_evidence": "评标办法3.2：…（P28）",
  "scoring_label": "偏差率插入法", "scoring_evidence": "…",
  "suggest_primary": "1126", "suggest_secondary": "1130",
  "suggest_note": "…", "params_note": "K∈默认池"
}
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from string import Template

GREEN, YELLOW, RED = "#10B981", "#FBBF24", "#F87171"
OUT = "#CBD5E1"  # 区间外（浅色主题）


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def zone_color(p: float, rz: dict) -> str:
    lo, lo_u = rz.get("lowRiskLower"), rz.get("lowRiskUpper")
    md, md_u = rz.get("mediumRiskLower"), rz.get("mediumRiskUpper")
    hi, hi_u = rz.get("highRiskLower"), rz.get("highRiskUpper")
    if lo is None:
        return OUT
    if lo <= p <= lo_u:
        return GREEN
    if md is not None and (md <= p < lo or lo_u < p <= md_u):
        return YELLOW
    if hi is not None and (hi <= p < md or md_u < p <= hi_u):
        return RED
    return OUT


def fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.2f}".rstrip("0").rstrip(".")
    return str(v)


def build(result: dict, meta: dict, template_path: Path) -> str:
    if not result.get("ok"):
        raise SystemExit(f"结果 ok=false，无法出图: {result.get('error', '')}")
    hist = result.get("histogram") or {}
    probs = hist.get("probabilities") or []
    rz = hist.get("riskZones") or {}
    if not probs or not rz:
        raise SystemExit("结果缺少 histogram / riskZones，无法出图")

    min_price = hist.get("minPrice", 0)
    prices = [min_price + i for i in range(len(probs))]
    mean = result.get("winningMean")
    applied = result.get("applied") or {}
    seed = result.get("seed")
    sims = result.get("simulations", "")

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
    seg = {k: max(v, 0.0) for k, v in seg.items()}

    # 标尺刻度
    ticks = [
        (hi_l, ""), (md_l, ""), (lo_l, "low"),
        (lo_u, "low"), (md_u, ""), (hi_u, ""),
    ]
    labels, last_x = [], None
    for v, cls in ticks:
        x = pin(v)
        if last_x is not None and x - last_x < 7:
            continue
        last_x = x
        labels.append(
            f'<span class="t {cls}" style="left:{x:.2f}%"><b class="num">{fmt(v)}</b></span>'
        )
    ruler_labels = "".join(labels)

    # 直方图（裁掉全零尾部，两侧各留 2 档；分组降采样到 ≤150 根柱）
    nz = [i for i, p in enumerate(probs) if p > 1e-9]
    if nz:
        i0 = max(0, nz[0] - 2)
        i1 = min(len(probs) - 1, nz[-1] + 2)
    else:
        i0, i1 = 0, len(probs) - 1
    view = probs[i0:i1 + 1]
    view_prices = prices[i0:i1 + 1]
    p_lo, p_hi = view_prices[0], view_prices[-1]

    if len(view) > 150:
        import math
        g = math.ceil(len(view) / 150)
        gp, gv = [], []
        for i in range(0, len(view), g):
            chunk = view[i:i + g]
            gp.append(view_prices[i] + (len(chunk) - 1) / 2)
            gv.append(sum(chunk))
        view_prices, view = gp, gv

    vmax = max(view) or 1.0
    bars = []
    for p, price in zip(view, view_prices):
        h = p / vmax * 100
        color = zone_color(price, rz)
        if p <= 1e-9:
            bars.append('<div class="bar zero"></div>')
        else:
            bars.append(f'<div class="bar" style="height:{h:.2f}%;background:{color}"></div>')
    bars_html = "".join(bars)
    p_span = max(p_hi - p_lo, 1e-6)
    mean_line = max(0.0, min(100.0, (mean - p_lo) / p_span * 100)) if mean else 50.0

    # 参数
    def num(key, default=None):
        try:
            return float(applied.get(key, default))
        except (TypeError, ValueError):
            return None

    ceiling = num("ceilingPrice")
    max_p, min_p = num("maxPrice"), num("minPrice")
    participants = applied.get("participantCount", "—")
    bid_range = f"{fmt(min_p)} – {fmt(max_p)}" if (max_p and min_p) else "—"
    dist_center = fmt((max_p + min_p) / 2) if (max_p and min_p) else "—"
    target_width = round(lo_u - lo_l, 1)
    target_pct = f"{target_width / ceiling * 100:.1f}" if ceiling else "—"

    low_span = f"{lo_l:,}–{lo_u:,}"
    med_span = f"{md_l:,}–{md_u:,}"
    high_span = f"{hi_l:,}–{hi_u:,}"

    # meta 兜底
    today = dt.date.today().isoformat()
    project = meta.get("project") or "投标报价测算"
    date = meta.get("date") or today
    rule_label = meta.get("rule_label") or result.get("ruleKey") or applied.get("benchmarkRule", "—")
    rule_key = applied.get("benchmarkRule", "—")
    scoring_label = meta.get("scoring_label") or applied.get("scoringRule", "—")
    scoring_key = applied.get("scoringRule", "—")
    rule_ev = meta.get("rule_evidence") or "（未提供识别依据，请在报告中标注原文出处）"
    scoring_ev = meta.get("scoring_evidence") or "（未提供识别依据）"
    primary = meta.get("suggest_primary") or (f"{mean:.0f}" if mean else "—")
    secondary = meta.get("suggest_secondary") or f"{(lo_l + lo_u) // 2}"
    ph = meta.get("suggest_primary_hit")
    sh = meta.get("suggest_secondary_hit")
    primary_hit_line = f'<br><span class="hit">命中概率 {float(ph):.1f}%</span>' if ph is not None else ""
    secondary_hit_line = f'<br><span class="hit">命中概率 {float(sh):.1f}%</span>' if sh is not None else ""

    # 报价占招标控制价的折扣率
    def _f(v):
        try:
            return float(str(v).replace(",", ""))
        except (TypeError, ValueError):
            return None

    def disc(v) -> str:
        fv, _c = _f(v), ceiling
        if not _c or fv is None:
            return ""
        return f"{fv / _c * 100:.1f}%"

    _pd, _sd = disc(primary), disc(secondary)
    primary_disc_line = f'<br><span class="dr">占控制价 {_pd}</span>' if _pd else ""
    secondary_disc_line = f'<br><span class="dr">占控制价 {_sd}</span>' if _sd else ""
    note = meta.get("suggest_note") or (
        f"建议在 {low_span} {unit} 目标带内结合成本底线选点；"
        "中风险带可博利润，高风险带明显偏离模拟最优。"
    )
    params_note = meta.get("params_note") or "标书未写明，采用默认随机池"

    unit = result.get("unitLabel") or "万元"
    mean_s = (f"{mean:,.0f}" if abs(mean) >= 10000 else f"{mean:.2f}") if mean else "—"
    range_s = f"{lo_l} — {lo_u}"
    mean_fs = 54 if len(mean_s.replace(",", "")) <= 9 else 40
    range_fs = 44 if len(range_s) <= 13 else 34

    values = {
        "project": project, "date": date,
        "unit": unit,
        "mean": mean_s,
        "mean_fs": str(mean_fs), "range_fs": str(range_fs),
        "target_low": f"{lo_l:,}", "target_high": f"{lo_u:,}",
        "target_width": f"{target_width:,.0f}", "target_pct": target_pct,
        "medium_span": med_span, "high_span": high_span, "low_span": low_span,
        "simulations": str(sims), "seed": str(seed if seed is not None else "—"),
        "ceiling": fmt(ceiling), "participants": str(participants),
        "bid_range": bid_range, "dist_center": dist_center,
        "rule_label": rule_label, "rule_key": rule_key, "rule_evidence": rule_ev,
        "scoring_label": scoring_label, "scoring_key": scoring_key, "scoring_evidence": scoring_ev,
        "suggest_primary": str(primary), "suggest_secondary": str(secondary),
        "primary_hit_line": primary_hit_line, "secondary_hit_line": secondary_hit_line,
        "primary_disc_line": primary_disc_line, "secondary_disc_line": secondary_disc_line,
        "suggest_note": note, "params_note": params_note,
        "bars": bars_html, "ruler_labels": ruler_labels,
        "mean_pin": f"{pin(mean):.2f}" if mean else "50",
        "mean_line": f"{mean_line:.2f}",
        "axis_min": f"{p_lo:,.0f}", "axis_max": f"{p_hi:,.0f}",
        "axis_mid": f"{(p_lo + p_hi) // 2:,.0f}",
        **{k: f"{v:.3f}" for k, v in seg.items()},
    }
    # 模板里硬编码的“万元”统一替换为单位占位（在替换 meta 文本之前，避免污染原文引用）
    tpl_text = template_path.read_text(encoding="utf-8").replace("万元", "${unit}")
    html = Template(tpl_text).safe_substitute(values)
    return html


def screenshot(html: str, output: str) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: 需要 python playwright（本机已装 1.60）。可退回 render_chart.py", file=sys.stderr)
        sys.exit(3)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(device_scale_factor=2)
        page = ctx.new_page()
        page.set_viewport_size({"width": 1200, "height": 1200})
        page.set_content(html, wait_until="load")
        page.wait_for_timeout(250)
        page.screenshot(path=str(out), full_page=True)
        browser.close()
    print(str(out))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--meta", default=None)
    ap.add_argument("--template", default=None)
    args = ap.parse_args()

    result = load_json(args.result)
    meta = load_json(args.meta) if args.meta else {}
    template = Path(args.template) if args.template else (
        Path(__file__).resolve().parent.parent / "assets" / "report_template.html"
    )
    if not template.exists():
        raise SystemExit(f"模板不存在: {template}")
    html = build(result, meta, template)
    screenshot(html, args.output)


if __name__ == "__main__":
    main()
