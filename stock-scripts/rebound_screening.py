#!/usr/bin/env python3
"""筛选反弹标的 - A股反弹股票筛选 v6 - 并发优化版"""
import sys
sys.path.insert(0, '/root/.openclaw/workspace')
from stock_tencent import get_stocks_quote
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import requests
import json
import warnings
warnings.filterwarnings('ignore')
from concurrent.futures import ThreadPoolExecutor, as_completed

print(f"🔍 开始筛选反弹标的... 当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

def get_kline_data(symbol, days=15):
    start_date = (datetime.today() - timedelta(days=35)).strftime('%Y-%m-%d')
    url = f'https://ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,{start_date},,{days},qfq'
    try:
        r = requests.get(url, timeout=8, headers={'User-Agent': 'Mozilla/5.0'})
        data = json.loads(r.text)
        kdata = data.get('data', {}).get(symbol, {})
        qfqday = kdata.get('qfqday') or kdata.get('day') or []
        result = []
        for item in qfqday:
            if len(item) >= 6:
                try:
                    result.append({'date': item[0], 'close': float(item[2]), 'volume': float(item[5])})
                except:
                    continue
        return result
    except:
        return None

def analyze_stock(code, name):
    """分析单只股票"""
    sym = ('sh' + code) if code.startswith(('6','5')) else ('sz' + code)
    kdata = get_kline_data(sym)
    if not kdata or len(kdata) < 4:
        return None
    
    closes = [d['close'] for d in kdata]
    vols = [d['volume'] for d in kdata]
    
    # 近3日跌幅
    drop_3d = (closes[-1] - closes[-4]) / closes[-4] * 100
    if drop_3d > -7:
        return None
    
    # 近5日跌幅
    drop_5d = (closes[-1] - closes[-6]) / closes[-6] * 100 if len(closes) >= 6 else 0
    
    pct_chgs = [(closes[i] - closes[i-1]) / closes[i-1] * 100 for i in range(1, len(closes))]
    last_pct = pct_chgs[-1]
    prev_vol = vols[-2] if len(vols) >= 2 else vols[-1]
    vol_ratio = vols[-1] / prev_vol if prev_vol > 0 else 0
    
    # 止跌企稳
    is_consolidation = abs(last_pct) < 3 and vol_ratio < 1.2
    if not is_consolidation:
        return None
    
    ma20 = np.mean(closes[-20:]) if len(closes) >= 20 else np.mean(closes)
    dist_ma20 = (closes[-1] - ma20) / ma20 * 100
    broken = "是" if closes[-1] < ma20 else "否"
    advise = "可低吸" if (dist_ma20 > -10 and broken == "否") else "观望"
    
    return {
        '股票名称': name,
        '代码': code,
        '回调天数': 3,
        '距20日线': f"{dist_ma20:+.1f}%",
        '是否有效跌破': broken,
        '近3日跌幅': f"{drop_3d:+.1f}%",
        '昨收涨跌': f"{last_pct:+.2f}%",
        '操作建议': advise
    }

# 1. 获取全市场股票列表
import akshare as ak
df_names = ak.stock_info_a_code_name()
name_dict = dict(zip(df_names['code'].astype(str), df_names['name']))
print(f"股票列表: {len(name_dict)} 只")

def to_tc(code):
    code = str(code).zfill(6)
    return ('sh' + code) if code.startswith(('6','5')) else ('sz' + code)

# 2. 批量获取行情，筛选市值>100亿 & 今日跌幅>2%
batch_size = 100
all_candidates = []
all_codes = list(name_dict.keys())

for start in range(0, len(all_codes), batch_size):
    batch = all_codes[start:start+batch_size]
    tc_codes = [to_tc(c) for c in batch]
    try:
        df_q = get_stocks_quote(tc_codes)
        if len(df_q) > 0:
            df_q['mkt'] = pd.to_numeric(df_q['总市值'].str.replace('亿',''), errors='coerce')
            df_q['pct'] = pd.to_numeric(df_q['涨跌幅'].str.replace('%','').str.replace('+',''), errors='coerce')
            cond = (df_q['mkt'] > 100) & (df_q['pct'] < -2)
            filtered = df_q[cond].copy()
            if len(filtered) > 0:
                all_candidates.append(filtered)
    except:
        pass

if not all_candidates:
    print("❌ 无法获取行情数据")
    exit(1)

df_candidates = pd.concat(all_candidates, ignore_index=True)
print(f"✅ 市值>100亿 & 今日跌幅>2% 股票: {len(df_candidates)} 只")

# 3. 并发分析K线
results = []
with ThreadPoolExecutor(max_workers=20) as executor:
    futures = {executor.submit(analyze_stock, str(row['代码']).zfill(6), row['名称']): row 
               for _, row in df_candidates.iterrows()}
    done = 0
    for future in as_completed(futures):
        done += 1
        if done % 50 == 0:
            print(f"已分析 {done}/{len(df_candidates)} 只...")
        try:
            r = future.result()
            if r:
                results.append(r)
        except:
            pass

# 排序取前20
results.sort(key=lambda x: float(x['近3日跌幅'].rstrip('%')), reverse=True)
results = results[:20]

print(f"\n✅ 符合反弹条件股票: {len(results)} 只")

if results:
    print("\n| 股票名称 | 代码 | 回调天数 | 距20日线 | 是否有效跌破 | 近3日跌幅 | 昨收涨跌 | 操作建议 |")
    print("|:--------:|:----:|:--------:|:--------:|:------------:|:--------:|:--------:|:--------:|")
    for r in results:
        print(f"| {r['股票名称']} | {r['代码']} | {r['回调天数']}天 | {r['距20日线']} | {r['是否有效跌破']} | {r['近3日跌幅']} | {r['昨收涨跌']} | {r['操作建议']} |")
else:
    print("今日无符合条件的反弹标的")
