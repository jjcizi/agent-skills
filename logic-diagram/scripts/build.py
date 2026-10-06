#!/usr/bin/env python3
"""选页 → 填入内容 → 渲染出图。

两种模式：

【A】自动配对（仅适用于占位符页，全库 18 页：2,4,5,7,8,9,13,15,16,20,21,23,28,29,31,36,38,39）
  python3 build.py --page 7 --spec content.json --outdir ./输出
  content.json：{"heading":"主标题","items":[{"title":"..","body":".."}]}

【B】显式映射（适用于任何页，含 105 页带示例内容的页）
  python3 build.py --page 43 --map map.json --outdir ./输出
  map.json：{"heading":"主标题（可选）","replacements":[{"shape":27,"text":"新文字"}]}
  先用 `layout.py --page 43` 拿到形状清单，再对着缩略图决定哪个 idx 换成什么。

两种模式产物相同：<outdir>/<name>.pptx / .pdf / .png
"""
import argparse
import json
import os
import subprocess
import sys

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from layout import analyse, set_text, get_shape, walk_shapes, TPL      # noqa: E402

SOFFICE = '/opt/homebrew/bin/soffice'
HEADING_FALLBACK_FONT = 'PingFang SC'
HEADING_COLOR = RGBColor(0x1F, 0x6F, 0xC4)

# 全页统一字体。
# 模板原用「阿里巴巴普惠体」「思源宋体 CN Heavy」，本机都没装。
# LibreOffice 碰到不存在的字体名会按 fontconfig 各自乱回退，
# 同一页里主标题/卡片标题/卡片正文/编号可能变成四款字体
# （实测出现过手札体、华文仿宋、魏碑体混排）。
# 与其猜字体名再映射，不如出图前把全页字体无条件钉死到
# 一个确定可用的字体：字号、字重、颜色一律保留，只换字体名。
# 若将来模板字体装齐，把 normalise_fonts() 的调用去掉即可。
FONT_TARGET = 'PingFang SC'


def normalise_fonts(slide, target=FONT_TARGET):
    """把全页每个 run 的字体无条件钉到 target，消除渲染回退导致的字体混排。

    纯文字替换不会动字体，模板里那个装不了的字体名会一直留着，
    每次渲染都靠 fontconfig 碰运气。出图前把名字换掉，结果才可控。
    字号、字重、颜色、对齐都不动，只改 typeface。
    """
    changed = 0
    for _path, sh in walk_shapes(slide.shapes):
        if not sh.has_text_frame:
            continue
        for p in sh.text_frame.paragraphs:
            for r in p.runs:
                rPr = r._r.find(qn('a:rPr'))
                if rPr is None:
                    continue
                for tag in ('a:latin', 'a:ea', 'a:cs'):
                    el = rPr.find(qn(tag))
                    if el is not None:
                        el.set('typeface', target)
                        changed += 1
    return changed


def template_font(slide):
    """读模板主视觉字体名，供主标题复用，保证标题与卡片同款。

    坑：一页里常有多款字体（标题 / 正文 / 编号各不相同），而且各自
    字符数悬殊——正文一堆字、标题只几个字。按「第一个命中」会被形状
    顺序带偏（编号常排在前面），按「字符数加权」会被正文带偏。
    这里改为**每个文本形状投一票**（投给它首个 run 的字体），取票数
    最高者：它代表页面里「最多元素在用」的字体，即主视觉字体。

    返回的名字可能是模板原名（本机未装），随后 normalise_fonts
    会统一映射成已装字体，主标题与卡片标题因此同进退。
    """
    votes = {}
    for _path, sh in walk_shapes(slide.shapes):
        if not sh.has_text_frame:
            continue
        name = None
        for p in sh.text_frame.paragraphs:
            for r in p.runs:
                rPr = r._r.find(qn('a:rPr'))
                if rPr is None:
                    continue
                el = rPr.find(qn('a:ea'))
                if el is None:
                    el = rPr.find(qn('a:latin'))
                if el is not None and el.get('typeface'):
                    name = el.get('typeface')
                    break
            if name:
                break
        if name:
            votes[name] = votes.get(name, 0) + 1
    if not votes:
        return HEADING_FALLBACK_FONT
    return max(votes.items(), key=lambda kv: kv[1])[0]


def add_heading(slide, text, font=None):
    """在页面顶部加一个主标题（模板本身不含标题位）。"""
    tb = slide.shapes.add_textbox(Inches(0.6), Inches(0.5), Inches(12.13), Inches(0.8))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = text
    run.font.size = Pt(26)
    run.font.bold = True
    run.font.color.rgb = HEADING_COLOR
    rPr = run._r.get_or_add_rPr()
    for tag in ('a:latin', 'a:ea', 'a:cs'):
        rPr.append(rPr.makeelement(qn(tag), {'typeface': font or HEADING_FALLBACK_FONT}))


