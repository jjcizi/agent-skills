#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_pack.py —— 把「配套材料/」目录下的多份 Markdown 合并成一份可打印的 Word。

每份材料自动：
  - 另起一页
  - 顶部加一行「【需打印】材料 N」标注
  - 保留材料自身的 # 标题与正文样式（沿用 make_docx 的排版规范）

用法：
    python3 make_pack.py 配套材料/ -o "打印材料包.docx" --title "《制定项目章程》配套打印材料"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_docx import build  # noqa: E402

# 每份材料从新的一页开始，方便直接打印；材料上不叠加任何元信息文字。

def collect(src: Path) -> list[Path]:
    if src.is_dir():
        files = sorted(p for p in src.glob("*.md") if not p.name.startswith("_"))
    else:
        files = [src]
    return files


def merge(files: list[Path], compact: bool = False) -> str:
    """合并材料：每份从新的一页开始。不在材料上插入任何页眉/标注文字。"""
    chunks = []
    for i, f in enumerate(files, 1):
        text = f.read_text(encoding="utf-8").lstrip("\n")
        prefix = "" if i == 1 else "\n\\newpage\n\n"
        chunks.append(prefix + text)
    return "\n".join(chunks)


def main():
    ap = argparse.ArgumentParser(description="配套材料 → 合并的可打印 Word")
    ap.add_argument("source", help="配套材料目录或单个 md")
    ap.add_argument("-o", "--out", required=True, help="输出的 .docx 路径")
    ap.add_argument("--title", help="文档标题（用于页眉）")
    ap.add_argument("--style", choices=["standard", "kami"], default="standard")
    ap.add_argument("--compact", action="store_true",
                    help="极紧排版（仅当单份材料内容特别多时才用）")
    ap.add_argument("--standard", action="store_true",
                    help="标准排版（字体最大，但可能超出每份 1 页）")
    a = ap.parse_args()

    files = collect(Path(a.source))
    if not files:
        print(f"目录中没有 .md 材料：{a.source}", file=sys.stderr)
        return 2

    use_fit = not a.compact and not a.standard
    merged = merge(files, compact=a.compact)
    tmp = Path(a.out).with_suffix(".merged.md")
    tmp.write_text(merged, encoding="utf-8")

    path, doc_title = build(tmp, Path(a.out), a.title or "配套打印材料", a.style,
                            compact=a.compact, fit=use_fit,
                            header=False, footer=False)  # 发给学生的材料：不要页眉页码
    tmp.unlink(missing_ok=True)
    print(f"已生成: {path}\n合并材料 {len(files)} 份:")
    for i, f in enumerate(files, 1):
        print(f"  材料 {i}: {f.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
