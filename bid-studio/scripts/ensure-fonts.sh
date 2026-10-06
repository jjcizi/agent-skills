#!/usr/bin/env bash
# bid-studio 字体就绪脚本
# 开源字体（思源宋体 SC，SIL OFL 1.1）随仓库内置，无需下载；
# 商业字体（仓耳今楷 02，版权归仓耳字库）体积大且需自行确认授权，按需自动下载。
#
# 用法：
#   bash scripts/ensure-fonts.sh
# 只读环境下可指定可写目录：
#   BIDSTUDIO_FONT_DIR=~/.local/share/fonts/bid-studio bash scripts/ensure-fonts.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FONT_DIR="${BIDSTUDIO_FONT_DIR:-$SKILL_DIR/assets/fonts}"

# 体积阈值：低于此值视为下载不完整/占位文件
MIN_OTF=5000000    # 思源宋体 SC 约 23-24MB
MIN_TTF=10000000   # 仓耳今楷 02 约 18MB

size_ok() {
  [[ -f "$1" ]] || return 1
  local s
  s=$(wc -c < "$1" | tr -d ' ')
  [[ "$s" -ge "$2" ]]
}

echo "bid-studio 字体检查"
echo "字体目录：$FONT_DIR"
if ! mkdir -p "$FONT_DIR" 2>/dev/null; then
  echo "错误：字体目录不可写。请用 BIDSTUDIO_FONT_DIR 指定可写目录后重试。"
  exit 1
fi

missing_open=0
missing_comm=0

# ── 1. 开源字体：思源宋体 SC（SIL OFL 1.1，仓库自带）──────────────
echo
echo "[1/2] 开源字体 · 思源宋体 SC（SIL OFL 1.1）"
for f in SourceHanSerifSC-Regular.otf SourceHanSerifSC-Medium.otf; do
  if size_ok "$FONT_DIR/$f" "$MIN_OTF"; then
    echo "  ✓ ${f}"
  else
    echo "  ✗ ${f} 缺失"
    missing_open=1
  fi
done

# ── 2. 商业字体：仓耳今楷 02（需自行确认授权，自动下载）───────────
echo
echo "[2/2] 商业字体 · 仓耳今楷 02（版权归仓耳字库，商用请自行确认授权）"
MIRRORS=(
  "https://cdn.jsdelivr.net/gh/tw93/Kami@main/assets/fonts"
  "https://cdn.jsdmirror.com/gh/tw93/Kami@main/assets/fonts"
)
for f in TsangerJinKai02-W04.ttf TsangerJinKai02-W05.ttf; do
  if size_ok "$FONT_DIR/$f" "$MIN_TTF"; then
    echo "  ✓ ${f}（已就绪）"
    continue
  fi
  got=0
  for src in "${MIRRORS[@]}"; do
    url="$src/$f"
    echo "  下载 ${f}"
    echo "    ← $url"
    if curl --retry 2 --connect-timeout 15 --max-time 300 -fSL "$url" \
            -o "$FONT_DIR/$f.part" 2>/dev/null \
       && size_ok "$FONT_DIR/$f.part" "$MIN_TTF"; then
      mv "$FONT_DIR/$f.part" "$FONT_DIR/$f"
      echo "  ✓ ${f} 完成（$(du -h "$FONT_DIR/$f" | cut -f1)）"
      got=1
      break
    fi
    rm -f "$FONT_DIR/$f.part"
  done
  if [[ "$got" -eq 0 ]]; then
    echo "  ✗ ${f} 自动下载失败（网络不可达或镜像变更）"
    missing_comm=1
  fi
done

# ── 收尾 ──────────────────────────────────────────────────────────
echo
if [[ "$missing_open" -eq 1 || "$missing_comm" -eq 1 ]]; then
  cat <<'EOF'
────────────────────────────────────────────────────────────
部分字体未就绪，请按需手动补齐：

【仓耳今楷 02 · 商业字体，商用需自行确认授权】
  1) 官网下载：https://tsanger.cn  → 「仓耳今楷」→ W04 / W05
     重命名为 TsangerJinKai02-W04.ttf / TsangerJinKai02-W05.ttf
     放入上述字体目录
  2) 或从本机已装字体直接复制同名文件

【思源宋体 SC · 开源 SIL OFL 1.1】
  官方发布页：https://github.com/adobe-fonts/source-han-serif/releases
  macOS 亦可：brew install --cask font-source-han-serif-sc

字体缺失不会导致导出失败，但中文会回退到系统衬线字体
（宋体 / Songti SC），与 kami 审美规范的字形存在差异。
────────────────────────────────────────────────────────────
EOF
  exit 1
fi

echo "字体全部就绪 ✓"
