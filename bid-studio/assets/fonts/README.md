# 字体清单与获取方式（kami 排版所需）

本目录承载 bid-studio（kami 审美排版）所需字体。

**分发策略**：开源字体随仓库内置，开箱即用；**商业字体不入库**，由准备脚本在本地按需获取——既保证克隆即可用，也避免把需授权的字体打包分发。

## 一键准备（推荐）

```bash
# 在 bid-studio 技能根目录执行，可重复执行
bash scripts/ensure-fonts.sh
```

脚本做三件事：

1. 核对**开源字体**是否齐全（缺失则提示补齐方式）；
2. **仓耳今楷 02**（W04 / W05）缺失时，自动从 CDN 镜像下载（官方直链已失效，脚本以镜像为主力）；
3. 仍有字体缺失时，打印手动获取指引——**不阻断使用**，中文会回退到思源宋体 SC / 系统衬线字体。

技能目录只读时，指定可写目录：

```bash
BIDSTUDIO_FONT_DIR=~/.local/share/fonts/bid-studio bash scripts/ensure-fonts.sh
```

## 字体清单

- `SourceHanSerifSC-Regular.otf` — 思源宋体 SC Regular — 中文回退（400 字重）— SIL OFL 1.1 — **仓库内置**
- `SourceHanSerifSC-Medium.otf` — 思源宋体 SC Medium — 中文回退（500 字重，匹配 kami「锁 500 不加粗」）— SIL OFL 1.1 — **仓库内置**
- `JetBrainsMono.woff2` — JetBrains Mono — 等宽（代码 / 编号 / 金额）— SIL OFL 1.1 — **仓库内置**
- `TsangerJinKai02-W04.ttf` — 仓耳今楷 02（W04）— 中文衬线标题 + 正文（主字体）— 商业字体（仓耳字库）— **不入库，脚本下载**
- `TsangerJinKai02-W05.ttf` — 仓耳今楷 02（W05）— 中文衬线（主字体，另一字重子集）— 商业字体（仓耳字库）— **不入库，脚本下载**

> 本仓库不包含商业字体仓耳今楷 02（单文件约 18MB，且商用需授权）。请用 `scripts/ensure-fonts.sh` 或下方手动方式在本地获取。

## 手动获取

**仓耳今楷 02（商业字体，商用请先确认授权）**

1. 官网 <https://tsanger.cn> 下载 W04 / W05 字重；
2. 重命名为 `TsangerJinKai02-W04.ttf` / `TsangerJinKai02-W05.ttf`，放入本目录；
3. 或从本机其它已装字体 / kami 技能中复制同名文件。

**思源宋体 SC（开源，SIL OFL 1.1）**

- 官方发布：<https://github.com/adobe-fonts/source-han-serif/releases>（取 `OTF/SimplifiedChinese/`）
- macOS 亦可：`brew install --cask font-source-han-serif-sc`

## 字体栈（与 SKILL.md 排版审美规范一致）

- 中文衬线：`TsangerJinKai02` → `Source Han Serif SC` → `Noto Serif CJK SC` → `Songti SC` → `STSong` → `SimSun`
- 英文衬线：`Charter` → `Georgia` → `Palatino` → `Times New Roman`
- 等宽：`JetBrains Mono` → `SF Mono` → `Consolas` → `Monaco`

## 使用方式

- **Word（.docx）**：导出前将 `*.ttf` / `*.otf` 安装到系统（Windows 双击安装），或让 Word 内嵌字体（「文件 → 选项 → 保存 → 将字体嵌入文件」），保证跨机器显示一致。
- **PDF（HTML 渲染）**：通过 `@font-face` 引用本目录相对路径即可，无需系统安装；WeasyPrint / Chromium 均能加载本地字体文件。
- **PDF（Word 导出）**：依赖 Word 中已安装的字体，导出时勾选「嵌入字体」。

## 授权说明（务必阅读）

- **仓耳今楷 02（TsangerJinKai02）**：商业字体，版权归仓耳字库（Tsanger）所有。**本仓库不分发该字体**，仅由使用脚本在本机按需获取，供本地排版使用；**商业使用前请确认并遵循仓耳字库的授权要求**，本技能不承担字体商用授权责任。若无法获得授权，直接用内置的思源宋体 SC 即可（审美同为衬线风格）。
- **思源宋体（Source Han Serif SC）**：Adobe 出品，SIL Open Font License 1.1，可自由使用、复制、修改、再分发（须保留版权声明与 OFL 文本）。本仓库随附 `LICENSE-SourceHanSerifK.txt`。
- **JetBrains Mono**：JetBrains 出品，SIL Open Font License 1.1，可自由使用。

## 来源

- 思源宋体 SC：Adobe 官方仓库 [adobe-fonts/source-han-serif](https://github.com/adobe-fonts/source-han-serif)（`OTF/SimplifiedChinese/`），随本仓库分发。
- JetBrains Mono、`LICENSE-SourceHanSerifK.txt`：来自开源项目 [tw93/Kami](https://github.com/tw93/Kami)。
- 仓耳今楷 02：由 `scripts/ensure-fonts.sh` 从 [tw93/Kami](https://github.com/tw93/Kami) 的 CDN 镜像获取（官方 tsanger.cn 直链已失效）；亦可从仓耳字库官网手动下载。
