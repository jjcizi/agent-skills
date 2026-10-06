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

import fitz
from PIL import Image, ImageChops, ImageFont
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from layout import analyse, set_text, get_shape, walk_shapes, TPL      # noqa: E402
from fonts import (FONT_FAMILY, ensure_fonts, find_soffice,            # noqa: E402
                   soffice_hint)

# LibreOffice 自动探测（环境变量 SOFFICE > PATH > 常见安装路径）。
# 原来硬编码 /opt/homebrew/bin/soffice，换台机器就找不到。
SOFFICE = find_soffice()
HEADING_FALLBACK_FONT = FONT_FAMILY
HEADING_COLOR = RGBColor(0x1F, 0x6F, 0xC4)

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, '..', 'assets', 'fonts')
EMU_PT = 12700.0        # 1 pt = 12700 EMU
PAD_RATIO = 0.02        # 裁剪后四周留白 = 内容长边的 2%（下限 8px）
LINE_SPACING = 1.1      # 单倍行高估算系数（由模板实测反推：0.57″ 框装 2 行 12pt 正常）

# 全页统一字体。
# 模板原用「阿里巴巴普惠体」「思源宋体 CN Heavy」，两者都不可自由分发，
# 绝大多数机器上也没装。LibreOffice 碰到不存在的字体名会按 fontconfig
# 各自乱回退，同一页里主标题/卡片标题/卡片正文/编号可能变成四款字体
# （实测出现过手札体、华文仿宋、魏碑体混排）。
# 与其猜字体名再映射，不如出图前把全页字体无条件钉死到**随包携带**的
# Noto Sans SC（思源黑体 Google 版，SIL OFL 1.1，允许再分发）：字号、
# 字重、颜色一律保留，只换字体名。ensure_fonts() 会保证它已装进系统。
# 若想改用本机其它字体：设环境变量 FONT_TARGET 覆盖即可。
FONT_TARGET = os.environ.get('FONT_TARGET') or FONT_FAMILY


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
                    rPr = r._r.get_or_add_rPr()
                # 已存在的字体槽全部改掉。除 latin/ea/cs 外还要管 a:sym：
                # 模板里的编号 01-06 只定义了一个 a:sym（=「阿里巴巴普惠体」
                # 这个装不上的字体），不管它就会回退成 Liberation Mono Italic。
                for tag in ('a:latin', 'a:ea', 'a:cs', 'a:sym'):
                    el = rPr.find(qn(tag))
                    if el is not None:
                        el.set('typeface', target)
                        changed += 1
                # 完全没有 latin 定义时补一个：否则拉丁字符（编号、英文单词）
                # 会落到主题默认字体，再被 fontconfig 碰运气回退。
                if rPr.find(qn('a:latin')) is None:
                    rPr.get_or_add_latin().set('typeface', target)
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


# ------------------------------------------------------------------ 文字适配

_font_cache = {}


def _metrics_font(size_pt, bold):
    """取测宽用字体对象（按 4 倍字号缓存再除 4，提高小字号的测量精度）。"""
    key = (int(round(size_pt * 4)), bool(bold))
    f = _font_cache.get(key)
    if f is None:
        name = 'NotoSansSC-Bold.otf' if bold else 'NotoSansSC-Regular.otf'
        f = ImageFont.truetype(os.path.join(FONT_DIR, name), max(4, key[0]))
        _font_cache[key] = f
    return f


def text_width_pt(text, size_pt, bold=False):
    """按 Noto Sans SC 度量一段文字的渲染宽度（单位 pt），与 PPTX 字号同尺度。"""
    if not text:
        return 0.0
    return _metrics_font(size_pt, bold).getlength(text) / 4.0


def _para_lines(p):
    """把段落按 <a:br/> 切成多行。

    坑：python-pptx 写 run.text 时把 '\\n' 落成 <a:br/>（软换行）而不是新段落，
    p.runs 会给出多个 run。直接 ''.join(r.text) 会把两行拼成一行——宽度翻倍，
    字号被白白压小。所以必须逐个 XML 子元素走，遇 br 就断行。
    """
    lines, cur = [], []
    for child in p._p:
        tag = child.tag.split('}')[-1]
        if tag == 'br':
            lines.append(''.join(cur))
            cur = []
        elif tag == 'r':
            t = child.find(qn('a:t'))
            cur.append(t.text if t is not None and t.text else '')
    lines.append(''.join(cur))
    return lines


def _is_vertical(tf):
    """是否竖排文本（eaVert / vert / vert270）。"""
    bp = tf._txBody.find(qn('a:bodyPr'))
    if bp is None:
        return False
    return (bp.get('vert') or 'horz') != 'horz'


