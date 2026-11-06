#!/usr/bin/env python3
"""
卖出信号检测脚本 v3（增强版）
包含完整技术指标和卖出信号
"""

import requests
import re
import akshare as ak
import pandas as pd
from datetime import datetime

HOLDINGS_FILE = "/root/.openclaw/workspace/data/holdings.txt"

def load_holdings():
    """加载持仓数据"""
    holdings = []
    with open(HOLDINGS_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                parts = line.split(',')
                if len(parts) >= 5:
                    holdings.append({
                        'name': parts[0],
                        'code': parts[1],
                        'cost': float(parts[2]),
                        'stop_loss': float(parts[3]),
                        'profit_target': float(parts[4]),
                    })
    return holdings

def get_realtime_price(code):
    """获取实时价格"""
    try:
        if code.startswith('6'):
            qcode = f"sh{code}"
        else:
            qcode = f"sz{code}"
        
        url = f"https://qt.gtimg.cn/q={qcode}"
        resp = requests.get(url, timeout=5)
        fields = resp.text.split('"')[1].split('~')
        price = float(fields[3])
        prev_close = float(fields[4])
        pct = (price - prev_close) / prev_close * 100
        turnover = float(fields[38]) if fields[38] and fields[38] != '-' else 0
        return price, pct, turnover
    except:
        return None, None, None

def get_technical(code):
    """获取技术指标"""
    try:
        if code.startswith('6') or code.startswith('5'):
            market = "sh" + code
        else:
            market = "sz" + code
        
        df = ak.stock_zh_a_daily(symbol=market, adjust="qfq")
        df = df.tail(60)
        
        closes = df['close']
        highs = df['high']
        lows = df['low']
        
        # MA
        ma5 = closes.rolling(5).mean().iloc[-1]
        ma10 = closes.rolling(10).mean().iloc[-1]
        ma20 = closes.rolling(20).mean().iloc[-1]
        ma60 = closes.rolling(60).mean().iloc[-1] if len(closes) >= 60 else None
        
        # MACD
        ema12 = closes.ewm(span=12, adjust=False).mean()
        ema26 = closes.ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()
        macd_bar = 2 * (dif - dea)
        
        # KDJ
        period = 9
        highest = highs.rolling(period).max()
        lowest = lows.rolling(period).min()
        rsv = (closes - lowest) / (highest - lowest) * 100
        k = rsv.ewm(com=2, adjust=False).mean()
        d = k.ewm(com=2, adjust=False).mean()
        j = 3 * k - 2 * d
        
        # RSI
        delta = closes.diff()
        gain = delta.where(delta > 0, 0)
        loss = (-delta).where(delta < 0, 0)
        avg_gain = gain.ewm(com=13, adjust=False).mean()
        avg_loss = loss.ewm(com=13, adjust=False).mean()
        rs = avg_gain / avg_loss
        rsi = (100 - (100 / (1 + rs))).iloc[-1]
        
        # BBR (布林带)
        bbr_mid = closes.rolling(20).mean()
        bbr_std = closes.rolling(20).std()
        bbr_upper = (bbr_mid + 2 * bbr_std).iloc[-1]
        bbr_lower = (bbr_mid - 2 * bbr_std).iloc[-1]
        bbr_mid_v = bbr_mid.iloc[-1]
        
        current = closes.iloc[-1]
        
        return {
            'ma5': ma5,
            'ma10': ma10,
            'ma20': ma20,
            'ma60': ma60,
            'dif': dif.iloc[-1],
            'dea': dea.iloc[-1],
            'macd_bar': macd_bar.iloc[-1],
            'k': k.iloc[-1],
            'd': d.iloc[-1],
            'j': j.iloc[-1],
            'rsi': rsi,
            'bbr_upper': bbr_upper,
            'bbr_mid': bbr_mid_v,
            'bbr_lower': bbr_lower,
            'current': current,
        }
    except Exception as e:
        return None

def get_trend_signal(tech):
    """判断趋势信号"""
    if not tech:
        return "数据不足"
    
    ma5 = tech['ma5']
    ma10 = tech['ma10']
    ma20 = tech['ma20']
    
    if ma5 > ma10 > ma20:
        return "📈 多头排列"
    elif ma5 < ma10 < ma20:
        return "📉 空头排列"
    else:
        return "📊 均线缠绕"

def get_bbr_position(price, upper, mid, lower):
    """判断布林带位置"""
    if price < lower:
        return "🔴 触及下轨，可能反弹"
    elif price > upper:
        return "🟢 触及上轨，注意回落"
    elif price > mid:
        return "🟡 在中上轨"
    else:
        return "🟡 在中下轨"

def analyze_sell_signal(name, code, cost, stop_loss, profit_target):
    """分析卖出信号"""
    price, pct, turnover = get_realtime_price(code)
    if price is None:
        return None
    
    tech = get_technical(code)
    
    profit = (price - cost) / cost * 100
    
    # 信号判断
    signals = []
    
    # 1. 止损检查（最高优先级）
    if price <= stop_loss:
        return {
            'name': name, 'code': code, 'price': price, 'pct': pct,
            'profit': profit, 'cost': cost, 'stop_loss': stop_loss,
            'profit_target': profit_target, 'turnover': turnover,
            'signal': '🔴', 'type': '止损', 'action': f'立即清仓！跌破{stop_loss}',
            'tech': tech
        }
    
    # 2. 止盈检查
    if price >= profit_target:
        signals.append(('🟠', '触及目标', f'触及目标{profit_target}，卖1/2-2/3'))
    
    # 3. MACD分析
    if tech:
        if tech['dif'] < tech['dea']:
            signals.append(('🟡', 'MACD死叉', '趋势转弱，减1/3'))
        elif tech['j'] > 80:
            signals.append(('🟡', 'KDJ超买', '注意回调，减1/3'))
        elif tech['rsi'] > 70:
            signals.append(('🟡', 'RSI超买', '超买区域，谨慎'))
        
        # 盈利超10%可考虑止盈
        if profit > 10:
            signals.append(('🟡', '盈利超10%', '可考虑部分止盈'))
    
    # 4. 选择最强信号
    if signals:
        for sig in signals:
            if '止损' in sig[1] or '目标' in sig[1]:
                return {
                    'name': name, 'code': code, 'price': price, 'pct': pct,
                    'profit': profit, 'cost': cost, 'stop_loss': stop_loss,
                    'profit_target': profit_target, 'turnover': turnover,
                    'signal': sig[0], 'type': sig[1], 'action': sig[2],
                    'tech': tech
                }
        return {
            'name': name, 'code': code, 'price': price, 'pct': pct,
            'profit': profit, 'cost': cost, 'stop_loss': stop_loss,
            'profit_target': profit_target, 'turnover': turnover,
            'signal': signals[0][0], 'type': signals[0][1], 'action': signals[0][2],
            'tech': tech
        }
    
    return {
        'name': name, 'code': code, 'price': price, 'pct': pct,
        'profit': profit, 'cost': cost, 'stop_loss': stop_loss,
        'profit_target': profit_target, 'turnover': turnover,
        'signal': '🟢', 'type': '持有', 'action': '正常波动',
        'tech': tech
    }

def main():
    print("=" * 75)
    print(f"📉 卖出信号检测 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 75)
    
    holdings = load_holdings()
    print(f"\n检测 {len(holdings)} 只持仓...\n")
    
    results = []
    for h in holdings:
        result = analyze_sell_signal(h['name'], h['code'], h['cost'], h['stop_loss'], h['profit_target'])
        if result:
            results.append(result)
    
    # 输出汇总表
    print("【卖出信号汇总】")
    print("-" * 75)
    print(f"{'股票':<10s} {'现价':>8s} {'涨跌':>7s} {'盈亏':>8s} {'止损':>7s} {'目标':>7s} {'信号':>4s} {'操作建议'}")
    print("-" * 75)
    
    for r in results:
        print(f"{r['name']:<10s} {r['price']:>8.2f} {r['pct']:>+6.2f}% {r['profit']:>+7.2f}% {r['stop_loss']:>6.2f} {r['profit_target']:>6.2f} {r['signal']:>4s} {r['action']}")
    
    # 详细分析
    print("\n" + "=" * 75)
    print("【详细技术分析】")
    print("=" * 75)
    
    for r in results:
        print(f"\n{'='*50}")
        print(f"📊 {r['name']} ({r['code']})")
        print(f"{'='*50}")
        
        print(f"\n【价格与成本】")
        print(f"  现价: {r['price']:.2f} ({r['pct']:+.2f}%)")
        print(f"  成本: {r['cost']:.2f} | 盈亏: {r['profit']:+.2f}%")
        print(f"  止损: {r['stop_loss']:.2f} | 目标: {r['profit_target']:.2f}")
        
        if r['tech']:
            t = r['tech']
            
            print(f"\n【均线系统】")
            print(f"  MA5:  {t['ma5']:.2f}")
            print(f"  MA10: {t['ma10']:.2f}")
            print(f"  MA20: {t['ma20']:.2f}")
            if t['ma60']:
                print(f"  MA60: {t['ma60']:.2f}")
            print(f"  → {get_trend_signal(t)}")
            
            print(f"\n【MACD】")
            print(f"  DIF: {t['dif']:.2f}")
            print(f"  DEA: {t['dea']:.2f}")
            print(f"  MACD柱: {t['macd_bar']:+.2f}")
            macd_sig = "🟢金叉" if t['dif'] > t['dea'] else "🔴死叉"
            print(f"  → {macd_sig}")
            
            print(f"\n【KDJ】")
            print(f"  K: {t['k']:.1f}  D: {t['d']:.1f}  J: {t['j']:.1f}")
            if t['j'] < 20:
                kdj_sig = "🔴超卖"
            elif t['j'] > 80:
                kdj_sig = "🟢超买"
            else:
                kdj_sig = "🟡中性"
            print(f"  → {kdj_sig}")
            
            print(f"\n【RSI(14)】")
            print(f"  RSI: {t['rsi']:.1f}")
            if t['rsi'] < 30:
                rsi_sig = "🔴超卖"
            elif t['rsi'] > 70:
                rsi_sig = "🟢超买"
            else:
                rsi_sig = "🟡中性"
            print(f"  → {rsi_sig}")
            
            print(f"\n【布林带】")
            print(f"  上轨: {t['bbr_upper']:.2f}")
            print(f"  中轨: {t['bbr_mid']:.2f}")
            print(f"  下轨: {t['bbr_lower']:.2f}")
            bbr_pos = get_bbr_position(r['price'], t['bbr_upper'], t['bbr_mid'], t['bbr_lower'])
            print(f"  → {bbr_pos}")
        
        print(f"\n【信号】 {r['signal']} {r['type']}: {r['action']}")
    
    print("\n" + "=" * 75)
    print("⚠️ 仅供参考，投资需谨慎")
    print("=" * 75)

if __name__ == "__main__":
    main()
