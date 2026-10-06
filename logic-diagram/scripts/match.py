#!/usr/bin/env python3
"""内容特征 → 逻辑图模板页候选排序。

用法：
  # 直接给特征
  python3 match.py --items 9 --logic 顺序流程 --chars-per-item 40

  # 或用 JSON 规格
  python3 match.py --spec spec.json

  # 浏览索引（不匹配，只筛选）
  python3 match.py --list --logic 对比 --slots 4

输出：JSON 数组，按得分降序，每项含 page / score / reasons / summary。
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, '..', 'assets', 'index.json')

# 逻辑类型的近邻关系：内容逻辑 → (强匹配, 弱匹配)
RELATED = {
    '顺序流程': {'strong': ['顺序流程'], 'weak': ['时间轴', '递进阶梯']},
    '时间轴':   {'strong': ['时间轴'],   'weak': ['顺序流程', '递进阶梯']},
    '并列要点': {'strong': ['并列要点'], 'weak': ['清单列表', '对比']},
    '对比':     {'strong': ['对比'],     'weak': ['并列要点', '二维矩阵']},
    '层级金字塔': {'strong': ['层级金字塔'], 'weak': ['漏斗筛选', '总分发散']},
    '总分发散': {'strong': ['总分发散'], 'weak': ['环形关系', '层级金字塔']},
    '循环闭环': {'strong': ['循环闭环'], 'weak': ['环形关系', '顺序流程']},
    '环形关系': {'strong': ['环形关系'], 'weak': ['循环闭环', '总分发散']},
    '因果链':   {'strong': ['因果链'],   'weak': ['顺序流程']},
    '漏斗筛选': {'strong': ['漏斗筛选'], 'weak': ['层级金字塔']},
    '二维矩阵': {'strong': ['二维矩阵'], 'weak': ['对比', '象限分布']},
    '递进阶梯': {'strong': ['递进阶梯'], 'weak': ['顺序流程', '层级金字塔']},
}


def load_index():
    with open(INDEX, encoding='utf-8') as f:
        return json.load(f)


def score_page(x, need):
    """对单页打分。返回 (分数, 理由列表)。"""
    st, cap = x['structure'], x['capacity']
    r, why = 0.0, []

    # 1) 逻辑类型（权重最高）
    lt = need.get('logic')
    if lt:
        rel = RELATED.get(lt, {'strong': [lt], 'weak': []})
        if x['logic_type'] in rel['strong']:
            r += 50
            why.append('类型命中+50')
        elif x['logic_type'] in rel['weak']:
            r += 28
            why.append(f"类型近似({x['logic_type']})+28")

    # 2) 槽位数量 —— 差 1 格扣 6 分，差 2 格以上基本出局
    n = need.get('n_items')
    if n:
        d = abs(st['slot_count'] - n)
        s = max(0.0, 30 - d * 6)
        r += s
        why.append(f"槽位{st['slot_count']}(差{d})+{s:.0f}")

    # 3) 容量：每个槽位放不放得下
    need_chars = need.get('chars_per_item')
    if need_chars:
        if cap['per_slot_chars'] >= need_chars:
            r += 20
            why.append(f"槽容{cap['per_slot_chars']}字≥需{need_chars}+20")
        else:
            ratio = cap['per_slot_chars'] / float(need_chars)
            r += 20 * ratio
            why.append(f"槽容{cap['per_slot_chars']}字<需{need_chars}+{20*ratio:.0f}")

    # 4) 层级过深不利于平铺（内容平铺时扣分；内容本身分层则不加不减）
    if need.get('flat', True) and st['hierarchy_depth'] >= 3:
        r -= 8
        why.append('层级深-8')

    # 5) 有序性
    if need.get('ordered') and st['ordered']:
        r += 5
        why.append('有序+5')
    if need.get('ordered') is False and not st['ordered']:
        r += 5
        why.append('无序+5')

    # 6) 场景匹配
    sc = need.get('scene')
    if sc and sc in x.get('scenes', []):
        r += 8
        why.append(f"场景({sc})+8")

    # 7) 置信度加权
    r *= (0.7 + 0.3 * x['confidence'])

    return r, why


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--items', type=int, help='内容项数')
    ap.add_argument('--logic', help='逻辑类型，如 顺序流程')
    ap.add_argument('--chars-per-item', type=int, help='每项大致字数')
    ap.add_argument('--scene', help='场景，如 教学课件')
    ap.add_argument('--ordered', action='store_true', default=None, help='内容有先后顺序')
    ap.add_argument('--spec', help='JSON 规格文件')
    ap.add_argument('--top', type=int, default=8, help='返回前 N 个（默认 8）')
    ap.add_argument('--list', action='store_true', help='只筛选不排序')
    ap.add_argument('--slots', help='--list 用：槽位数筛选，如 4 或 3-5')
    ap.add_argument('--all', action='store_true', help='--list 用：不限类型，列全部')
    args = ap.parse_args()

    idx = load_index()

    need = {}
    if args.spec:
        with open(args.spec, encoding='utf-8') as f:
            need = json.load(f)
    else:
        if args.items:
            need['n_items'] = args.items
        if args.logic:
            need['logic'] = args.logic
        if args.chars_per_item:
            need['chars_per_item'] = args.chars_per_item
        if args.scene:
            need['scene'] = args.scene
        if args.ordered is not None:
            need['ordered'] = args.ordered

    # ── 浏览模式 ──
    if args.list:
        sel = idx
        if args.logic and not args.all:
            sel = [x for x in sel if x['logic_type'] == args.logic]
        if args.slots:
            if '-' in args.slots:
                lo, hi = (int(v) for v in args.slots.split('-'))
                sel = [x for x in sel if lo <= x['structure']['slot_count'] <= hi]
            else:
                sel = [x for x in sel if x['structure']['slot_count'] == int(args.slots)]
        out = [{
            'page': x['page'], 'logic_type': x['logic_type'],
            'slots': x['structure']['slot_count'],
            'per_slot_chars': x['capacity']['per_slot_chars'],
            'depth': x['structure']['hierarchy_depth'],
            'confidence': x['confidence'], 'summary': x['summary'],
        } for x in sel]
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return

    if not need:
        ap.error('需要至少一个条件（--items/--logic/--chars-per-item/--scene），或用 --list 浏览')

    scored = []
    for x in idx:
        s, why = score_page(x, need)
        scored.append((s, x, why))
    scored.sort(key=lambda t: -t[0])

    out = [{
        'page': x['page'], 'score': round(s, 1),
        'logic_type': x['logic_type'],
        'slots': x['structure']['slot_count'],
        'per_slot_chars': x['capacity']['per_slot_chars'],
        'depth': x['structure']['hierarchy_depth'],
        'confidence': x['confidence'],
        'summary': x['summary'],
        'reasons': why,
    } for s, x, why in scored[:args.top]]

    print(json.dumps(out, ensure_ascii=False, indent=1))
    # 提示分数过低
    if out and out[0]['score'] < 55:
        print('\n⚠ 最高分偏低，说明库中可能没有真正贴合的版式；'
              '建议放宽逻辑类型或改用相近类型，并人工看图确认。', file=sys.stderr)


if __name__ == '__main__':
    main()
