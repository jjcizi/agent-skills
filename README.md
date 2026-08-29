# Agent Skills Collection

个人 Agent 技能集合，适用于 MiMoCode / Claude Code / OpenCode 等 AI 编码助手。

## 技能列表

| 技能 | 说明 | 安装路径 |
|------|------|----------|
| [university-lecture](university-lecture/) | 模拟顶尖大学优秀教师，6步逻辑闭环课堂精讲，输出自包含 HTML 讲义（含 SVG 可视化） | `.agents/skills/university-lecture/` |

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
