#!/usr/bin/env python3
"""
反弹标的筛选脚本 v4（配置文件+并发版）
- 从配置文件读取股票列表（市值>100亿）
- 并发拉取K线，大幅缩短运行时间
"""
import urllib.request
import json
import pandas as pd
import numpy as np
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import warnings
warnings.filterwarnings('ignore')

CONFIG_FILE = "/root/.openclaw/workspace/data/big_cap_stocks.txt"
MAX_WORKERS = 30  # 并发线程数

def load_big_cap_stocks():
    stocks = []
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(',')
            if len(parts) >= 2:
                code = parts[0].strip()
                name = parts[1].strip()
                mkt_cap = float(parts[2]) if len(parts) >= 3 else 0
                prefix = 'sh' if code.startswith('6') else 'sz'
                stocks.append({'code': code, 'name': name, 'full_code': f"{prefix}{code}", 'market_cap': mkt_cap})
    return stocks

def batch_get_price_and_turnover(codes_full, batch_size=80):
    results = {}
    total = len(codes_full)
    for i in range(0, total, batch_size):
        batch = codes_full[i:i+batch_size]
        code_str = ','.join(batch)
        url = f'https://qt.gtimg.cn/q={code_str}'
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0')
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read().decode('gbk', errors='ignore')
            for line in data.strip().split('\n'):
                if '=' not in line:
                    continue
                parts = line.split('=')[1].strip('";').split('~')
                if len(parts) < 50:
                    continue
                try:
                    full_code = parts[2]
                    results[full_code] = {
                        'name': parts[1],
                        'price': float(parts[3]) if parts[3] else 0,
                        'pct_chg': float(parts[32]) if parts[32] else 0,
                        'turnover': float(parts[38]) if parts[38] else 0
                    }
                except:
                    pass
        except:
            pass
        time.sleep(0.06)
    return results

def get_kline(full_code, count=45):
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

def analyze_pullback(kline, mkt_info):
    if kline is None or len(kline) < 25:
        return None
    
    kline = kline.sort_values('date').tail(40).reset_index(drop=True)
    n = len(kline)
    if n < 20:
        return None
    
    ma20 = kline['close'].rolling(20).mean().iloc[-1]
    latest_close = kline.iloc[-1]['close']
    dist_ma20 = (latest_close - ma20) / ma20 * 100
    
    if abs(dist_ma20) > 5:
        return None
    
    recent_30 = kline.tail(30)
    high_30 = recent_30['high'].max()
    high_30_idx_in_30 = recent_30['high'].idxmax()
    offset = n - 30
    high_30_idx = high_30_idx_in_30 + offset
    days_ago = n - 1 - high_30_idx
    
    if days_ago < 2 or days_ago > 6:
        return None
    
    pullback_pct = (latest_close - high_30) / high_30 * 100
    if pullback_pct >= 0 or pullback_pct < -22:
        return None
    
    recent_5 = kline.tail(5)['close'].values
    recent_5_chg = (recent_5[-1] - recent_5[0]) / recent_5[0] * 100
    recent_3 = kline.tail(3)['close'].values
    consec_downs = sum(1 for i in range(len(recent_3) - 1) if recent_3[i] > recent_3[i+1])
    
    if recent_5_chg >= -1 and consec_downs < 2:
        return None
    
    vol_recent = kline.tail(3)['volume'].mean()
    vol_prev = kline.tail(8).iloc[:-3]['volume'].mean()
    if vol_prev <= 0 or vol_recent >= vol_prev * 0.8:
        return None
    
    turnover = mkt_info.get('turnover', 0) if mkt_info else 0
    if turnover < 0.5:
        return None
    
    broken = '是' if dist_ma20 < -2 else '否'
    drop_days = sum(1 for i in range(len(recent_3) - 1) if recent_3[i] > recent_3[i+1])
    pct_1d = (kline.iloc[-1]['close'] - kline.iloc[-2]['close']) / kline.iloc[-2]['close'] * 100 if n >= 2 else 0
    
    return {
        'dist_ma20': round(dist_ma20, 1),
        'broken': broken,
        'drop_days': drop_days,
        'pullback': round(pullback_pct, 1),
        'recent_5_chg': round(recent_5_chg, 1),
        'turnover': turnover,
        'pct_1d': round(pct_1d, 1),
    }

def process_stock(stock):
    """处理单只股票（在线程中执行）"""
    full_code = stock['full_code']
    kline = get_kline(full_code, count=45)
    mkt_info = {'turnover': stock.get('turnover', 0)}
    analysis = analyze_pullback(kline, mkt_info)
    if analysis:
        return {
            'name': stock['name'],
            'code': stock['code'],
            'drop_days': analysis['drop_days'],
            'dist_ma20': f"{analysis['dist_ma20']:+.1f}%",
            'broken': analysis['broken'],
            'pullback': analysis['pullback'],
            'recent_5_chg': analysis['recent_5_chg'],
            'turnover': analysis['turnover'],
            'price': stock.get('price', 0),
            'market_cap': stock['market_cap'],
            'pct_1d': analysis['pct_1d'],
        }
    return None

# ========== 主程序 ==========
print("=" * 70)
print("反弹标的筛选 v4（配置文件+并发版）")
print("=" * 70)

print("\n[1/4] 读取大盘股列表（市值>100亿）...")
big_cap_stocks = load_big_cap_stocks()
print(f"  共 {len(big_cap_stocks)} 只")

if len(big_cap_stocks) == 0:
    print("配置文件为空，请先运行 update_big_cap_list.py")
    exit(1)

print("\n[2/4] 批量获取实时行情...")
price_data = batch_get_price_and_turnover([s['full_code'] for s in big_cap_stocks])
for s in big_cap_stocks:
    pd_data = price_data.get(s['full_code'], {})
    s['price'] = pd_data.get('price', 0)
    s['turnover'] = pd_data.get('turnover', 0)
print(f"  获取到 {len(price_data)} 只行情数据")

print(f"\n[3/4] 并发K线分析（{MAX_WORKERS}线程）...")
results = []
total = len(big_cap_stocks)
done = 0

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = {executor.submit(process_stock, s): s for s in big_cap_stocks}
    for future in as_completed(futures):
        done += 1
        if done % 200 == 0 or done == total:
            print(f"  进度: {done}/{total}")
        r = future.result()
        if r:
            results.append(r)

print(f"  初筛通过: {len(results)} 只")

if results:
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values(['recent_5_chg', 'turnover'], ascending=[True, False]).head(20)
    
    print(f"\n{'='*95}")
    print(f"{'股票名称':^8}|{'代码':^8}|{'回调天数':^6}|{'距20日线':^8}|{'是否跌破':^6}|{'热门板块':^8}|{'操作建议'}")
    print(f"{'-'*95}")
    
    for _, r in results_df.iterrows():
        if r['dist_ma20'].startswith('-') and float(r['dist_ma20'][:-1]) < -2:
            op = '观望'
        else:
            op = '可低吸'
        sector = '热门题材'
        print(f"{r['name']:^8}|{r['code']:^8}|{r['drop_days']:^4}天|{r['dist_ma20']:^8}|{r['broken']:^6}|{sector:^8}|{op}")
    
    print(f"{'='*95}")
    print(f"共 {len(results_df)} 只 | 市值>100亿 | 30日内创阶段新高后回落 | 缩量回调 | 股价±5%于20日线")
else:
    print("\n未筛选出符合条件的股票")

print("\nDone.")