def keep_only(prs, page_index):
    """只保留指定页（含 drop_rel，清理关系）。"""
    R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
    lst = prs.slides._sldIdLst
    ids = list(lst)
    for i in sorted([i for i in range(len(ids)) if i != page_index], reverse=True):
        prs.part.drop_rel(ids[i].get(R))
        lst.remove(ids[i])


def render(pptx_path, out_dir):
    subprocess.run(
        [SOFFICE, '-env:UserInstallation=file:///tmp/lo_profile',
         '--headless', '--norestore', '--convert-to', 'pdf',
         pptx_path, '--outdir', out_dir],
        check=True, capture_output=True, timeout=300,
    )
    pdf = os.path.splitext(pptx_path)[0] + '.pdf'
    import fitz
    doc = fitz.open(pdf)
    png = os.path.splitext(pptx_path)[0] + '.png'
    doc[0].get_pixmap(dpi=150).save(png)
    doc.close()
    return pdf, png


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--page', type=int, required=True)
    ap.add_argument('--spec', help='内容 JSON（自动配对模式）')
    ap.add_argument('--map', dest='mapfile', help='替换映射 JSON（显式模式）')
    ap.add_argument('--outdir', default='.')
    ap.add_argument('--name', help='输出文件名（不含扩展名）')
    ap.add_argument('--no-heading', action='store_true', help='不加顶部主标题')
    args = ap.parse_args()

    if bool(args.spec) == bool(args.mapfile):
        sys.exit('✗ 必须且只能指定一个：--spec（自动配对）或 --map（显式映射）')

    prs = Presentation(TPL)
    slide = prs.slides[args.page - 1]
    snake = None

    if args.mapfile:
        # ---- 模式 B：显式映射 ----
        with open(args.mapfile, encoding='utf-8') as f:
            m = json.load(f)
        reps = m.get('replacements', [])
        if not reps:
            sys.exit('✗ map.json 里没有 replacements')
        n = sum(1 for _ in walk_shapes(slide.shapes))
        for rep in reps:
            path = str(rep['shape'])
            try:
                sh = get_shape(slide, path)
            except (IndexError, ValueError, AttributeError):
                sys.exit(f'✗ 形状路径 {path} 无效（该页共 {n} 个形状，id 形如 "6" 或 "3/0"；'
                         f'请用 layout.py --page {args.page} 查看清单）')
            if not sh.has_text_frame:
                sys.exit(f'✗ 形状 {path} 不含文本框，无法写入（用 layout.py 确认 id）')
            set_text(sh, rep.get('text', ''))
        heading = m.get('heading')
        print(f'✓ 已替换 {len(reps)} 处文字')
    else:
        # ---- 模式 A：自动配对 ----
        with open(args.spec, encoding='utf-8') as f:
            spec = json.load(f)
        items = spec.get('items', [])
        heading = spec.get('heading')

        r = analyse(args.page)
        cards, slots = r['order'], r['slot_count']
        snake = r['snake_rows']

        if r['unit'] != '卡片':
            sys.exit(
                f'✗ 第 {args.page} 页不是占位符页（文本组数 ≠ 2），自动配对不适用。\n'
                f'  全库纯占位符页只有：2,4,5,7,8,9,13,15,16,20,21,23,28,29,31,36,38,39\n'
                f'  该页请改用 --map 显式映射模式（先跑 layout.py --page {args.page} 看形状清单）。')

        if len(items) != slots:
            sys.exit(f'✗ 槽位不匹配：第 {args.page} 页有 {slots} 个槽位，内容给了 {len(items)} 项。\n'
                     f'  请增删内容项，或换一页模板（用 match.py 找槽位数相符的页）。')

        has_body = cards[0].get('body_idx') is not None
        for card, item in zip(cards, items):
            set_text(get_shape(slide, card['title_idx']), item.get('title', ''))
            if has_body:
                set_text(get_shape(slide, card['body_idx']), item.get('body', ''))

    if heading and not args.no_heading:
        add_heading(slide, heading, template_font(slide))

    normalise_fonts(slide)

    keep_only(prs, args.page - 1)

    os.makedirs(args.outdir, exist_ok=True)
    name = args.name or f'第{args.page}页'
    out = os.path.join(args.outdir, name + '.pptx')
    prs.save(out)
    print(f'✓ PPTX  {out}')
    pdf, png = render(out, args.outdir)
    print(f'✓ PDF   {pdf}')
    print(f'✓ PNG   {png}')

    if snake:
        print(f'\n⚠ 该页第 {snake} 行是逆序读取的蛇形版式（模板固有）；'
              f'内容有严格先后时请看图确认顺序。')
    print('\n⚠ 请打开 PNG 核对：文字是否溢出、顺序是否正确、有无空白槽位。')


if __name__ == '__main__':
    main()
