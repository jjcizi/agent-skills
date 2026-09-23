[English](#english) | [简体中文](#简体中文)

---

<a id="english"></a>

# person-investigation

A Claude Code skill for systematic person background investigation.

Think like an investigative journalist — don't mechanically follow a checklist. Enter with a clear goal, dynamically adjust direction based on clues discovered at each step, and systematically reconstruct a person's public profile.

---

## v2.0 Capabilities

| Capability | Description |
|------------|-------------|
| Progressive workflow | Disambiguate first, then deep-dive — avoid wasting time on the wrong target |
| 8-dimension research | Education, career, startup/investment, network, public opinions, social media, risk signals, technical background |
| Parallel sub-agent dispatch | Independent dimensions collected in parallel, drastically reducing total time |
| Source credibility grading | 3-tier source labeling (high/medium/low) — distinguishes first-party content, official records, authoritative media, and reposts |
| Bilingual CN/EN search | Auto-generates pinyin variants to cover different naming conventions across platforms |
| Structured report output | Standardized due diligence report template with source attribution; empty dimensions explicitly noted rather than omitted |
| Investigation experience accumulation | Stores research patterns by domain/persona type, reusable across sessions |
| web-access integration | Auto-enables CDP browser capabilities when web-access skill is detected, reaching login-gated platforms |

## Installation

**Option 1: Let Claude auto-install**

```
Install this skill: https://github.com/yuweiwan/person-investigation
```

**Option 2: Manual**

```bash
git clone https://github.com/yuweiwan/person-investigation ~/.claude/skills/person-investigation
```

## Optional Dependencies

| Dependency | Purpose | Required? |
|------------|---------|-----------|
| [web-access](https://github.com/eze-is/web-access) skill | CDP browser automation for login-gated / anti-scraping platforms (Maimai, Xiaohongshu, Jike, etc.) | No — falls back to WebSearch + WebFetch mode without it, but recommended for better coverage |

## Usage

After installation, trigger via natural conversation — the skill takes over automatically:

- "Investigate Zhang San, he's the founder of XX company"
- "Run a background check on [name + company/industry]"
- "Look into XXX's background"
- "Check this person XXX, focus on risk signals"

### Target Personas

Founders, core team members, investors, industry experts, potential partners, etc.

### Research Workflow

1. **Phase 1: Disambiguation & Anchoring** — Identify the unique target; present candidate list for user confirmation when namesakes exist
2. **Phase 2: Deep Research** — Parallel collection across dimensions, clue tracking and cross-verification
3. **Phase 3: Report Generation** — Output structured due diligence report with source attribution and information gap notes

### Platform Coverage

LinkedIn · Maimai · Twitter/X · Zhihu · Jike · Xiaohongshu · Weibo · Tianyancha/Qichacha · ITjuzi/Crunchbase · GitHub · Google Scholar · China Judgments Online

## Design Philosophy

> Skill = Philosophy + Technical Facts, not a step-by-step manual. Define goals and principles, let the AI decide how to execute.

- **Think like an investigative journalist**: Every search result is a clue entry point, not just a binary "found or not" signal
- **Primary sources over secondary**: Search engines are discovery entry points, not evidence sources
- **Circular corroboration ≠ multi-source verification**: Three articles saying the same thing doesn't mean three independent sources — check if they cite the same origin
- **Don't fabricate for completeness**: If not found, label "no public information found" — don't speculate

See the Research Philosophy section in [SKILL.md](./SKILL.md) for details.

## Privacy & Compliance

- Only uses publicly available information
- No illegal information gathering
- Sensitive information (family member details, personal addresses) not actively collected
- Full transparency on information sources in reports, letting users assess on their own

## License

MIT · Author: [Yuwei Wan](https://github.com/yuweiwan)

---

<a id="简体中文"></a>

# person-investigation

给 Claude Code 装上人物背景尽调能力的 skill。

像调查记者一样思考——不是机械地按清单搜索，而是带着明确目标进入，根据每一步发现的线索动态调整方向，系统性地还原一个人的公开画像。

---

## v2.0 能力

| 能力 | 说明 |
|------|------|
| 渐进式工作流 | 先消歧锚定再深入，避免在错误目标上浪费调研时间 |
| 8 维度系统调研 | 教育经历、职业轨迹、创业/投资、关系网络、公开观点、社交媒体、风险信号、技术背景 |
| 并行子 Agent 分治 | 多维度独立信息采集并行执行，大幅缩短总耗时 |
| 信息可信度分级 | 高/中/低三级来源标注，区分本人直接产出、官方记录、权威媒体、转载报道 |
| 中英文双语搜索 | 自动生成拼音变体，覆盖不同平台的命名习惯 |
| 结构化报告输出 | 标准化的尽调报告模板，每条关键信息标注来源，空维度明确标注而非省略 |
| 调研经验积累 | 按域名/人物类型存储调研经验，跨 session 复用 |
| web-access 联动 | 检测到 web-access skill 时自动启用 CDP 浏览器能力，触达需登录态的平台 |

## 安装

**方式一：让 Claude 自动安装**

```
帮我安装这个 skill：https://github.com/yuweiwan/person-investigation
```

**方式二：手动**

```bash
git clone https://github.com/yuweiwan/person-investigation ~/.claude/skills/person-investigation
```

## 可选依赖

| 依赖 | 用途 | 是否必须 |
|------|------|---------|
| [web-access](https://github.com/eze-is/web-access) skill | CDP 浏览器操作，触达需登录态/反爬严格的平台（脉脉、小红书、即刻等） | 否，无此 skill 时自动降级为 WebSearch + WebFetch 模式，但仍建议配备更好的搜索工具 |

## 使用

安装后直接对话触发，skill 自动接管：

- "帮我调查张三，他是 XX 公司的创始人"
- "对这个人进行尽调：[姓名 + 公司/行业]"
- "了解一下 XXX 的背景"
- "查一下 XXX 这个人，重点看风险信号"

### 适用对象

创始人、核心团队成员、投资人、行业专家、潜在合作伙伴等。

### 调研流程

1. **阶段 1：消歧与锚定** — 确定唯一调研对象，同名者呈现候选列表让用户确认
2. **阶段 2：深度调研** — 按维度并行采集，线索追踪与交叉验证
3. **阶段 3：报告生成** — 输出结构化尽调报告，含来源标注和信息缺口说明

### 常用平台覆盖

LinkedIn · 脉脉 · Twitter/X · 知乎 · 即刻 · 小红书 · 微博 · 天眼查/企查查 · IT桔子/Crunchbase · GitHub · Google Scholar · 裁判文书网

## 设计哲学

> Skill = 哲学 + 技术事实，不是操作手册。讲清目标和原则让 AI 自己判断，不替它规定每一步怎么做。

- **像调查记者一样思考**：每条搜索结果都是线索入口，不只是"有或没有"的二元信号
- **一手信息优于二手信息**：搜索引擎是发现入口，不是证据来源
- **循环印证 ≠ 多源验证**：三篇文章说同一件事，需看它们是否引用了同一个源头
- **不为完整而编造**：未找到就标注"未找到公开信息"，不猜测

详见 [SKILL.md](./SKILL.md) 中的调研哲学部分。

## 隐私与合规

- 仅使用公开可获取的信息
- 不进行非法信息获取
- 敏感信息（家庭成员详情、个人住址）不主动收集
- 报告中对信息来源透明，让用户自行评估

## License

MIT · 作者：[Yuwei Wan](https://github.com/yuweiwan)
