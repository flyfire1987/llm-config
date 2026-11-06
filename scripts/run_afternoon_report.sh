#!/bin/bash
# run_afternoon_report.sh - 运行财经午报并发送QQ
# 用法: bash run_afternoon_report.sh

set -e
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export PYTHONIOENCODING=utf-8

WS=/root/.openclaw/workspace
LOG_DIR=$WS/logs/afternoon_report
mkdir -p "$LOG_DIR"

TS=$(date +%Y%m%d_%H%M%S)
LOG_FILE=$LOG_DIR/report_${TS}.log

echo "[$(date '+%F %T')] 财经午报开始执行" | tee "$LOG_FILE"

# 1. 运行数据采集脚本
REPORT=$($WS/scripts/afternoon_news_report.py 2>>"$LOG_FILE" || echo "⚠️ 午报脚本执行失败，请查看日志: $LOG_FILE")

if [ -z "$REPORT" ]; then
    REPORT="⚠️ 财经午报生成失败，请检查日志：$LOG_FILE"
fi

# 2. 持久化报告
REPORT_FILE=$LOG_DIR/report_${TS}.md
echo "$REPORT" > "$REPORT_FILE"
echo "[$(date '+%T')] 报告已保存: $REPORT_FILE" >> "$LOG_FILE"

# 3. 清理旧日志（保留最近30天）
find "$LOG_DIR" -name "*.log" -mtime +30 -delete 2>/dev/null
find "$LOG_DIR" -name "*.md" -mtime +30 -delete 2>/dev/null

# 4. 输出报告（agentTurn 会捕获这个输出并推送给用户）
echo "$REPORT"

# 5. 输出元数据
echo ""
echo "----"
echo "✅ 执行成功 | 日志: $LOG_FILE | 报告: $REPORT_FILE"
