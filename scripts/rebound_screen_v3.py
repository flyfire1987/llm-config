#!/usr/bin/env python3
"""
反弹标的筛选脚本 v3
修正：近30日创阶段新高 = 30日内某天最高价是近30天最高，且当前价格已从该高点回落
"""
import urllib.request
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import warnings
warnings.filterwarnings('ignore')

def get_all_stock_codes():
    """获取所有A股股票代码"""
    import akshare as ak
    df = ak.stock_info_a_code_name()
    codes = []
    for _, row in df.iterrows():
        code = row['code']
        if code.startswith('0') or code.startswith('3') or code.startswith('6'):
            prefix = 'sz' if code.startswith(('0', '3')) else 'sh'
            codes.append({'code': code, 'name': row['name'], 'full_code': f"{prefix}{code}"})
    return codes

def batch_get_market_cap(codes_full, batch_size=80):
    """批量获取市值数据"""
    results = []
    total = len(codes_full)
    for i in range(0, total, batch_size):
        batch = codes_full[i:i+batch_size]
        code_str = ','.join([c['full_code'] for c in batch])
        url = f'https://qt.gtimg.cn/q={code_str}'
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read().decode('gbk', errors='ignore')
            lines = data.strip().split('\n')
            for line in lines:
                if '=' not in line:
                    continue
                parts = line.split('=')[1].strip('";').split('~')
                if len(parts) < 50:
                    continue
                try:
                    mkt_cap = float(parts[44]) if parts[44] else 0
                    if mkt_cap >= 100:
                        full_code = parts[2] if len(parts) > 2 else ''
                        name = parts[1] if len(parts) > 1 else ''
                        price = float(parts[3]) if parts[3] else 0
                        pct_chg = float(parts[32]) if parts[32] else 0
                        turnover = float(parts[38]) if parts[38] else 0
                        results.append({
                            'code': full_code,
                            'name': name,
                            'price': price,
                            'pct_chg': pct_chg,
                            'turnover': turnover,
                            'market_cap': mkt_cap
                        })
                except:
                    pass
        except Exception as e:
            pass
        if (i // batch_size + 1) % 10 == 0:
            print(f"  市值进度: {min(i+batch_size, total)}/{total}")
        time.sleep(0.08)
    return pd.DataFrame(results)

def get_kline(full_code, count=40):
    """获取日K线数据（前复权）"""
    url = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayhfq&param={full_code},day,2026-01-10,2026-04-06,{count},qfp'
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0')
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = resp.read().decode('utf-8', errors='ignore')
        json_str = data[data.index('=') + 1:]
        obj = json.loads(json_str)
        qfq_key = list(obj['data'].values())[0] if 'data' in obj else {}
        qfq_data = qfq_key.get('qfqday') or qfq_key.get('day') or []
        if not qfq_data:
            return None
        df = pd.DataFrame(qfq_data, columns=['date', 'open', 'close', 'high', 'low', 'volume'])
        for col in ['close', 'open', 'high', 'low', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        return df.dropna().reset_index(drop=True)
    except:
        return None

def analyze_rebound(df):
    """
    筛选反弹条件:
    1. 近30个交易日内创出过阶段新高（某天high是30日内最高）
    2. 近期连续下跌2～4天，缩量回调
    3. 股价已回踩至20日均线附近（±4%）
    """
    if df is None or len(df) < 25:
        return None
    
    df = df.sort_values('date').tail(40).reset_index(drop=True)
    n = len(df)
    
    # 近30日最高价及其位置
    recent_30 = df.tail(30).copy()
    high_30 = recent_30['high'].max()
    high_30_idx = recent_30['high'].idxmax()
    days_from_high = n - 1 - high_30_idx  # 距今天数
    
    # 条件1: 近30日创阶段新高，且从高点回落了1天以上
    if not (days_from_high >= 1 and days_from_high <= 5):
        return None  # 高点距今1-5天比较合理
    
    # 条件2: 连续下跌2-4天
    recent_6 = df.tail(6).reset_index(drop=True)
    drop_days = 0
    for i in range(len(recent_6) - 2, -1, -1):
        if recent_6.iloc[i]['close'] < recent_6.iloc[i+1]['close']:
            drop_days += 1
        else:
            break
    
    if drop_days < 2 or drop_days > 4:
        return None
    
    # 检查缩量: 下跌期间成交量 < 前期同等天数平均成交量
    vol_recent = recent_6.iloc[-drop_days:]['volume'].mean()
    vol_prev = recent_6.iloc[-(drop_days+5):-(drop_days)]['volume'].mean()
    if vol_prev > 0 and vol_recent >= vol_prev * 0.9:  # 未缩量
        return None
    
    # 条件3: 股价回踩20日均线 ±4%
    if n < 20:
        return None
    ma20 = df['close'].rolling(20).mean().iloc[-1]
    latest_close = df.iloc[-1]['close']
    dist_ma20 = (latest_close - ma20) / ma20 * 100
    
    if abs(dist_ma20) > 4:
        return None
    
    # 条件4: 换手率 > 1%（成交活跃）
    # 通过df传入的turnover需要额外获取，这里用成交量变化率简化判断
    vol_active = vol_recent > df['volume'].mean() * 0.8
    
    broken_ma20 = '是' if dist_ma20 < -2 else '否'
    
    # 近5日涨跌幅
    if n >= 5:
        pct_5d = (df.iloc[-1]['close'] - df.iloc[-5]['close']) / df.iloc[-5]['close'] * 100
    else:
        pct_5d = 0
    
    return {
        'drop_days': drop_days,
        'dist_ma20': round(dist_ma20, 1),
        'broken_ma20': broken_ma20,
        'latest_close': latest_close,
        'ma20': ma20,
        'high_30': high_30,
        'days_from_high': days_from_high,
        'pct_5d': round(pct_5d, 1),
        'vol_active': vol_active
    }

# ========== 主程序 ==========
print("=" * 70)
print("反弹标的筛选 v3")
print("=" * 70)

# Step 1 & 2: 获取股票列表和市值
print("\n[1/3] 获取A股股票列表...")
all_stocks = get_all_stock_codes()
print(f"  共 {len(all_stocks)} 只")

print("\n[2/3] 批量获取市值...")
mkt_df = batch_get_market_cap(all_stocks, batch_size=80)
print(f"  市值>100亿: {len(mkt_df)} 只")

if len(mkt_df) == 0:
    print("无法获取市值数据")
    exit(1)

# Step 3: 获取K线并筛选
print("\n[3/3] K线分析...")
results = []
total = len(mkt_df)

for idx, (_, row) in enumerate(mkt_df.iterrows()):
    if (idx + 1) % 100 == 0:
        print(f"  进度: {idx+1}/{total} ({ (idx+1)*100//total }%)")
    
    kline = get_kline(row['code'], count=45)
    analysis = analyze_rebound(kline)
    
    if analysis:
        results.append({
            'name': row['name'],
            'code': row['code'].replace('sh', '').replace('sz', ''),
            'drop_days': analysis['drop_days'],
            'dist_ma20': f"{analysis['dist_ma20']:+.1f}%",
            'broken_ma20': analysis['broken_ma20'],
            'recent_5_pct': analysis['pct_5d'],
            'turnover': row['turnover'],
            'price': row['price'],
            'market_cap': row['market_cap'],
            'days_from_high': analysis['days_from_high']
        })
    time.sleep(0.04)

print(f"  初筛通过: {len(results)} 只")

# Step 4: 排序输出
if results:
    results_df = pd.DataFrame(results)
    # 按近5日跌幅降序（跌得多优先）+ 换手率降序
    results_df = results_df.sort_values(['recent_5_pct', 'turnover'], ascending=[True, False]).head(20)
    
    print(f"\n{'='*90}")
    print(f"{'股票名称':^8} | {'代码':^8} | {'回调天数':^6} | {'距20日线':^8} | {'是否跌破':^6} | {'近5日涨跌':^8} | {'操作建议'}")
    print(f"{'-'*90}")
    
    for _, r in results_df.iterrows():
        op = '可低吸' if r['dist_ma20'] >= '-2.0%' else '观望'
        print(f"{r['name']:^8} | {r['code']:^8} | {r['drop_days']:^4}天 | {r['dist_ma20']:^8} | {r['broken_ma20']:^6} | {r['recent_5_pct']:>+6.1f}% | {op}")
    print(f"{'='*90}")
else:
    print("未筛选出符合条件的股票")

print("\nDone.")
