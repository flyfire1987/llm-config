#!/usr/bin/env python3
"""调试反弹筛选 v2"""
import pandas as pd
import numpy as np
import urllib.request
import json
import warnings
warnings.filterwarnings('ignore')

def get_kline_tencent(code):
    try:
        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayhfq&param={code},day,,,320,qfq&r=0.1"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.qq.com'})
        resp = urllib.request.urlopen(req, timeout=10)
        text = resp.read().decode('utf-8')
        text = text.replace('kline_dayhfq=', '', 1)
        data = json.loads(text)
        days = data.get('data', {}).get(code, {}).get('qfqday', [])
        if not days:
            days = data.get('data', {}).get(code, {}).get('day', [])
        if not days:
            return None
        df = pd.DataFrame(days, columns=['date', 'open', 'close', 'high', 'low', 'volume'])
        for col in ['open', 'close', 'high', 'low', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        return df
    except:
        return None

# 扩大测试范围
test_codes = [
    ('sh600519','贵州茅台'), ('sz002594','比亚迪'), ('sh601012','隆基绿能'), 
    ('sh600036','招商银行'), ('sz000333','美的集团'), ('sh601318','中国平安'),
    ('sh600887','伊利股份'), ('sh600030','中信证券'), ('sh600900','长江电力'),
    ('sh601888','中国中免'), ('sh600028','中国石化'), ('sh601398','工商银行'),
    ('sh300750','宁德时代'), ('sh300059','东方财富'), ('sz002475','立讯精密'),
    ('sz002415','海康威视'), ('sz000858','五粮液'), ('sz000568','泸州老窖'),
    ('sz002230','科大讯飞'), ('sh688041','海光信息'), ('sh688111','金山办公'),
]

pass_count = 0
for code, name in test_codes:
    df_k = get_kline_tencent(code)
    if df_k is None or len(df_k) < 30:
        print(f"{name}({code}): K线获取失败(len={len(df_k) if df_k is not None else 0})")
        continue
    df_k = df_k.tail(60).copy()
    df_k['ma20'] = df_k['close'].rolling(20).mean()
    
    recent4 = df_k.tail(4)
    down_days = sum(1 for i in range(3) if recent4.iloc[-(i+1)]['close'] < recent4.iloc[-(i+2)]['close'])
    
    last_vol = df_k.iloc[-1]['volume']
    prev_vol = df_k.iloc[-2]['volume']
    
    ma20 = df_k.iloc[-1]['ma20']
    last_close = df_k.iloc[-1]['close']
    dist_ma20 = (last_close - ma20) / ma20 * 100 if ma20 > 0 else 0
    
    high30 = df_k['high'].tail(30).max()
    is_high = last_close >= high30 * 0.98
    
    vol_shrink = last_vol < prev_vol
    broken = last_close < ma20 * 0.97
    
    # 检查是否满足条件
    cond1 = down_days >= 2
    cond2 = vol_shrink
    cond3 = abs(dist_ma20) <= 4
    cond4 = is_high
    cond5 = True
    
    meets = cond1 and cond2 and cond3 and cond4
    if meets:
        pass_count += 1
        print(f"✓ {name}({code[-6:]}) 回调{down_days}天 缩量{vol_shrink} 距20日{dist_ma20:+.1f}% 30日新高:{is_high} 有效跌破:{broken}")
    elif cond1 and cond2:
        print(f"  {name}({code[-6:]}) 回调{down_days}天 缩量{vol_shrink} 距20日{dist_ma20:+.1f}% 30日新高:{is_high}")
    
print(f"\n满足条件的股票: {pass_count} 只")
