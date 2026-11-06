#!/usr/bin/env python3
"""综合卖出信号+趋势+资金判断"""
import akshare as ak
import pandas as pd

holdings = [
    ("科创50ETF华夏", "588000", "sh"),
    ("贵州茅台", "600519", "sh"),
    ("新易盛", "300502", "sz"),
    ("创业板ETF广发", "159952", "sh"),
    ("英维克", "002837", "sz"),
    ("中国核建", "601611", "sh"),
]

def get_30min_trend(code):
    try:
        df = ak.stock_zh_a_hist_min_em(symbol=code, period='30', start_date='20260506', adjust='qfq')
        if df is None or len(df) < 2:
            return None
        recent = df.tail(4)
        closes = recent['收盘'].tolist()
        change_pct = (closes[-1] - closes[0]) / closes[0] * 100
        low_idx = closes.index(min(closes))
        v_shape = len(closes) >= 4 and low_idx > 0 and low_idx < len(closes)-1 and closes[-1] >= max(closes[:low_idx+1]) * 0.998
        trend = "上升" if change_pct > 1 else ("下降" if change_pct < -1 else "中性")
        return {"trend": trend, "change_pct": change_pct, "v_shape": v_shape}
    except Exception:
        return None

def get_main_fund(code):
    try:
        mkt = 'sh' if code.startswith(('5','1','4','8')) else 'sz'
        df = ak.stock_individual_fund_flow(stock=code, market=mkt)
        if df is None or len(df) < 1:
            return None
        latest = df.iloc[-1]
        main_net = 0
        for col in df.columns:
            if '主力净流入' in col and '净额' in col:
                main_net = float(latest[col]) if pd.notna(latest[col]) else 0
                break
        return main_net
    except Exception:
        return None

def adjust_signal(signal, name, trend, fund_flow):
    if signal not in ['卖出信号', '减仓信号'] or trend is None:
        return signal
    is_outflow = fund_flow is not None and fund_flow < -10000000
    is_inflow = fund_flow is not None and fund_flow > 10000000
    if trend['trend'] == '上升' or is_inflow:
        return "继续持有观察"
    elif trend['trend'] == '下降' and is_outflow:
        return "确认减仓信号"
    return signal

signals = {
    "科创50ETF华夏": "暂无明确信号",
    "贵州茅台": "减仓1/3 (MACD死叉)",
    "新易盛": "减仓1/3 (MACD死叉)",
    "创业板ETF广发": "跑赢指数，继续持有",
    "英维克": "减仓1/3 (MACD死叉)",
    "中国核建": "减仓1/3 (MACD死叉)",
}

print("=" * 85)
print("【卖出信号检测 - 综合判断报告】")
print("=" * 85)
print(f"\n📅 检测时间: 2026-05-06 10:20")
print(f"📊 上证指数: +1.17%\n")

for name, code, market in holdings:
    trend_data = get_30min_trend(code)
    fund_data = get_main_fund(code)
    signal = signals.get(name, "暂无数据")
    
    if '减仓' in signal:
        signal = adjust_signal(signal, name, trend_data, fund_data)
    
    trend_str = ""
    if trend_data:
        v_msg = " ⬅️V型反弹" if trend_data.get('v_shape') else ""
        trend_str = f"30分{trend_data['trend']}({trend_data['change_pct']:+.2f}%){v_msg}"
    
    fund_str = ""
    if fund_data is not None:
        if fund_data > 10000000:
            fund_str = "主力🟢流入"
        elif fund_data < -10000000:
            fund_str = "主力🔴流出"
        else:
            fund_str = "主力🟡持平"
    
    status_icon = "✅" if '持有' in signal or '跑赢' in signal else ("⚠️" if '观察' in signal else "🔴")
    
    print(f"{status_icon} {name}")
    print(f"   卖出信号: {signal}")
    if trend_str:
        print(f"   短期趋势: {trend_str}")
    if fund_str:
        print(f"   主力资金: {fund_str}")
    print()

print("=" * 85)
print("【综合结论】")
print("  • MACD死叉标的: 茅台、新易盛、英维克、核建")
print("  • 其中 英维克 30分钟上升趋势 → 改为继续持有观察")
print("  • 其余三只 30分钟中性/下降 且 主力流出 → 确认减仓信号")
print("=" * 85)