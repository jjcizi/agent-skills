#!/usr/bin/env python3
"""安装 / 检查 / 卸载本 skill 随包字体（Noto Sans SC，SIL OFL 1.1）。

  python3 setup_fonts.py              # 安装（幂等，写入用户字体目录）
  python3 setup_fonts.py --check      # 只检查，不改动
  python3 setup_fonts.py --uninstall  # 卸载（仅移除本 skill 装的那份）
  python3 setup_fonts.py --where      # 打印字体目录与状态

通常不必手动跑：build.py 启动时会自动确保字体就绪。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fonts import (FONT_DIR, FONT_FAMILY, FONT_FILES, ensure_fonts,  # noqa: E402
                   fonts_installed, install_fonts, uninstall_fonts,
                   user_font_dir, find_soffice, soffice_hint)


def main():
    ap = argparse.ArgumentParser(description=f'管理随包字体 {FONT_FAMILY}')
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--check', action='store_true', help='只检查，不安装')
    g.add_argument('--uninstall', action='store_true', help='卸载随包字体')
    g.add_argument('--where', action='store_true', help='显示路径与状态')
    args = ap.parse_args()

    if args.where:
        print(f'随包字体目录 : {FONT_DIR}')
        print(f'  ' + '\n  '.join(FONT_FILES))
        print(f'用户字体目录 : {user_font_dir()}')
        print(f'字体族名     : {FONT_FAMILY}')
        print(f'已安装       : {"是" if fonts_installed() else "否"}')
        s = find_soffice()
        print(f'LibreOffice  : {s or "未找到（安装后重跑）"}')
        return 0

    if args.check:
        if fonts_installed():
            print(f'✓ {FONT_FAMILY} 已安装（{user_font_dir()}）')
            return 0
        print(f'✗ {FONT_FAMILY} 未安装。运行 `python3 setup_fonts.py` 安装。')
        return 1

    if args.uninstall:
        uninstall_fonts()
        print('提示：其他项目若也用了同一份字体，可能同时受影响（按文件大小一致判定）。')
        return 0

    ok = ensure_fonts()
    if not ok:
        print('✗ 字体安装未成功，请检查随包 assets/fonts/ 是否完整。', file=sys.stderr)
        return 1
    if not find_soffice():
        print(soffice_hint(), file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
