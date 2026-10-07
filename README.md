# Agent Skills Collection

个人 Agent 技能集合，适用于 MiMoCode / Claude Code / OpenCode 等 AI 编码助手。

## 技能列表

| 技能 | 说明 | 安装路径 |
|------|------|----------|
| [university-lecture](university-lecture/) | 模拟顶尖大学优秀教师，6步逻辑闭环课堂精讲，输出自包含 HTML 讲义（含 SVG 可视化） | `.agents/skills/university-lecture/` |
| [bid-studio](bid-studio/) | 标书超级工坊——投标全生命周期一站式技能，融合招标解析、条款级响应、废标项检查、kami 排版审美与图表绘制，支持 Word/PDF 交付 | `.agents/skills/bid-studio/` |
| [teaching-plan](teaching-plan/) | 把知识点或教材章节转成"综艺思维"教案——用悬念/身份/反转/站队/盲盒/复盘六机制设计课堂节奏，输出教案 Word、投屏 PPT、打印材料包与材料清单 | `.agents/skills/teaching-plan/` |
| [logic-diagram](logic-diagram/) | 把一段文字内容套进 141 页专业逻辑图模板（孔雀蓝），按内容逻辑匹配候选版式，替换文字后输出 PPTX/PDF/PNG | `.agents/skills/logic-diagram/` |
| [person-investigation](person-investigation/) | 人物背景尽调——消歧锚定、8 维度调研、并行子 Agent、来源可信度分级与结构化尽调报告 | `.agents/skills/person-investigation/` |

## 安装方法

### 方法一：克隆整个仓库（推荐）

```bash
git clone https://github.com/jjcizi/agent-skills.git

# 按需复制单个技能
cp -r agent-skills/university-lecture ~/.agents/skills/
```

### 方法二：单独下载某个技能

进入对应技能目录，下载 `SKILL.md`，放入本地 skills 目录即可：

```
~/.agents/skills/<skill-name>/SKILL.md
```

### 技能发现目录（任选其一）

| 工具 | 技能目录 |
|------|----------|
| MiMoCode | `.agents/skills/`、`.codex/skills/`、`.opencode/skill(s)/` |
| Claude Code | `.claude/skills/` |

## 外部依赖

技能本体只是 Markdown + Python 脚本，但部分技能需要额外的运行时组件——**请自行安装**。

**logic-diagram（逻辑图）**

```bash
pip install python-pptx pymupdf pillow
```

- `python-pptx` —— 读写 PPTX
- `PyMuPDF`（`import fitz`）—— PPTX→PDF→PNG 与字体排查
- `Pillow` —— 图片处理
- **LibreOffice**（提供 `soffice`）—— 负责 PPTX→PDF 渲染
  - macOS：`brew install --cask libreoffice`
  - Ubuntu：`sudo apt install libreoffice`
  - 其他：<https://www.libreoffice.org/download/>
  - 装在非标准路径时：`export SOFFICE=/path/to/soffice`

字体已随包放在 `logic-diagram/assets/fonts/`（**Noto Sans SC**，SIL OFL 1.1，
可自由再分发），首次出图会自动装入用户字体目录，无需手动下载。

## 添加新技能

```bash
git clone https://github.com/jjcizi/agent-skills.git
cd agent-skills

mkdir new-skill-name
# 将 SKILL.md 放入 new-skill-name/

git add .
git commit -m "feat: add new-skill-name"
git push
```

---

> 技能持续更新中。