def _wrap_lines(lines, size, avail_w, bold):
    """按可用宽对每行贪心折行，返回折行后的总行数。None = 框太窄，单字都放不下。"""
    total = 0
    for line in lines:
        if not line:
            total += 1
            continue
        if text_width_pt(line, size, bold) <= avail_w:   # 常见情形：一次测完
            total += 1
            continue
        cur, n = 0.0, 1
        for ch in line:
            w = text_width_pt(ch, size, bold)
            if w > avail_w:
                return None
            if cur + w > avail_w + 0.01:
                n += 1
                cur = w
            else:
                cur += w
        total += n
    return total


def fit_text(slide, min_pt=7.5):
    """按框宽自动缩字号，保证每段一行放得下；并关掉「形状随文字变高」。

    根因：模板里的文本框是 spAutoFit（形状高度跟着文字走）。字数一多就折行，
    文字框跟着变高，可背景色块是另一个形状、纹丝不动 —— 于是文字溢出框外。
    改法：先算出「最宽段落一行放得下的最大字号」把字号钉死，再把 autofit
    关掉（改成 noAutofit），形状尺寸就稳了，折行与溢出都不会再有。

    返回 (fitted, tight)：fitted = 缩了字号的框；tight = 缩到下限仍偏宽的框。
    """
    fitted, tight = [], []
    for path, sh in walk_shapes(slide.shapes):
        if not sh.has_text_frame:
            continue
        tf = sh.text_frame
        if not tf.text.strip():
            continue

        runs, base = [], None
        for p in tf.paragraphs:
            for r in p.runs:
                if not r.text:
                    continue
                sz = r.font.size.pt if r.font.size else None
                if sz and (base is None or sz < base):
                    base = sz
                runs.append(r)
        if base is None:                     # 字号继承自版式，不擅自改
            continue

        bolds = [bool(r.font.bold) for p in tf.paragraphs for r in p.runs if r.text]
        bold = any(bolds)
        lines = []
        for p in tf.paragraphs:
            lines.extend(_para_lines(p))
        lines = [l for l in lines if l.strip()]
        if not lines:
            continue

        ml, mr = tf.margin_left or 0, tf.margin_right or 0
        mt, mb = tf.margin_top or 0, tf.margin_bottom or 0
        avail_w = (sh.width - ml - mr) / EMU_PT
        avail_h = (sh.height - mt - mb) / EMU_PT
        vert = _is_vertical(tf)
        if vert:
            avail_w, avail_h = avail_h, avail_w     # 真·竖排：宽高互换
        if avail_w <= 1 or avail_h <= 1:
            continue

        # 框内连一个汉字都放不下：模板自带的超窄标签（靠逐字换行显示成竖排），
        # 原样保留——硬缩只会毁掉版面。
        if not vert and text_width_pt('国', base, bold) > avail_w:
            continue

        def fits(sz):
            n = _wrap_lines(lines, sz, avail_w, bold)
            return n is not None and n * sz * LINE_SPACING <= avail_h

        size = base
        while size > min_pt and not fits(size):
            size = max(min_pt, size - 0.5)
        for r in runs:
            r.font.size = Pt(size)
        tf.auto_size = MSO_AUTO_SIZE.NONE

        if size < base - 0.01:
            fitted.append((path, base, size))
        if not fits(size):
            n = _wrap_lines(lines, size, avail_w, bold)
            tight.append((path, size, n if n else '—', round(avail_h, 1)))
    return fitted, tight


# ------------------------------------------------------------------ 出图裁剪

def trim_outputs(doc, page, png_path, pad_ratio=PAD_RATIO, tol=6):
    """裁掉四周多余空白：内容包围盒 + **四边等宽**留白。

    模板是 16:9 演示页，内容只占中间一块、四周留白宽窄不一，插进文档还得
    手裁。这里按内容包围盒裁紧，四边补等宽留白；内容若贴边就用白底补齐，
    保证四条边留白严格一致（不会因为贴边而某一边变窄）。
    PDF 用同一组像素坐标换算 cropbox，两种产物几何完全对齐。
    """
    im = Image.open(png_path).convert('RGB')
    W, H = im.size
    white = Image.new('RGB', im.size, (255, 255, 255))
    mask = ImageChops.difference(im, white).convert('L').point(
        lambda v: 255 if v > tol else 0)          # 容差内一律视为纯白底
    bbox = mask.getbbox()
    if not bbox:
        return None
    x0, y0, x1, y1 = bbox
    pad = max(8, int(round(pad_ratio * max(x1 - x0, y1 - y0))))
    cx0, cy0, cx1, cy1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad

    if cx0 < 0 or cy0 < 0 or cx1 > W or cy1 > H:   # 内容贴边：补白，四边仍等宽
        canvas = Image.new('RGB', (cx1 - cx0, cy1 - cy0), (255, 255, 255))
        sx0, sy0 = max(0, cx0), max(0, cy0)
        canvas.paste(im.crop((sx0, sy0, min(W, cx1), min(H, cy1))),
                     (sx0 - cx0, sy0 - cy0))
        out = canvas
    else:
        out = im.crop((cx0, cy0, cx1, cy1))
    out.save(png_path)

    scale = page.rect.width / W
    ph = page.rect.height          # 坑：PDF 原点在左下、y 轴朝上，必须翻转 y
    box = fitz.Rect(cx0 * scale, ph - cy1 * scale, cx1 * scale, ph - cy0 * scale)
    page.set_cropbox(box)       # 先 CropBox（此时 MediaBox 还是原页，必然包含）
    page.set_mediabox(box)      # 再 MediaBox；两者都设，兼容不同阅读器/文档工具
    return {'src': (W, H), 'dst': out.size, 'pad': pad,
            'edge_before': (x0, y0, W - x1, H - y1)}


