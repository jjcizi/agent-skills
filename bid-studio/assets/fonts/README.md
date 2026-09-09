# 内置字体清单（kami 排版所需）

> ⚠️ **本仓库分发版不含大于 10MB 的字体文件**（仓耳今楷 02 TTF、思源宋体 OTF）。请按下方「来源」自行下载后放入本目录，否则 Word/PDF 导出将回退到思源宋体 SC / 系统默认字体。

本目录内置 kami 排版审美体系所需的核心字体，导出 Word/PDF 时无需联网即可使用。

## 字体清单

| 文件 | 字体名 | 用途 | 授权 |
|------|--------|------|------|
| `TsangerJinKai02-W04.ttf` | 仓耳今楷 02（W04） | 中文衬线标题 + 正文（主字体） | 商业字体，版权归仓耳字库（Tsanger） |
| `TsangerJinKai02-W05.ttf` | 仓耳今楷 02（W05） | 中文衬线（主字体，另一字重子集） | 商业字体，版权归仓耳字库（Tsanger） |
| `SourceHanSerifSC-Regular.otf` | 思源宋体 SC（Regular） | 中文回退（400 字重） | SIL Open Font License 1.1 |
| `SourceHanSerifSC-Medium.otf` | 思源宋体 SC（Medium） | 中文回退（500 字重，匹配 kami「锁 500 不加粗」） | SIL Open Font License 1.1 |
| `JetBrainsMono.woff2` | JetBrains Mono | 等宽（代码 / 编号 / 金额） | SIL Open Font License 1.1 |

## 字体栈（与 SKILL.md 排版审美规范一致）

- 中文衬线：`TsangerJinKai02` → `Source Han Serif SC` → `Noto Serif CJK SC` → `Songti SC` → `STSong` → `SimSun`
- 英文衬线：`Charter` → `Georgia` → `Palatino` → `Times New Roman`
- 等宽：`JetBrains Mono` → `SF Mono` → `Consolas` → `Monaco`

## 使用方式

- **Word（.docx）**：导出前将 `*.ttf` / `*.otf` 安装到系统（Windows 双击安装），或让 Word 内嵌字体（「文件 → 选项 → 保存 → 将字体嵌入文件」），保证跨机器显示一致。
- **PDF（HTML 渲染）**：通过 `@font-face` 引用本目录相对路径即可，无需系统安装；WeasyPrint / Chromium 均能加载本地字体文件。
- **PDF（Word 导出）**：依赖 Word 中已安装的字体，导出时勾选「嵌入字体」。

## 授权说明（务必阅读）

- **仓耳今楷 02（TsangerJinKai02）**：商业字体，版权归仓耳字库（Tsanger）所有。本副本来源于开源项目 [tw93/Kami](https://github.com/tw93/Kami)（MIT 分发）。用于个人 / 本地排版预览无碍；**商业使用前请确认并遵循仓耳字库的授权要求**，本技能不承担字体商用授权责任。
- **思源宋体（Source Han Serif SC）**：Adobe 出品，SIL Open Font License 1.1，可自由使用、复制、修改、再分发（须保留版权声明与 OFL 文本）。
- **JetBrains Mono**：JetBrains 出品，SIL Open Font License 1.1，可自由使用。

## 来源

- 仓耳今楷 02、JetBrains Mono、LICENSE-SourceHanSerifK.txt：来自本地已安装的 kami 技能 `assets/fonts/`。
- 思源宋体 SC：下载自 Adobe 官方仓库 [adobe-fonts/source-han-serif](https://github.com/adobe-fonts/source-han-serif)（`release` 分支，`OTF/SimplifiedChinese/`）。
