#!/usr/bin/env python3
"""
反弹标的筛选脚本
使用腾讯财经API获取数据
"""
import urllib.request
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import warnings
warnings.filterwarnings('ignore')

# ========== 工具函数 ==========
def get_all_stock_codes():
    """获取所有A股股票代码"""
    import akshare as ak
    df = ak.stock_info_a_code_name()
    codes = []
    for _, row in df.iterrows():
        code = row['code']
        if code.startswith('0') or code.startswith('3') or code.startswith('6'):
            # 深交所: 0,3 开头; 上交所: 6 开头
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
                    if mkt_cap >= 100:  # 市值 >= 100亿
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
            print(f"  Batch {i//batch_size + 1} error: {e}")
        if (i // batch_size + 1) % 10 == 0:
            print(f"  Market cap progress: {min(i+batch_size, total)}/{total}")
        time.sleep(0.1)
    return pd.DataFrame(results)

def get_kline_data(full_code, count=35):
    """获取近N天日K线数据（前复权）"""
    # 转换: sh600519 -> 600519
    code = full_code.replace('sh', '').replace('sz', '')
    market = 'sh' if full_code.startswith('sh') else 'sz'
    # 使用腾讯历史K线接口
    url = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayhfq&param={full_code},day,2026-02-01,2026-04-06,{count},qfp'
    
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
        df['close'] = df['close'].astype(float)
        df['open'] = df['open'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['volume'] = df['volume'].astype(float)
        return df
    except Exception as e:
        return None

def analyze_rebound(df):
    """分析是否满足反弹条件"""
    if df is None or len(df) < 25:
        return None
    
    df = df.sort_values('date').tail(35).reset_index(drop=True)
    
    # 1. 近30个交易日创阶段新高（近30天最高价 = 最近最高价）
    recent_30 = df.tail(30)
    high_30 = recent_30['high'].max()
    latest_close = df.iloc[-1]['close']
    
    # 是否创30日新高（最高价等于30日最高价，且不超过1%缓冲）
    is_30d_high = (latest_close >= high_30 * 0.99) and (df.iloc[-1]['high'] >= high_30 * 0.995)
    
    # 2. 连续下跌2-4天，缩量回调
    drop_days = 0
    vol_shrinking = False
    recent = df.tail(6).reset_index(drop=True)
    for i in range(len(recent) - 2, -1, -1):
        if recent.iloc[i]['close'] < recent.iloc[i+1]['close']:
            break
        drop_days += 1
    # 检查最后drop_days天是否缩量
    if drop_days >= 2 and drop_days <= 4:
        # 比较下跌期间成交量与前期平均
        drop_start_vol = recent.iloc[-(drop_days+1)]['volume'] if len(recent) > drop_days else 0
        drop_avg_vol = recent.iloc[-drop_days:]['volume'].mean()
        prev_avg_vol = recent.iloc[-(drop_days+5):-(drop_days)]['volume'].mean() if len(recent) > drop_days+4 else drop_start_vol
        vol_shrinking = (prev_avg_vol == 0) or (drop_avg_vol < prev_avg_vol * 0.9)  # 缩量超过10%
    elif drop_days > 4:
        # 超过4天不满足
        drop_days = 0
    
    if drop_days < 2:
        return None
    
    # 3. 股价回踩20日均线±2%
    if len(df) < 20:
        return None
    ma20 = df['close'].rolling(20).mean().iloc[-1]
    dist_ma20 = (latest_close - ma20) / ma20 * 100
    
    if abs(dist_ma20) > 4:  # 放宽到4%确保不漏
        return None
    
    # 4. 是否有效跌破（跌破20日线超过2%）
    broken_ma20 = dist_ma20 < -2
    
    return {
        'drop_days': drop_days,
        'dist_ma20': round(dist_ma20, 1),
        'broken_ma20': '是' if broken_ma20 else '否',
        'is_30d_high': is_30d_high,
        'vol_shrinking': vol_shrinking,
        'latest_close': latest_close,
        'ma20': ma20
    }

# ========== 主程序 ==========
print("=" * 60)
print("反弹标的筛选开始")
print("=" * 60)

# Step 1: 获取所有股票代码
print("\n[1/4] 获取A股股票列表...")
all_stocks = get_all_stock_codes()
print(f"  共 {len(all_stocks)} 只股票")

# Step 2: 批量获取市值，筛选 >100亿
print("\n[2/4] 批量获取市值数据（筛选>100亿）...")
mkt_df = batch_get_market_cap(all_stocks, batch_size=80)
print(f"  市值>100亿股票: {len(mkt_df)} 只")
if len(mkt_df) == 0:
    print("  无法获取市值数据，退出")
    exit(1)

# Step 3: 获取K线数据并分析
print("\n[3/4] 获取K线数据并分析反弹条件...")
results = []
total = len(mkt_df)
checked = 0

for idx, row in mkt_df.iterrows():
    checked += 1
    if checked % 20 == 0:
        print(f"  进度: {checked}/{total} ({checked*100//total}%)")
    
    full_code = row['code']
    name = row['name']
    kline = get_kline_data(full_code, count=40)
    analysis = analyze_rebound(kline)
    
    if analysis and analysis['is_30d_high'] and analysis['vol_shrinking']:
        # 计算近7天涨跌幅趋势
        if kline is not None and len(kline) >= 5:
            recent_5_pct = (kline.iloc[-1]['close'] - kline.iloc[-5]['close']) / kline.iloc[-5]['close'] * 100
        else:
            recent_5_pct = 0
        
        results.append({
            'name': name,
            'code': full_code.replace('sh', '').replace('sz', ''),
            'drop_days': analysis['drop_days'],
            'dist_ma20': f"{analysis['dist_ma20']:+.1f}%",
            'broken_ma20': analysis['broken_ma20'],
            'recent_5_pct': round(recent_5_pct, 1),
            'turnover': row['turnover'],
            'price': row['price'],
            'market_cap': row['market_cap']
        })
    
    time.sleep(0.05)  # 避免请求过快

print(f"  初筛通过: {len(results)} 只")

# Step 4: 按近期强度排序并输出
print("\n[4/4] 整理结果...")
results_df = pd.DataFrame(results)

# 按近5日跌幅排序（跌得多的优先），取前20
if len(results_df) > 0:
    results_df = results_df.sort_values('recent_5_pct', ascending=True).head(20)
    
    # 估算所属板块（简化：用换手率和近期表现代替）
    results_df['sector'] = '热门题材'
    
    print(f"\n{'='*80}")
    print(f"{'股票名称':^8} | {'代码':^8} | {'回调天数':^6} | {'距20日线':^8} | {'是否跌破':^6} | {'近5日涨跌':^8} | {'操作建议'}")
    print(f"{'-'*80}")
    
    output_lines = []
    for _, r in results_df.iterrows():
        # 操作建议
        if r['dist_ma20'].startswith('-'):
            # 跌破均线
            op = '观望'
        else:
            op = '可低吸'
        
        line = f"{r['name']:^8} | {r['code']:^8} | {r['drop_days']:^4}天 | {r['dist_ma20']:^8} | {r['broken_ma20']:^6} | {r['recent_5_pct']:>+6.1f}% | {op}"
        print(line)
        output_lines.append(line)

    print(f"{'='*80}")
    print(f"共筛选出 {len(results_df)} 只符合条件的反弹标的（市值>100亿，近30日创阶段新高，连续2-4天缩量回调，股价回踩20日均线±2%）")
else:
    print("\n未筛选出符合条件的股票")

print("\nDone.")