def render(pptx_path, out_dir, trim=True, pad_ratio=PAD_RATIO, keep_full=False):
    subprocess.run(
        [SOFFICE, '-env:UserInstallation=file:///tmp/lo_profile',
         '--headless', '--norestore', '--convert-to', 'pdf',
         pptx_path, '--outdir', out_dir],
        check=True, capture_output=True, timeout=300,
    )
    pdf = os.path.splitext(pptx_path)[0] + '.pdf'
    png = os.path.splitext(pptx_path)[0] + '.png'
    doc = fitz.open(pdf)
    page = doc[0]
    page.get_pixmap(dpi=150).save(png)

    info = None
    if trim:
        if keep_full:                              # 留一份未裁的全页版便于对照
            Image.open(png).save(os.path.splitext(png)[0] + '.full.png')
        info = trim_outputs(doc, page, png, pad_ratio)
        tmp = pdf + '.tmp'
        doc.save(tmp, deflate=True)     # 不用 garbage：会触发 structure tree 报错
        doc.close()
        os.replace(tmp, pdf)
    else:
        doc.close()
    return pdf, png, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--page', type=int, required=True)
    ap.add_argument('--spec', help='内容 JSON（自动配对模式）')
    ap.add_argument('--map', dest='mapfile', help='替换映射 JSON（显式模式）')
    ap.add_argument('--outdir', default='.')
    ap.add_argument('--name', help='输出文件名（不含扩展名）')
    ap.add_argument('--no-heading', action='store_true', help='不加顶部主标题')
    ap.add_argument('--no-fit', action='store_true', help='不自动缩放字号（保留模板原字号）')
    ap.add_argument('--no-trim', action='store_true', help='不裁四周白边（输出整页）')
    ap.add_argument('--pad', type=float, default=PAD_RATIO,
                    help=f'裁剪后四边留白比例（默认 {PAD_RATIO}）')
    ap.add_argument('--keep-full', action='store_true', help='额外保留未裁剪的全页 PNG')
    args = ap.parse_args()

    if not ensure_fonts():
        sys.exit('✗ 随包字体不可用。请先运行：python3 scripts/setup_fonts.py')
    if not SOFFICE:
        sys.exit(soffice_hint())

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

    fitted, tight = ([], [])
    if not args.no_fit:
        fitted, tight = fit_text(slide)

    normalise_fonts(slide)

    keep_only(prs, args.page - 1)

    os.makedirs(args.outdir, exist_ok=True)
    name = args.name or f'第{args.page}页'
    out = os.path.join(args.outdir, name + '.pptx')
    prs.save(out)
    print(f'✓ PPTX  {out}')
    pdf, png, info = render(out, args.outdir, trim=not args.no_trim,
                            pad_ratio=args.pad, keep_full=args.keep_full)
    print(f'✓ PDF   {pdf}')
    print(f'✓ PNG   {png}')

    if fitted:
        print(f'\n✓ 文字适配：{len(fitted)} 个文本框自动缩了字号（保证不折行、不越框）')
        for path, base, size in fitted[:14]:
            print(f'    [{path:>5s}] {base:g}pt → {size:g}pt')
        if len(fitted) > 14:
            print(f'    … 另有 {len(fitted) - 14} 个')
    if tight:
        print(f'\n⚠ 下列文本框缩到下限仍装不下，请精简文字：')
        for path, size, n, ah in tight:
            print(f'    [{path:>5s}] {size:g}pt 下需 {n} 行，超出可用高 {ah}pt')
    if info:
        sw, sh_ = info['src']
        dw, dh = info['dst']
        e = info['edge_before']
        print(f'\n✓ 裁白边：{sw}×{sh_} → {dw}×{dh}px，四边留白 {info["pad"]}px 等宽'
              f'（裁前四周分别为 左{e[0]} 上{e[1]} 右{e[2]} 下{e[3]}px）')

    if snake:
        print(f'\n⚠ 该页第 {snake} 行是逆序读取的蛇形版式（模板固有）；'
              f'内容有严格先后时请看图确认顺序。')
    print('\n⚠ 请打开 PNG 核对：文字是否溢出、顺序是否正确、有无空白槽位。')


if __name__ == '__main__':
    main()
