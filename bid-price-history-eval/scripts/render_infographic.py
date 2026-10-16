#!/usr/bin/env python3
"""bid-price-history-eval 信息分享长图（HTML 模板 + Playwright 截图 → PNG）。

用法:
  python render_infographic.py --result result.json --output 历史评估法信息图.png \
      [--meta meta.json] [--heatmap 路径.png] [--template assets/infographic_template.html]

- 输出为微信/群聊可分享的单张长图（宽度 1200px，全页截图）；
- 默认自动查找 result.json 同目录下的 heatmap_折扣乘折扣.png 并以 base64 内嵌；
  找不到则该节降级为文字说明（不影响出图）。
- meta.json 字段与 render_report.py 相同（见其模块 docstring）。
"""
import argparse
import base64
import datetime as dt
import json
import sys
from pathlib import Path
from string import Template

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_report import (  # noqa: E402
    load_json, money, pct, pin, esc,
)


def seg_pct(iv, lo, hi):
    left = pin(iv[0], lo, hi)
    right = pin(iv[1], lo, hi)
    return f"{left:.2f}", f"{max(right - left, 0.6):.2f}"


def build(result: dict, meta: dict, template_path: Path, heatmap: Path | None) -> str:
    if not result.get("ok"):
        raise SystemExit(f"result ok=false，无法出图: {result.get('error', '')}")

    axis_lo, axis_hi = float(result["axis"]["lo"]), float(result["axis"]["hi"])
    ceiling = float(result["ceiling_price"])
    sc = result["scoring"]
    base, valid, target = result["base_interval"], result["competitor_validate"], result["target_interval"]
    optimal = float(result["optimal"])
    tie_set = [float(t) for t in result["tie_set"]]
    competitors, scenarios = result["competitors"], result["scenarios"]

    project = meta.get("project") or result.get("project") or "投标报价测算"
    date = meta.get("date") or dt.date.today().isoformat()

    base_left, base_w = seg_pct(base, axis_lo, axis_hi)
    valid_left, valid_w = seg_pct(valid, axis_lo, axis_hi)
    target_left, target_w = seg_pct(target, axis_lo, axis_hi)
    optimal_pin = f"{pin(optimal, axis_lo, axis_hi):.2f}"

    # 四步收敛条（与 PDF 同口径）
    steps = [
        ("确定基础区间", base, f"{pct(base[0])}–{pct(base[1])}", "#3B82F6", False),
        ("对手报价习惯验证", valid, f"{pct(valid[0])}–{pct(valid[1])}", "#10B981", False),
        ("收缩目标区间", target, f"{pct(target[0])}–{pct(target[1])}", "#F87171", False),
        ("得分模拟锁定最优", (optimal, optimal), pct(optimal), "#DC2626", True),
    ]
    funnel_html = []
    for i, (title, iv, val, color, is_point) in enumerate(steps):
        f_l = pin(iv[0], axis_lo, axis_hi)
        f_w = max(pin(iv[1], axis_lo, axis_hi) - f_l, 1.2)
        if is_point:
            fill = f'<div class="fpin" style="left:{f_l:.2f}%"></div>'
        else:
            fill = f'<div class="ffill" style="left:{f_l:.2f}%;width:{f_w:.2f}%;background:{color}"></div>'
        funnel_html.append(
            f'<div class="fstep"><span class="fno">{i + 1}</span>'
            f'<span class="ftitle">{esc(title)}</span>'
            f'<div class="ftrack">{fill}</div>'
            f'<span class="fval num" style="color:{color}">{val}</span></div>'
        )
    funnel_html = "".join(funnel_html)

    # 对手区间（双列）
    comp_rows = []
    for c in sorted(competitors, key=lambda x: x["low"]):
        lo, hi = float(c["low"]), float(c["high"])
        bid = float(c.get("bid", (lo + hi) / 2))
        f_l = pin(lo, axis_lo, axis_hi)
        f_w = max(pin(hi, axis_lo, axis_hi) - f_l, 1.0)
        b_l = pin(bid, axis_lo, axis_hi)
        comp_rows.append(
            f'<div class="comp-row"><span class="comp-name">{esc(c["name"])}</span>'
            f'<div class="comp-track">'
            f'<div class="comp-fill" style="left:{f_l:.2f}%;width:{f_w:.2f}%"></div>'
            f'<div class="comp-bid" style="left:{b_l:.2f}%"></div></div>'
            f'<span class="comp-val num">{pct(lo)}–{pct(hi)}</span></div>'
        )
    comps_html = "".join(comp_rows)

    # 热力图内嵌
    if heatmap and heatmap.exists():
        b64 = base64.b64encode(heatmap.read_bytes()).decode("ascii")
        heatmap_img = f'<img alt="折扣乘折扣热力图" src="data:image/png;base64,{b64}">'
    else:
        heatmap_img = ('<div style="padding:60px 0;color:#8B98AE;font-size:15px">'
                       '（未找到 heatmap_折扣乘折扣.png，运行 history_eval.py 后重试）</div>')

    optimal_pct = pct(optimal)
    tie_txt = "/".join(pct(t) for t in tie_set)
    secondary = float(meta["secondary_discount"]) if meta.get("secondary_discount") is not None else (
        tie_set[-1] if len(tie_set) > 1 else optimal)
    secondary_pct, secondary_price = pct(secondary), money(round(secondary * ceiling, 2))

    kpi1_sub = (f"目标区间 {pct(target[0])}–{pct(target[1])} · 并列带 {tie_txt} 内按"
                f"{'偏低' if result.get('prefer_low', True) else '偏高'}取值")
    kpi2_sub = f"= 最高限价 {money(ceiling)} 元 × {optimal_pct}"
    kpi3_sub = (f"三情景平均 · {len(competitors) + 1} 家参与 × {len(scenarios)} 档情景 · "
                f"平均第 {result['avg_rank']} 名")
    suggest_note = meta.get("suggest_note") or (
        f"目标折扣 {optimal_pct} 在三档情景中平均得分 {result['avg_score']} 分；"
        f"{tie_txt} 统计并列，按甲方降本偏好取并列带内偏低值。"
    )

    values = {
        "project": esc(project), "date": date,
        "participants": str(len(competitors) + 1),
        "scenario_count": str(len(scenarios)),
        "rule_label": esc(meta.get("rule_label") or (meta.get("scoring_label") or "基准价法").split("（")[0]),
        "ceiling": money(ceiling),
        "target_interval": f"{pct(target[0])}–{pct(target[1])}",
        "tie_txt": tie_txt,
        "optimal_pct": optimal_pct, "optimal_price": money(result["optimal_price"]),
        "avg_score": str(result["avg_score"]), "avg_rank": str(result["avg_rank"]),
        "kpi1_sub": kpi1_sub, "kpi2_sub": kpi2_sub, "kpi3_sub": kpi3_sub,
        "base_left": base_left, "base_w": base_w, "base_txt": f"{pct(base[0])}–{pct(base[1])}",
        "valid_left": valid_left, "valid_w": valid_w, "valid_txt": f"{pct(valid[0])}–{pct(valid[1])}",
        "target_left": target_left, "target_w": target_w, "target_txt": f"{pct(target[0])}–{pct(target[1])}",
        "optimal_pin": optimal_pin,
        "axis_min": pct(axis_lo), "axis_mid": pct((axis_lo + axis_hi) / 2), "axis_max": pct(axis_hi),
        "funnel_html": funnel_html, "comps_html": comps_html,
        "heatmap_img": heatmap_img,
        "secondary_pct": secondary_pct, "secondary_price": secondary_price,
        "suggest_note": esc(suggest_note),
    }
    tpl_text = template_path.read_text(encoding="utf-8")
    return Template(tpl_text).safe_substitute(values)


def screenshot(html: str, output: str) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: 需要 python playwright 才能生成长图", file=sys.stderr)
        sys.exit(3)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(device_scale_factor=1.5)
        page = ctx.new_page()
        page.set_viewport_size({"width": 1200, "height": 1200})
        page.set_content(html, wait_until="load")
        page.wait_for_timeout(300)
        page.screenshot(path=str(out), full_page=True)
        browser.close()
    print(str(out))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--meta", default=None)
    ap.add_argument("--heatmap", default=None)
    ap.add_argument("--template", default=None)
    args = ap.parse_args()

    result = load_json(args.result)
    meta = load_json(args.meta) if args.meta else {}
    template = Path(args.template) if args.template else (
        Path(__file__).resolve().parent.parent / "assets" / "infographic_template.html"
    )
    if not template.exists():
        raise SystemExit(f"模板不存在: {template}")
    if args.heatmap:
        heatmap = Path(args.heatmap)
    else:
        heatmap = Path(args.result).parent / "heatmap_折扣乘折扣.png"
    html = build(result, meta, template, heatmap)
    screenshot(html, args.output)


if __name__ == "__main__":
    main()
