# AGENTS.md - 工作区配置

## Workspace 选取规则

| 场景 | Workspace |
|------|-----------|
| A股、股票、投资相关 | 默认 workspace (`~/.openclaw/workspace`) |
| 小红书、发帖子、内容创作 | workspace-xhs (`~/.openclaw/workspace-xhs`) |

## 文件结构

### workspace (A股)
```
~/.openclaw/workspace/
├── SOUL.md
├── USER.md
├── AGENTS.md
├── memory/
└── skills/
```

### workspace-xhs (小红书)
```
~/.openclaw/workspace-xhs/
├── SOUL.md
├── USER.md
├── AGENTS.md
├── memory/
└── skills/
```

## 规则说明

1. **A股相关**：板块分析、个股诊断、持仓更新、行情查询
2. **小红书相关**：文案生成、封面制作、内容发布、搜索互动

## 更新记录

- 2026-03-10: 创建规则









<!-- WEB-TOOLS-STRATEGY-START -->
### Web Tools Strategy (CRITICAL)

**Before using web_search/web_fetch/browser/opencli, you MUST `read workspace/skills/web-tools-guide/SKILL.md`!**

**Four tools, branch by scenario (NOT a hierarchy):**
```
web_search  -> No URL, need to search info         ─┐
web_fetch   -> Known URL, static content            ─┤ Primary (pick by scenario)
                                                     │
opencli     -> Either fails? CLI structured access  ─┤ Fallback (try before browser)
browser     -> All above fail? Full browser control ─┘ Last resort
```

**When web_search/web_fetch fail**: try `opencli` first (70+ sites, `opencli --help` to discover). Only escalate to `browser` when opencli also can't handle it.

**When web_search errors: You MUST read the skill's "web_search failure handling" section first, guide user to configure search API. Only fall back after user explicitly refuses.**
<!-- WEB-TOOLS-STRATEGY-END -->
