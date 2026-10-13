#!/usr/bin/env python3
"""字体与 LibreOffice 定位。

逻辑图模板原用「阿里巴巴普惠体」「思源宋体 CN Heavy」，两者都不可自由
分发、绝大多数机器上也没装。本 skill 随包携带 **Noto Sans SC**（思源黑体
的 Google 发行版，SIL OFL 1.1，明确允许再分发），放在 assets/fonts/ 下，
出图前把全页字体钉到它，跨机器结果才一致。

关键点：LibreOffice 只能渲染**系统已安装**的字体。所以首次运行要把
assets/fonts/*.otf 装进用户字体目录（用户级，无需 sudo）。
build.py 会自动调用 ensure_fonts()；也可单独跑 setup_fonts.py。
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.normpath(os.path.join(HERE, '..', 'assets', 'fonts'))
FONT_FAMILY = 'Noto Sans SC'
FONT_FILES = ('NotoSansSC-Regular.otf', 'NotoSansSC-Bold.otf')

SOFFICE_CANDIDATES = (
    '/opt/homebrew/bin/soffice',                          # macOS (Apple Silicon)
    '/usr/local/bin/soffice',                             # macOS (Intel)
    '/Applications/LibreOffice.app/Contents/MacOS/soffice',
    '/usr/bin/soffice',                                   # Debian/Ubuntu
    '/usr/bin/libreoffice',
    '/snap/bin/libreoffice',                              # snap
    '/usr/lib/libreoffice/program/soffice',               # 部分发行版
    r'C:\Program Files\LibreOffice\program\soffice.exe',  # Windows
    r'C:\Program Files (x86)\LibreOffice\program\soffice.exe',
)


def user_font_dir():
    """各平台的用户级字体目录（无需管理员权限）。"""
    if sys.platform == 'darwin':
        return os.path.expanduser('~/Library/Fonts')
    if os.name == 'nt':
        base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~/AppData/Local')
        return os.path.join(base, 'Microsoft', 'Windows', 'Fonts')
    return os.path.expanduser('~/.local/share/fonts')


def _same_size(a, b):
    return os.path.exists(a) and os.path.exists(b) and os.path.getsize(a) == os.path.getsize(b)


def fonts_installed():
    """用户字体目录里是否已有与随包副本同大小的字体。"""
    d = user_font_dir()
    return all(_same_size(os.path.join(d, f), os.path.join(FONT_DIR, f)) for f in FONT_FILES)


def refresh_cache():
    """刷新 fontconfig 缓存（Linux/有 fontconfig 的 macOS 需要）。"""
    exe = shutil.which('fc-cache')
    if not exe:
        return False
    try:
        subprocess.run([exe, '-f'], capture_output=True, timeout=180)
        return True
    except Exception:
        return False


def install_fonts(verbose=True):
    """把随包字体复制到用户字体目录并刷新缓存。幂等。"""
    d = user_font_dir()
    os.makedirs(d, exist_ok=True)
    copied = []
    for f in FONT_FILES:
        src = os.path.join(FONT_DIR, f)
        if not os.path.exists(src):
            raise FileNotFoundError(f'随包字体缺失：{src}')
        dst = os.path.join(d, f)
        if not _same_size(dst, src):
            shutil.copy2(src, dst)
            copied.append(f)
    refreshed = refresh_cache()
    if verbose:
        if copied:
            print(f'✓ 已安装 {len(copied)} 个字体到 {d}')
            if refreshed:
                print('  （已刷新字体缓存）')
            else:
                print('  （未找到 fc-cache；若 LibreOffice 仍认不出字体，请重启它或重开终端）')
        else:
            print(f'✓ 字体已是最新：{d}')
    return fonts_installed()


def ensure_fonts(verbose=True):
    """确保字体就绪；缺失则自动安装。返回是否就绪。"""
    if not os.path.isdir(FONT_DIR):
        if verbose:
            print(f'✗ 找不到随包字体目录：{FONT_DIR}', file=sys.stderr)
        return False
    if fonts_installed():
        if verbose:
            print(f'✓ 字体就绪：{FONT_FAMILY}')
        return True
    try:
        return install_fonts(verbose=verbose)
    except Exception as e:
        if verbose:
            print(f'✗ 字体安装失败：{e}', file=sys.stderr)
        return False


def uninstall_fonts(verbose=True):
    """从用户字体目录移除随包字体（copy 安装方式的逆操作）。"""
    d = user_font_dir()
    removed = []
    for f in FONT_FILES:
        p = os.path.join(d, f)
        if _same_size(p, os.path.join(FONT_DIR, f)):
            os.remove(p)
            removed.append(f)
    refresh_cache()
    if verbose:
        print(f'✓ 已移除 {len(removed)} 个字体文件' if removed else '· 用户字体目录里没有本 skill 安装的字体')
    return removed


def find_soffice():
    """定位 LibreOffice 可执行文件；找不到返回 None。"""
    env = os.environ.get('SOFFICE')
    if env and os.path.exists(env):
        return env
    for name in ('soffice', 'libreoffice'):
        p = shutil.which(name)
        if p:
            return p
    for c in SOFFICE_CANDIDATES:
        if os.path.exists(c):
            return c
    return None


def soffice_hint():
    return (
        '✗ 找不到 LibreOffice（soffice）。请安装后重试：\n'
        '  macOS   : brew install --cask libreoffice\n'
        '  Ubuntu  : sudo apt install libreoffice\n'
        '  其他    : https://www.libreoffice.org/download/\n'
        '  已装在非标准路径时，设环境变量：export SOFFICE=/path/to/soffice'
    )
