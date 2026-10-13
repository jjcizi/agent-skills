#!/usr/bin/env python3
"""侦察模板页的版式：定位可替换的槽位、配对标题与正文、推导阅读顺序。

用法：
  python3 layout.py --page 7          # 人可读
  python3 layout.py --page 7 --json   # 机器可读
  python3 layout.py --page 7 --count  # 只报槽位数（选页后核对用）

核心概念：
  「槽位」= 一个可填内容的卡片。本模板库里绝大多数卡片由「标题 + 正文」两个形状组成，
  少数只有标题。顺序推导以**卡片**为单位（而非单个形状），否则标题行与正文行会被
  误判为两行，顺序全乱。
"""
import argparse
import json
import os
from collections import OrderedDict

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

HERE = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(HERE, '..', 'assets', 'template.pptx')
EMU = 914400.0
ROW_TOL = 0.45          # 卡片分行容差（英寸）；卡片高约 0.67，行距通常 >1.0


def walk_shapes(shapes, prefix=''):
    """递归遍历形状，含组合内部。

    坑：python-pptx 的 slide.shapes 不递归进组合。本模板约半数页面把
    「图标 + 说明文字」打包成了组合，不递归就会漏掉组内文字。

    产出 (path, shape)，path 形如 '6' 或 '3/0'（顶层第 3 个组合内的第 0 个形状）。
    """
    for i, sh in enumerate(shapes):
        p = f'{prefix}{i}'
        yield p, sh
        if sh.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from walk_shapes(sh.shapes, p + '/')


def get_shape(slide, path):
    """按 path 定位形状（walk_shapes 的逆运算）。"""
    parts = str(path).split('/')
    shapes = slide.shapes
    for p in parts[:-1]:
        shapes = shapes[int(p)].shapes
    return shapes[int(parts[-1])]


def load_slide(page):
    prs = Presentation(TPL)
    return prs, prs.slides[page - 1]


def collect_text_shapes(slide):
    """所有含非空文本的形状（含组合内部），带几何信息。idx 为路径字符串。"""
    out = []
    for path, sh in walk_shapes(slide.shapes):
        if not sh.has_text_frame:
            continue
        t = sh.text_frame.text.strip()
        if not t:
            continue
        out.append({
            'idx': path, 'text': t.replace('\n', ' ⏎ '), 'name': sh.name,
            'left': sh.left / EMU, 'top': sh.top / EMU,
            'width': sh.width / EMU, 'height': sh.height / EMU,
        })
    return out


def split_groups(shapes):
    """按「占位符文本」聚类。恰好 2 组时，短文本组是标题、长文本组是正文。"""
    groups = OrderedDict()
    for s in shapes:
        groups.setdefault(s['text'], []).append(s)
    info = [{'text': t, 'count': len(v)} for t, v in groups.items()]
    if len(groups) == 2:
        keys = sorted(groups, key=lambda t: len(t))
        return groups[keys[0]], groups[keys[1]], info
    return None, None, info


def make_cards(titles, bodies):
    """标题找最近正文配成卡片；返回每张卡片的锚点（用标题位置）。"""
    cards = []
    if titles is None:
        return cards
    used = set()
    for t in titles:
        cand = [b for b in bodies if b['idx'] not in used]
        if not cand:
            break
        b = min(cand, key=lambda b: (b['left'] - t['left']) ** 2 + (b['top'] - t['top']) ** 2)
        used.add(b['idx'])
        cards.append({'title_idx': t['idx'], 'body_idx': b['idx'],
                      'left': t['left'], 'top': t['top'], 'row': None})
    return cards


def group_rows(items, tol=ROW_TOL):
    """按 top 聚成行（排序后相邻间隔 > tol 即换行），行内按 left 升序。"""
    rows = []
    cur = []
    for it in sorted(items, key=lambda s: s['top']):
        if cur and it['top'] - cur[-1]['top'] > tol:
            rows.append(sorted(cur, key=lambda s: s['left']))
            cur = []
        cur.append(it)
    if cur:
        rows.append(sorted(cur, key=lambda s: s['left']))
    return rows


