# llm-config

大模型试水配置 —— OpenClaw 工作区根目录的配置、脚本与工具沉淀。

本仓库从 `~/.openclaw/workspace` 根目录抽取，托管**不属于任何独立子项目**的部分。各子项目（游戏、题库、赛程等）各自独立建仓，本仓库不重复跟踪。

## 📁 目录结构

| 路径 | 说明 |
|------|------|
| `AGENTS.md` | 工作区选取规则（A股 / 小红书分流）、Web 工具选型策略 |
| `SOUL.md` | 助理人格、输出风格硬性规则 |
| `IDENTITY.md` | 助理职责边界、常用工作流 |
| `USER.md` | 用户画像、沟通偏好、定时任务时间表 |
| `TOOLS.md` | 本地环境备注（相机 / SSH / TTS 等） |
| `HEARTBEAT.md` | 心跳任务配置 |
| `stock-scripts/` | A 股脚本：反弹筛选、板块分析、行情抓取、盘报生成 |
| `scripts/` | 报告调度与策略脚本：早/晚报、买卖信号、三重评分 |
| `reports/supply-chain-bottleneck/` | 供应链瓶颈分析报告存档 |
| `game-design/` | 游戏设计方案文档 |
| `frontend/` | 前端组件（ThinkingBlock 等） |
| `wheel/` | 轮盘决策工具 |
| `regex-tool.html` | 正则测试工具 |
| `*.csv` | 分析结果缓存（反弹候选、板块预测） |

## 🚫 不入库内容

- **子项目目录**：`english-quiz/` `gomoku/` `monopoly/` `uno/` `echoes-of-eternity/` `renovation-guide/` `llm-review/` `schedule/` `daily-stock-analysis/` —— 各自独立仓库
- **个人记忆**：`memory/` `memory-flip/` `state/`（含持仓、交易记录、日记）
- **技能库**：`skills/`（内部资产）
- **股票数据**：`stock/`（约 302MB）
- **运行时产物**：`__pycache__/` `*.log` `*.db`

## 🛠 使用

```bash
git clone https://github.com/flyfire1987/llm-config.git
cd llm-config
pip install akshare requests pandas
```

A 股脚本数据源：`akshare` / 腾讯行情接口 / 财联社。

## 📅 更新记录

- 2026-11-06: 初始化仓库，从 workspace 根目录抽取配置与脚本
