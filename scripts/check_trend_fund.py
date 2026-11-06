#!/usr/bin/env python3
"""获取30分钟趋势和主力资金数据"""
import akshare as ak
import pandas as pd

# 持仓列表 (名称, 代码, 市场)
holdings = [
    ("科创50ETF华夏", "588000", "sh"),
    ("贵州茅台", "600519", "sh"),
    ("新易盛", "300502", "sz"),
    ("创业板ETF广发", "159952", "sh"),
    ("英维克", "002837", "sz"),
    ("中国核建", "601611", "sh"),
]

def get_30min_trend(code, market):
    """获取30分钟K线数据判断短期趋势"""
    try:
        df = ak.stock_zh_a_hist_min_em(symbol=code, period='30', start_date='20260506', adjust='qfq')
        if df is None or len(df) < 2:
            return None
        
        # 取最后4根K线
        recent = df.tail(4)
        closes = recent['收盘'].tolist()
        
        if len(closes) < 2:
            return None
        
        change_pct = (closes[-1] - closes[0]) / closes[0] * 100
        
        # 检测V型反弹
        low_idx = closes.index(min(closes))
        v_shape = False
        if low_idx > 0 and low_idx < len(closes) - 1:
            if closes[-1] >= max(closes[:low_idx+1]) * 0.998:
                v_shape = True
        
        if change_pct > 1:
            trend = "上升"
        elif change_pct < -1:
            trend = "下降"
        else:
            trend = "中性"
        
        return {"trend": trend, "change_pct": change_pct, "v_shape": v_shape}
    except Exception as e:
        return None

def get_main_fund(code, market):
    """获取主力资金净流入"""
    try:
        df = ak.stock_individual_fund_flow(stock=code, market=market)
        if df is None or len(df) < 1:
            return None
        
        # 取最新一行
        latest = df.iloc[-1]
        
        # 尝试找主力净流入相关列
        main_net = 0
        for col in df.columns:
            if '主力净流入' in col and '净额' in col:
                main_net = float(latest[col]) if pd.notna(latest[col]) else 0
                break
        
        return {"main_net_flow": main_net}
    except Exception as e:
        return None

print("=" * 80)
print("【持仓股短期趋势与主力资金分析】 2026-05-06 10:20")
print("=" * 80)

for name, code, market in holdings:
    print(f"\n📊 {name} ({code})")
    print("-" * 40)
    
    # 30分钟趋势
    trend_data = get_30min_trend(code, market)
    if trend_data:
        v_msg = " (V型反弹)" if trend_data.get("v_shape") else ""
        print(f"  30分钟趋势: {trend_data['trend']} ({trend_data['change_pct']:+.2f}%){v_msg}")
    else:
        print(f"  30分钟趋势: 暂无数据")
    
    # 主力资金
    fund_data = get_main_fund(code, market)
    if fund_data:
        flow = fund_data['main_net_flow']
        if flow > 1000:
            print(f"  主力资金: 🟢 净流入 {flow/10000:.2f} 亿元 ({flow:.0f}万元)")
        elif flow < -1000:
            print(f"  主力资金: 🔴 净流出 {abs(flow)/10000:.2f} 亿元")
        else:
            print(f"  主力资金: 🟡 基本持平")
    else:
        print(f"  主力资金: 暂无数据")

print("\n" + "=" * 80)
print("注: 资金流向数据可能滞后，仅供参考")