def reading_order(rows):
    """推导顺序：首行左→右；其后每行以「距上一行终点最近」的项作起点，
    起点在该行最右则整行反向 —— 蛇形折返版式靠这条规则自动识别。"""
    if not rows:
        return []
    seq = list(rows[0])
    for row in rows[1:]:
        if not row:
            continue
        last = seq[-1]
        start_i = min(range(len(row)),
                      key=lambda i: (row[i]['left'] - last['left']) ** 2
                                    + (row[i]['top'] - last['top']) ** 2)
        if start_i == 0:
            seq.extend(row)
        elif start_i == len(row) - 1:
            seq.extend(row[::-1])
        else:                      # 起点居中：向较近一侧展开
            seq.extend(list(reversed(row[:start_i + 1])) + row[start_i + 1:])
    return seq


def analyse(page):
    """完整版式分析。返回 dict。"""
    prs, slide = load_slide(page)
    shapes = collect_text_shapes(slide)
    titles, bodies, info = split_groups(shapes)

    if titles is not None:
        cards = make_cards(titles, bodies)
        unit = '卡片'
    else:
        cards = [{'title_idx': s['idx'], 'body_idx': None,
                  'left': s['left'], 'top': s['top'], 'text': s['text'], 'row': None}
                 for s in shapes]
        unit = '形状'

    rows = group_rows(cards)
    order = reading_order(rows)
    for i, row in enumerate(rows):
        for c in row:
            c['row'] = i

    # 判断是否有行被反向读取（蛇形）
    snake_rows = []
    pos = 0
    for i, row in enumerate(rows):
        seg = order[pos:pos + len(row)]
        pos += len(row)
        if len(row) > 1 and seg and seg[0]['left'] > seg[-1]['left']:
            snake_rows.append(i + 1)

    return {
        'page': page,
        'shape_total': sum(1 for _ in walk_shapes(slide.shapes)),
        'text_shape_count': len(shapes),
        'unit': unit,
        'text_groups': info,
        'slot_count': len(cards),
        'row_shape': [len(r) for r in rows],
        'snake_rows': snake_rows,
        'order': order,
        'shapes': shapes,
        'prs': prs, 'slide': slide,
    }


def set_text(shape, text):
    """替换文本但保留原有字号/颜色/对齐/字体。"""
    tf = shape.text_frame
    p0 = tf.paragraphs[0]
    if p0.runs:
        p0.runs[0].text = text
        for r in p0.runs[1:]:
            r._r.getparent().remove(r._r)
    else:
        p0.text = text
    for extra in list(tf.paragraphs[1:]):          # 清掉多余段落，避免残留旧文字
        extra._p.getparent().remove(extra._p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--page', type=int, required=True)
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--count', action='store_true', help='只报槽位数')
    args = ap.parse_args()

    r = analyse(args.page)

    if args.count:
        print(r['slot_count'])
        return

    if args.json:
        slim = {k: v for k, v in r.items() if k not in ('prs', 'slide')}
        slim['order'] = [{'title_idx': c['title_idx'], 'body_idx': c['body_idx'],
                          'left': round(c['left'], 2), 'top': round(c['top'], 2),
                          'row': c['row']} for c in r['order']]
        print(json.dumps(slim, ensure_ascii=False, indent=1))
        return

    print(f"第 {r['page']} 页 | 形状总数 {r['shape_total']}（含组合内） | 有文本 {r['text_shape_count']} 个")
    print(f"\n文本分组（相同占位文本为一组）：")
    for g in r['text_groups']:
        print(f"  ×{g['count']:2d}  {g['text'][:52]}")
    print(f"\n识别出 {r['slot_count']} 个槽位（{r['unit']}）")
    print(f"排列：{len(r['row_shape'])} 行，每行 {r['row_shape']}")
    if r['snake_rows']:
        print(f"⚠ 蛇形：第 {r['snake_rows']} 行是从右往左读的（模板固有设计）")
    print(f"\n阅读顺序：")
    for i, c in enumerate(r['order'], 1):
        b = f"+[{c['body_idx']}]" if c.get('body_idx') is not None else ''
        print(f"  #{i:2d}  [{c['title_idx']:>5s}]{b}   (x={c['left']:.2f}, y={c['top']:.2f})")
    if r['unit'] == '形状':
        print('\n⚠ 未配对成卡片（文本组数 ≠ 2）—— 请对照下方清单手工确认槽位。')
    print('\n形状清单（id 含 "/" 表示该文字藏在组合内部）：')
    for s in r['shapes']:
        print(f"  [{s['idx']:>5s}] {s['name'][:16]:16s} "
              f"({s['left']:5.2f},{s['top']:4.2f}) {s['width']:.2f}×{s['height']:.2f}  {s['text'][:40]}")


if __name__ == '__main__':
    main()
