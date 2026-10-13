# Word 排版规范（teaching-plan 的排版参照）

本文件说明 `teaching-plan` 输出 Word 时所依据的排版规范，供需要手工调整或
另写模板时对照。生成脚本：`scripts/make_docx.py`。

## 参照来源

1. **kami 设计规范**（`~/.agents/skills/kami/references/tokens.json` 与
   `CHEATSHEET.md`）——本 skill 在 kami 可用时优先读取其 token，作为 Word 的
   色彩与层次参照。kami 本身输出 HTML/PDF（WeasyPrint），**不产出 Word**，
   因此这里是把它的设计语言移植到 Word 样式，而不是调用它的构建链。
2. **中文正式文档通行排版**——黑体标题 / 宋体正文 / 1.5 倍行距 / 三线表 /
   页眉细分隔线 + 页脚页码。这是高校教案、学术论文、公文里最稳妥、打印最
   友好的组合。

## 色板（来自 kami tokens，均为实色，不使用透明度）

- **墨蓝 `#1B365D`** —— 唯一强调色：文档标题、环节标题、表头文字与表头下细线、标题左侧竖条
- 正文黑 `#141413`
- 次级文字 `#3D3D3A`；说明 `#504E49`；元信息 `#6B6A64`（暖调灰，不用冷灰）
- 分隔线 `#E8E6DC` / `#E5E3D8`
- 表头底纹 `#EEF2F7`（墨蓝 8% 实色化）；提示卡底纹 `#F7F6F1`

强调色刻意只占很小面积——标题竖条、表头、页码线，正文保持黑白，保证打印清晰。

## 样式清单

- **页面**：A4，上下页边距 2.3 / 2.2 cm，左右 2.4 cm
- **页眉**：文档标题，8.5pt 暖灰 `#6B6A64`，下方 0.75pt 分隔线
- **页脚**：居中页码域（PAGE），9pt 暖灰
- **文档标题**（Markdown `#`）：20pt 墨蓝加粗 + 下方 2.25pt 墨蓝横线；标题区可带副标题与元信息行
- **H1**（`##`）：15pt，墨蓝，带 2.75pt 墨蓝左竖条（环节标题）
- **H2**（`###`）：12.5pt，`#3D3D3A`
- **H3**（`####`）：11.5pt，`#504E49`
- **正文**：宋体 11pt，1.5 倍行距，段后 6pt
- **列表**：10.5pt，悬挂缩进，1.45 倍行距
- **提示卡**（Markdown `>`）：10.5pt `#504E49`，左侧 2.25pt 暖灰竖条 + 浅底 `#F7F6F1`
- **表格**：三线表——顶线 / 底线 1.75pt 黑，表头下细线 1pt 墨蓝；表头底纹 `#EEF2F7` 且文字墨蓝加粗；正文单元格 10pt；无竖线、无内部横线
- 所有标题 `keep_with_next`，避免标题孤行落在页底

## 字体体系

| `--style` | 标题（中） | 正文（中） | 西文 |
|---|---|---|---|
| `standard`（默认） | 黑体 | 宋体 | Georgia |
| `kami` | TsangerJinKai02 | Source Han Serif SC | Charter |

- `standard` 是跨平台最稳的选择（Windows 有 SimSun/SimHei，macOS 的 Word 会把
  "宋体/黑体"映射到 Songti SC / Heiti SC）。
- `kami` 更贴近 kami 的衬线视觉，但需要本机装有仓耳今楷与思源宋体（macOS 装
  kami 字体后可用）。
- 需要别的字体时用 `--font-title` / `--font-body` / `--font-ascii` 覆盖。
- 注意：在 LibreOffice / 部分预览器里，"宋体"可能回退为无衬线中文字体；这是
  预览器的字体映射问题，Word 中显示正常。要看最终效果请用 Word/WPS 打开。

## 生成与校验

在课题子目录内执行（教案 md 放在 `源文件/`）：

```bash
cd "教案-<课题>"
python3 ~/.codewhale/skills/teaching-plan/scripts/make_docx.py 源文件/教案-<课题>.md \
  -o 教案-<课题>.docx \
  --title "教案：<课题>" --subtitle "综艺思维六机制 · <课时>" \
  --meta "适用对象：<学段/课程>"
```

`--compact` 用于打印材料包（缩小边距字号、压缩表格内边距，把页数压到最少）；
教案本体不要用。

校验（至少做前两项）：

1. 重新读取生成的 docx，确认段落数、表格行列、页眉标题、标题颜色字号；
2. 转 PDF 确认能正常打开且页数合理：
   `soffice --headless --convert-to pdf --outdir . 教案-<课题>.docx`
3. 视觉：在 Word / WPS 中打开确认三线表、色条、页码（脚本无法替代人眼）。

## 若需要 PDF / 网页版

kami 的长文能力适合把同一份教案再排一版 PDF（`long-doc` 模板）或一页纸讲义
（`one-pager` 模板）。这是可选增强，默认交付仍是 Word。
