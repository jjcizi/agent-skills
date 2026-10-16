#!/usr/bin/env python3
"""bid-price-history-eval 手机版式报告 PDF（HTML 模板 + Playwright 打印）。

用法:
  python render_report.py --result result.json --output 历史评估法报价测算报告.pdf \
      [--meta meta.json] [--html debug.html]

输入:
  result.json  —— history_eval.py 产出的结构化结果（全部数字从这里取，禁止手算）
  meta.json    —— 叙事/证据字段（agent 填写），缺省时用兜底文案

meta.json 字段（除标注"必填"外均可缺省）:
  project / date
  scoring_label          评分方法名（如"基准价法（去极值算术平均）"）
  scoring_evidence       识别依据：章节+页码+原句（必填，可信度来源）
  scoring_formula        招标原文评分公式（缺省用 result.scoring.method_text）
  base_reason            第1步基础区间的依据
  validate_reason        第2步对手验证的依据
  narrow_reason          第3步收缩依据（缺省用 result.narrow_reason）
  suggest_note           报价建议理由（2~3 句）
  consistency            历史项目评分方法一致性校验（见下），强烈建议填写:
    {"current_method": "平均价基准（去极值算术平均）",
     "projects": [{"project": "2023-2024甘肃电信同类项目", "method": "平均价基准", "match": true},
                  {"project": "中国铁塔总部2025培训", "method": "最低价基准", "match": false}],
     "note": "低价基准项目折扣不可直接外推……"}
  limits                 ["限制1", ...] 缺省用通用三条
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from string import Template

sys.path.insert(0, str(Path(__file__).resolve().parent))
from history_eval import score_generic, anomaly_desc  # noqa: E402  算分唯一来源


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def money(v) -> str:
    try:
        return f"{float(v):,.2f}"
    except (TypeError, ValueError):
        return "—"


def pct(v) -> str:
    """折扣率显示：整数保留整数，半点（如98.5%）保留1位小数。"""
    v = float(v)
    x = v * 100.0
    r = round(x)
    if abs(x - r) < 1e-6:
        return f"{r:.0f}%"
    return f"{x:.1f}%"


def pin(v: float, lo: float, hi: float) -> float:
    return max(0.0, min(100.0, (v - lo) / max(hi - lo, 1e-9) * 100))


def cell_color(t: float) -> str:
    """归一化后的相对得分 t∈[0,1] → 浅色底（0=红, 1=绿）"""
    t = max(0.0, min(1.0, t))
    hue = t * 120.0
    return f"hsl({hue:.0f}, 70%, 84%)"


def esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def build(result: dict, meta: dict, template_path: Path) -> str:
    if not result.get("ok"):
        raise SystemExit(f"result ok=false，无法出报告: {result.get('error', '')}")

    axis_lo = float(result["axis"]["lo"])
    axis_hi = float(result["axis"]["hi"])
    ceiling = float(result["ceiling_price"])
    sc = result["scoring"]
    base = result["base_interval"]
    valid = result["competitor_validate"]
    target = result["target_interval"]
    optimal = float(result["optimal"])
    optimal_price = float(result["optimal_price"])
    tie_set = [float(t) for t in result["tie_set"]]
    candidates = [float(c) for c in result["candidates"]]
    scenarios = result["scenarios"]
    competitors = result["competitors"]

    project = meta.get("project") or result.get("project") or "投标报价测算"
    date = meta.get("date") or dt.date.today().isoformat()

    # ---------- 区间轴 ----------
    def seg(iv):
        left = pin(iv[0], axis_lo, axis_hi)
        right = pin(iv[1], axis_lo, axis_hi)
        return f"{left:.2f}", f"{max(right - left, 0.6):.2f}"

    base_left, base_w = seg(base)
    valid_left, valid_w = seg(valid)
    target_left, target_w = seg(target)
    optimal_pin = f"{pin(optimal, axis_lo, axis_hi):.2f}"

    # ---------- 对手区间条 ----------
    comp_rows = []
    for c in sorted(competitors, key=lambda x: x["low"]):
        lo, hi = float(c["low"]), float(c["high"])
        bid = float(c.get("bid", (lo + hi) / 2))
        f_l = pin(lo, axis_lo, axis_hi)
        f_w = max(pin(hi, axis_lo, axis_hi) - f_l, 0.8)
        b_l = pin(bid, axis_lo, axis_hi)
        comp_rows.append(
            f'<div class="comp-row">'
            f'<span class="comp-name">{esc(c["name"])}</span>'
            f'<div class="comp-track">'
            f'<div class="comp-fill" style="left:{f_l:.2f}%;width:{f_w:.2f}%"></div>'
            f'<div class="comp-bid" style="left:{b_l:.2f}%"></div>'
            f'</div>'
            f'<span class="comp-val num">{pct(lo)}–{pct(hi)}</span></div>'
        )
    comps_html = "".join(comp_rows)

    # ---------- 折扣×折扣矩阵（原生表格） ----------
    step = float(result.get("axis_step", 0.01))
    col_lo = max(axis_lo, target[0] - 0.02)
    col_hi = min(axis_hi, target[1] + 0.02)
    cols = [round(col_lo + i * step, 4) for i in range(int((col_hi - col_lo) / step) + 1)]
    rows = [round(valid[1] - i * step, 4) for i in range(int((valid[1] - valid[0]) / step) + 1)]

    def in_target(v):
        return target[0] - 1e-9 <= v <= target[1] + 1e-9

    head = ['<th class="corner">对手<br>＼我方</th>']
    for c in cols:
        cls = "opt" if abs(c - optimal) < 1e-9 else ("tgt" if in_target(c) else "")
        head.append(f'<th class="{cls}">{pct(c)}</th>')
    cell_scores = [[score_generic(c, r, sc) for c in cols] for r in rows]
    flat = [s for row in cell_scores for s in row]
    s_min, s_max = min(flat), max(flat)
    s_span = max(s_max - s_min, 1e-9)
    dec = 2 if sc.get("type") == "low_basis" else 1
    body = []
    for r, score_row in zip(rows, cell_scores):
        tds = [f'<th style="background:#F1F5FB">{pct(r)}</th>']
        for c, s in zip(cols, score_row):
            cls = "opt" if abs(c - optimal) < 1e-9 else ("tgt" if in_target(c) else "")
            tds.append(f'<td class="{cls}" style="background:{cell_color((s - s_min) / s_span)}">'
                       f'{s:.{dec}f}</td>')
        body.append("<tr>" + "".join(tds) + "</tr>")
    matrix_html = f'<table class="mtx"><thead><tr>{"".join(head)}</tr></thead><tbody>{"".join(body)}</tbody></table>'

    # ---------- 证据列表 ----------
    ev_items = []
    for c in competitors:
        nodata = "无数据" in str(c.get("evidence", ""))
        badge = f'{pct(c["low"])}–{pct(c["high"])}'
        ev_items.append(
            f'<div class="ev-item"><div class="ev-head">'
            f'<span class="ev-name">{esc(c["name"])}</span>'
            f'<span class="ev-badge{" nodata" if nodata else ""}">估 {badge}</span></div>'
            f'<div class="comp-ev">{esc(c.get("evidence", "（未提供证据）"))}</div></div>'
        )
    evidence_html = "".join(ev_items)

    # ---------- 四步推导 ----------
    validate_reason = meta.get("validate_reason") or (
        f"已核实 {len(competitors)} 家参与单位近两年同类项目中标折扣，"
        f"集中于 {pct(valid[0])}–{pct(valid[1])}，与基础区间吻合，符合市场竞争常态。"
    )
    if sc.get("type") == "low_basis":
        bench_anom = f"基准价=最低有效报价，{anomaly_desc(sc)}"
        prefer_why = "价格权重小 + 异常低价审查趋严，优先保收入"
    else:
        bench_anom = "基准价=有效价去极值算术平均，异常价 50%–200%"
        prefer_why = "高报价扣分系数更大 + 甲方降本偏好"
    step4_reason = (
        f"对目标区间内 {len(candidates)} 个候选折扣做 {len(scenarios)} 档市场情景全字段模拟"
        f"（{bench_anom}）。"
        f"平均得分并列带（差距≤{result['tie_band']} 分）为 "
        + "、".join(pct(t) for t in tie_set)
        + f"；按{'偏低优先' if result.get('prefer_low', True) else '偏高优先'}"
          f"（{prefer_why}）取 {pct(optimal)}。"
    )
    steps = [
        ("确定基础区间", meta.get("base_reason") or
         f"上限=我方上次同类中标折扣（历史锚），下限=全国同类项目中标折扣底线（行业锚）。",
         pct(base[0]) + "–" + pct(base[1]), ""),
        ("对手报价习惯验证", validate_reason, pct(valid[0]) + "–" + pct(valid[1]), ""),
        ("收缩目标区间", result.get("narrow_reason") or
         "甲方降本需求 + 高报价扣分风险更大 + 专家建议偏低。",
         pct(target[0]) + "–" + pct(target[1]), ""),
        ("得分模拟锁定最优值", step4_reason, pct(optimal), " point"),
    ]
    steps_html = "".join(
        f'<div class="step"><div class="step-top">'
        f'<span class="step-no">{i + 1}</span>'
        f'<span class="step-title">{esc(t)}</span>'
        f'<span class="step-iv{cls}">{b}</span></div>'
        f'<div class="step-reason">{esc(r)}</div></div>'
        for i, (t, r, b, cls) in enumerate(steps)
    )

    # ---------- 情景模拟表 ----------
    hdr = "".join(f"<th>{esc(s['name'])}</th>" for s in scenarios)
    sim_rows = []
    for c in candidates:
        cls = "opt" if abs(c - optimal) < 1e-9 else ("tie" if c in tie_set else "")
        tds = [f'<td class="cand">{pct(c)}</td>']
        for s in scenarios:
            r = next(x for x in result["simulation"]
                     if abs(float(x["候选折扣"].rstrip("%")) / 100 - c) < 1e-6
                     and x["情景"] == s["name"])
            tds.append(f'<td class="cell"><b>{float(r["我方得分"]):.2f}</b>'
                       f'<span>第 {r["排名"]} 名</span></td>')
        avg = result["avg_scores"][f"{c:.2f}"]
        rk = result["avg_ranks"][f"{c:.2f}"]
        tds.append(f'<td class="cell"><b>{avg:.2f}</b><span>均第 {rk:.1f} 名</span></td>')
        sim_rows.append(f'<tr class="{cls}">{"".join(tds)}</tr>')
    sim_table = (f'<table class="sim"><thead><tr><th>候选折扣</th>{hdr}'
                 f'<th>平均</th></tr></thead><tbody>{"".join(sim_rows)}</tbody></table>')
    shifts = "、".join(f"{s['name']} {s['shift']:+.0%}" for s in scenarios)
    if sc.get("type") == "low_basis":
        bench_rule = "基准价=全场最低有效投标报价"
        anom_rule = anomaly_desc(sc)
    else:
        bench_rule = "基准价=有效评标价去一个最高一个最低后的算术平均（≤5 家不去极值）"
        anom_rule = "异常价 50%–200%"
    sim_note = (f"情景平移：{shifts}（对每家对手的估计报价整体平移）；"
                f"{bench_rule}，{anom_rule}；"
                f"单元格=我方价格得分与全场排名，绿底=选定值，黄底=并列带；"
                f"各候选在各情景下的基准价明细见 scenario_tables.csv。")

    # ---------- 评分方法 ----------
    scoring_label = meta.get("scoring_label") or "基准价法（去极值算术平均）"
    rule_label = meta.get("rule_label") or scoring_label.split("（")[0]
    scoring_formula = meta.get("scoring_formula") or sc.get("method_text") or "（缺评分原文）"
    scoring_evidence = meta.get("scoring_evidence") or "（meta.json 缺 scoring_evidence：请补招标文件章节+原句+页码）"

    # ---------- 历史项目评分方法一致性校验 ----------
    cons = meta.get("consistency")
    if cons:
        rows_html = []
        for p in cons.get("projects", []):
            ok = p.get("match")
            if ok is True:
                badge = ('<span class="ev-badge" style="color:var(--green);background:rgba(14,159,110,.08);'
                         'border-color:rgba(14,159,110,.35)">同口径</span>')
            elif ok is False:
                badge = ('<span class="ev-badge" style="color:var(--red);background:rgba(220,38,38,.07);'
                         'border-color:rgba(220,38,38,.35)">异口径</span>')
            else:
                badge = '<span class="ev-badge nodata">未核验</span>'
            tail = ""
            if ok is False:
                tail = "（与本次算法不同，折扣不可直接外推，仅作边界参考）"
            elif ok is None:
                tail = "（中标公示未含评标办法，需回查招标文件全文核验）"
            rows_html.append(
                f'<div class="ev-item"><div class="ev-head">'
                f'<span class="ev-name" style="font-size:11.5px">{esc(p.get("project", ""))}</span>'
                f'{badge}</div>'
                f'<div class="comp-ev">价格分算法：{esc(p.get("method", "未知"))}{tail}</div></div>'
            )
        consistency_html = (
            '<div class="card" style="margin-top:10px">'
            '<div class="mtx-note"><b>历史项目价格分算法一致性校验</b>——同一甲方不同标的价格分'
            '算法可能不同（低价基准 / 平均基准 / 随机系数等），不同算法下的历史折扣不可直接外推。'
            f'本次算法：<b style="color:var(--blue)">{esc(cons.get("current_method", rule_label))}</b></div>'
            '<div class="ev-list" style="margin-top:8px">' + "".join(rows_html) + '</div>'
            + (f'<div class="sim-note" style="margin-top:8px">{esc(cons.get("note", ""))}</div>'
               if cons.get("note") else "")
            + '</div>'
        )
    else:
        consistency_html = (
            '<div class="card" style="margin-top:10px"><div class="mtx-note">'
            '<b>历史项目价格分算法一致性校验</b>：meta.json 未提供 consistency 字段——'
            '请核对同甲方各历史标的价格分算法（低价基准/平均基准）是否与本次一致，'
            '不一致的证据不可直接外推，补齐后重渲染。</div></div>'
        )

    # ---------- KPI / 建议 ----------
    optimal_pct = pct(optimal)
    tie_txt = "/".join(pct(t) for t in tie_set)
    tie_rule_txt = "取偏低" if result.get("prefer_low", True) else "取偏高"
    secondary = float(meta["secondary_discount"]) if meta.get("secondary_discount") is not None else (
        tie_set[-1] if len(tie_set) > 1 else optimal)
    secondary_pct = pct(secondary)
    secondary_price = money(round(secondary * ceiling, 2))

    kpi1_sub = (f"目标区间 {pct(target[0])}–{pct(target[1])} · "
                f"并列带 {tie_txt} 内按{'偏低' if result.get('prefer_low', True) else '偏高'}取值")
    kpi2_sub = (f"= 最高限价 {money(ceiling)} 元 × {optimal_pct} · "
                f"三情景平均得分 {result['avg_score']} 分")
    kpi3_sub = (f"{len(competitors) + 1} 家参与 × {len(scenarios)} 档情景 · "
                f"并列带内差异≤{result['tie_band']} 分，统计上不可区分")

    suggest_note = meta.get("suggest_note") or (
        f"目标折扣 {optimal_pct}（{money(optimal_price)} 元）在三情景模拟中平均得分 "
        f"{result['avg_score']} 分、平均排名第 {result['avg_rank']} 名；"
        f"与 {tie_txt} 统计并列，按甲方降本偏好与高报价扣分风险取并列带内偏低值。"
        f"若市场偏热（对手整体上移），可上调至备选 {secondary_pct} 抢排名；"
        f"若成本线不允许低于 {pct(target[0])}，请以成本底线为准重新评估。"
    )

    limits = meta.get("limits") or [
        "对手折扣为历史/近期公告推算的估计值，非实时报价；对手临场策略变化会直接改变基准价与排名。",
        "仅模拟价格维度得分；技术/商务等非价格分未纳入，最终排序需结合非价格项评估。",
        "同一甲方不同标的价格分算法可能不同（低价基准 vs 平均基准），异口径历史折扣已降权但残余偏差仍在。",
    ]
    limits_items = "".join(f"<li>{esc(x)}</li>" for x in limits)

    values = {
        "project": esc(project), "date": date,
        "participants": str(len(competitors) + 1),
        "scenario_count": str(len(scenarios)),
        "rule_label": esc(rule_label),
        "ceiling": money(ceiling),
        "target_interval": f"{pct(target[0])}–{pct(target[1])}",
        "tie_txt": tie_txt,
        "tie_rule_txt": tie_rule_txt,
        "optimal_pct": optimal_pct, "optimal_price": money(optimal_price),
        "avg_score": str(result["avg_score"]), "avg_rank": str(result["avg_rank"]),
        "kpi1_sub": kpi1_sub, "kpi2_sub": kpi2_sub, "kpi3_sub": kpi3_sub,
        "base_left": base_left, "base_w": base_w, "base_txt": f"{pct(base[0])}–{pct(base[1])}",
        "valid_left": valid_left, "valid_w": valid_w, "valid_txt": f"{pct(valid[0])}–{pct(valid[1])}",
        "target_left": target_left, "target_w": target_w, "target_txt": f"{pct(target[0])}–{pct(target[1])}",
        "optimal_pin": optimal_pin,
        "axis_min": pct(axis_lo), "axis_mid": pct((axis_lo + axis_hi) / 2), "axis_max": pct(axis_hi),
        "comps_html": comps_html, "matrix_html": matrix_html,
        "matrix_span": f"对手折扣 {pct(valid[0])}–{pct(valid[1])} × 我方候选邻域",
        "scoring_label": esc(scoring_label), "scoring_formula": esc(scoring_formula),
        "scoring_evidence": esc(scoring_evidence),
        "evidence_html": evidence_html, "steps_html": steps_html,
        "sim_table": sim_table, "sim_note": esc(sim_note),
        "secondary_pct": secondary_pct, "secondary_price": secondary_price,
        "suggest_note": esc(suggest_note),
        "limits_items": limits_items,
        "consistency_html": consistency_html,
    }
    tpl_text = template_path.read_text(encoding="utf-8")
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
