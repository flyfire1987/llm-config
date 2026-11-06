#!/usr/bin/env python3
"""短期趋势 + 主力资金分析"""
import sys
sys.path.insert(0, '/root/.openclaw/workspace')

import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# 持仓
holdings = [
    {"name": "赤峰黄金", "code": "600988"},
    {"name": "晓程科技", "code": "300139"},
    {"name": "四川黄金", "code": "001337"},
    {"name": "贵州茅台", "code": "600519"},
    {"name": "中国核建", "code": "601611"},
    {"name": "湖南白银", "code": "002716"},
]

def get_30min_trend(code):
    """获取30分钟趋势"""
    try:
        # 东方财富 30分钟数据
        df = ak.stock_zh_a_minute_em(symbol=code, period="30")
        if df is None or df.empty:
            return None, None
        
        # 取最近10个30分钟数据
        df = df.tail(10).copy()
        
        # 计算涨跌
        closes = df['close'].values
        if len(closes) < 3:
            return None, None
        
        # 最近3个30分钟的方向
        recent = closes[-3:]
        if recent[2] > recent[1] > recent[0]:
            trend = "上升📈"
        elif recent[2] < recent[1] < recent[0]:
            trend = "下降📉"
        elif closes[-1] > closes[0]:
            trend = "中性偏上↗"
        elif closes[-1] < closes[0]:
            trend = "中性偏下↘"
        else:
            trend = "中性→"
        
        # V型反弹检测
        if len(closes) >= 5:
            low_idx = closes.argmin()
            if low_idx >= 2 and low_idx <= 4:
                # 在最后几个周期内出现低点
                if closes[-1] > closes[low_idx]:
                    trend = "V型反弹↩"
        
        pct = (closes[-1] - closes[0]) / closes[0] * 100
        return trend, pct
    except Exception as e:
        return None, None

def get_main_fund(code):
    """获取当日主力资金净流入"""
    try:
        # 东方财富资金流
        df = ak.stock_individual_fund_flow(stock=code)
        if df is None or df.empty:
            return None, None
        
        latest = df.iloc[-1]
        # 超大单净流入 + 大单净流入
        super_big = float(latest.get('超大单净流入额(万)', 0) or 0)
        big = float(latest.get('大单净流入额(万)', 0) or 0)
        net = super_big + big
        
        return net, abs(net)
    except Exception as e:
        return None, None

print("=" * 70)
print("📊 短期趋势 + 主力资金 综合分析")
print("=" * 70)

results = []
for stock in holdings:
    name = stock["name"]
    code = stock["code"]
    
    # 格式化股票代码
    if code.startswith("6"):
        sym = f"sh{code}"
    else:
        sym = f"sz{code}"
    
    trend, trend_pct = get_30min_trend(code)
    net_flow, net_abs = get_main_fund(code)
    
    # 判断
    signal = "待定"
    action = ""
    
    if trend and net_flow is not None:
        if "上升" in trend or "V型" in trend or (net_flow > 0 and "偏上" in trend):
            signal = "🟢继续持有观察"
            action = "短期趋势向好/主力净流入，暂不减仓"
        elif "下降" in trend and net_flow < 0:
            signal = "🔴确认减仓信号"
            action = f"30分钟{trend}，主力净流出{net_abs:.2f}万"
        else:
            signal = "🟡谨慎持有"
            action = f"趋势{trend}，主力{'净流入' if net_flow>0 else '净流出'}{abs(net_flow):.2f}万"
    elif trend:
        signal = "🟡趋势参考"
        action = f"30分钟{trend}"
    else:
        signal = "⚪数据不足"
        action = "无法获取短期数据"
    
    results.append({
        "name": name,
        "code": code,
        "trend": trend or "未知",
        "trend_pct": trend_pct,
        "net_flow": net_flow,
        "net_abs": net_abs,
        "signal": signal,
        "action": action
    })
    
    flow_str = f"{net_flow:.2f}万" if net_flow is not None else "无数据"
    print(f"\n📌 {name}({code})")
    print(f"   30分钟趋势: {trend or '获取失败'} {f'({trend_pct:+.2f}%)' if trend_pct is not None else ''}")
    print(f"   主力资金: {'净流入🔴' if net_flow and net_flow > 0 else '净流出🟢'} {flow_str}")
    print(f"   → {signal}")
    print(f"   建议: {action}")

print("\n" + "=" * 70)
print("📋 综合建议汇总")
print("=" * 70)
for r in results:
    print(f"  {r['name']}({r['code']}): {r['signal']} - {r['action']}")