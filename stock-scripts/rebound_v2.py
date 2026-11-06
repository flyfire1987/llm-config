#!/usr/bin/env python3
"""
反弹标的筛选脚本 v2 - 腾讯财经 + akshare备用K线
"""

import pandas as pd
import numpy as np
import urllib.request
import json
import warnings
import sys
from datetime import datetime, timedelta

warnings.filterwarnings('ignore')

TODAY_STR = datetime.now().strftime('%Y%m%d')
print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始筛选反弹标的...")

# ── 1. 腾讯财经批量获取全量行情 ─────────────────────────────────────────────
def get_tencent_spot_batch():
    """获取全市场实时行情（分批请求）"""
    all_data = []
    # 沪市全量: 0.600000-0.609999, 0.601yyy
    # 深市全量: 0.000000-0.009999, 0.00xyyy
    prefixes = []
    for i in range(600000, 605000):
        prefixes.append(f'sh{i}')
    for i in range(1, 1500):
        prefixes.append(f'sz{str(i).zfill(6)}')

    batch_size = 50
    all_data = []
    errors = 0

    for i in range(0, min(len(prefixes), 3000), batch_size):
        batch = prefixes[i:i+batch_size]
        codes_str = ','.join(batch)
        url = f'https://qt.gtimg.cn/q={codes_str}'
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode('gbk', errors='ignore')
            lines = raw.strip().split('\n')
            for line in lines:
                if '=' not in line:
                    continue
                parts = line.split('=')
                if len(parts) < 2:
                    continue
                fields = parts[1].strip('";').split('~')
                if len(fields) < 50:
                    continue
                try:
                    code_raw = fields[2]
                    name = fields[1]
                    price = float(fields[3]) if fields[3] else 0
                    prev_close = float(fields[4]) if fields[4] else 0
                    open_p = float(fields[5]) if fields[5] else 0
                    vol = int(fields[6]) if fields[6] else 0
                    pct_chg = float(fields[32]) if fields[32] else 0
                    high = float(fields[33]) if fields[33] else 0
                    low = float(fields[34]) if fields[34] else 0
                    amount = float(fields[37]) * 10000 if fields[37] else 0
                    turnover = float(fields[38]) if fields[38] else 0
                    mkt_cap = float(fields[44]) if fields[44] else 0  # 亿
                    all_data.append({
                        'code': code_raw,
                        'name': name,
                        'price': price,
                        'prev_close': prev_close,
                        'open': open_p,
                        'volume': vol,
                        'pct_chg': pct_chg,
                        'high': high,
                        'low': low,
                        'amount': amount,
                        'turnover': turnover,
                        'market_cap_yi': mkt_cap,
                    })
                except:
                    continue
        except Exception as e:
            errors += 1
            continue

    return pd.DataFrame(all_data), errors

print("  正在获取全市场行情（腾讯财经）...")
df_all, batch_errors = get_tencent_spot_batch()
print(f"  获取到 {len(df_all)} 只股票，批次错误 {batch_errors}")

if len(df_all) == 0:
    print("行情获取失败，尝试备用方案...")
    # 备用：直接用已知大市值股票列表
    print("使用大市值股票列表（行情接口不可用）")
    sys.exit(1)

# ── 2. 市值 > 100亿 ─────────────────────────────────────────────────────────
df_big = df_all[df_all['market_cap_yi'] > 100].copy()
print(f"  市值>100亿: {len(df_big)} 只")

# ── 3. 近3日跌幅 > 7% 的候选 ─────────────────────────────────────────────
# 今日跌幅候选人
df_big['pct_chg'] = pd.to_numeric(df_big['pct_chg'], errors='coerce').fillna(0)
candidates = df_big[df_big['pct_chg'] < 0].copy()
candidates = candidates.nsmallest(200, 'pct_chg')
print(f"  今日有跌幅候选: {len(candidates)} 只")

# ── 4. 获取K线（腾讯历史接口）────────────────────────────────────────────
def get_tencent_kline(code_with_exchange):
    """获取腾讯K线数据（东方财富历史数据接口备用）"""
    # 腾讯K线接口
    code_raw = code_with_exchange.replace('sh', '').replace('sz', '')
    url = (f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayhfq&'
           f'param={code_with_exchange},day,,,320,qfq&r=0.1')
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0')
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode('utf-8', errors='ignore')
        if 'qfqday' not in raw and 'day' not in raw:
            return None
        # 简单解析
        import re
        m = re.search(r'data:\[(.*?)\]', raw, re.S)
        if not m:
            return None
        items = re.findall(r'\[([^\]]+)\]', m.group(1))
        records = []
        for item in items:
            parts = item.split(',')
            if len(parts) >= 6:
                records.append({
                    'date': parts[0],
                    'open': float(parts[1]),
                    'close': float(parts[2]),
                    'high': float(parts[3]),
                    'low': float(parts[4]),
                    'volume': float(parts[5]),
                })
        return records
    except:
        return None

# 尝试用akshare获取K线
def get_akshare_kline(symbol):
    """用akshare获取K线"""
    try:
        import akshare as ak
        df = ak.stock_zh_kline(symbol=symbol, period="daily", adjust="qfq",
                                start_date=(datetime.now() - timedelta(days=40)).strftime('%Y%m%d'))
        if df is None or len(df) < 10:
            return None
        cols = {c: c.lower().strip() for c in df.columns}
        df.rename(columns=cols, inplace=True)
        for c in df.columns:
            if 'close' in c or '收盘' in c:
                pass
        close_c = None
        for c in ['close', '收盘', '收盘价']:
            if c in df.columns:
                close_c = c
                break
        if close_c is None:
            return None
        df['close'] = pd.to_numeric(df[close_c], errors='coerce')
        return df.tail(30).to_dict('records')
    except:
        return None

results = []
kline_errors = 0

for _, row in candidates.iterrows():
    code = row['code']
    name = row['name']
    if not code or len(code) != 6:
        continue
    # 跳过ST、退市
    if 'ST' in str(name) or '退' in str(name) or name == '':
        continue

    if code.startswith('6'):
        sym = f'sh{code}'
    else:
        sym = f'sz{code}'

    # 获取K线
    kdata = get_tencent_kline(sym)
    if kdata is None or len(kdata) < 8:
        kline_errors += 1
        continue

    try:
        closes = [x['close'] for x in kdata[-6:]]
        opens  = [x['open']  for x in kdata[-6:]]
        highs  = [x['high']  for x in kdata[-6:]]
        lows   = [x['low']   for x in kdata[-6:]]
        vols   = [x['volume'] for x in kdata[-6:]]

        price_3d_ago = closes[-4] if len(closes) >= 4 else closes[0]
        price_today  = closes[-1]
        price_yesterday = closes[-2]

        if price_3d_ago == 0 or np.isnan(price_3d_ago):
            continue

        drop_3d = (price_today - price_3d_ago) / price_3d_ago * 100

        # 近3日跌幅 > 7%
        if drop_3d > -7:
            continue

        # 昨日止跌企稳：小阴小阳（实体<1.5%，振幅<4%）
        y_open, y_close = opens[-1], closes[-1]
        y_high, y_low   = highs[-1], lows[-1]
        y_body = abs(y_close - y_open) / y_open * 100 if y_open != 0 else 0
        y_range = (y_high - y_low) / y_open * 100 if y_open != 0 else 0
        y_upper = (y_high - max(y_close, y_open)) / y_open * 100 if y_open != 0 else 0
        y_lower = (min(y_close, y_open) - y_low) / y_open * 100 if y_open != 0 else 0
        stabilized = (y_body < 1.5) and (y_range < 4.0)

        # 成交量：近3日均量 > 前量
        avg_3d = np.nanmean(vols[-3:]) if len(vols) >= 3 else np.nanmean(vols)
        avg_prev = np.nanmean(vols[-6:-3]) if len(vols) >= 6 else avg_3d
        vol_active = (avg_3d > avg_prev * 0.7) if avg_prev > 0 else True

        # 距20日线
        all_closes = [x['close'] for x in kdata]
        ma20 = np.nanmean(all_closes[-20:]) if len(all_closes) >= 20 else np.nanmean(all_closes)
        ma20_dist = (price_today - ma20) / ma20 * 100 if ma20 and ma20 != 0 else 0

        # 有效跌破
        price_3d_ago_close = closes[-4] if len(closes) >= 4 else all_closes[0]
        broken_ma20 = (price_today < ma20) and (price_3d_ago_close > ma20) if ma20 else False

        # 回调天数（连续下跌天数，从最近高点算起）
        drop_days = 0
        for i in range(len(closes)-1, 0, -1):
            if closes[i] < closes[i-1]:
                drop_days += 1
            else:
                break

        # 操作建议
        if stabilized and vol_active and (ma20_dist > -8):
            suggestion = "可低吸"
        else:
            suggestion = "观望"

        results.append({
            '股票名称': name,
            '代码': code,
            '回调天数': drop_days,
            '近3日跌幅': f"{drop_3d:.1f}%",
            '距20日线': f"{ma20_dist:+.1f}%",
            '是否有效跌破': '是' if broken_ma20 else '否',
            '热门板块': '—',
            '操作建议': suggestion,
            '_sort_key': 0 if suggestion == '可低吸' else 1,
            '_drop': drop_3d,
        })

    except Exception as e:
        kline_errors += 1
        continue

print(f"  K线分析完成: {len(results)} 只满足条件，{kline_errors} 只K线失败")

if not results:
    print("没有找到符合条件的反弹标的")
    sys.exit(0)

df_result = pd.DataFrame(results)
df_result = df_result.sort_values(['_sort_key', '_drop'], ascending=[True, True])
df_result = df_result.head(20)

header = "| 股票名称 | 代码 | 回调天数 | 近3日跌幅 | 距20日线 | 是否有效跌破 | 热门板块 | 操作建议 |"
sep    = "|:--------:|:----:|:--------:|:--------:|:--------:|:------------:|:--------:|:--------:|"

lines = [header, sep]
for _, row in df_result.iterrows():
    lines.append(f"| {row['股票名称']} | {row['代码']} | {row['回调天数']}天 | {row['近3日跌幅']} | {row['距20日线']} | {row['是否有效跌破']} | {row['热门板块']} | {row['操作建议']} |")

print("\n" + '\n'.join(lines))
print(f"\n共筛选出 {len(df_result)} 只标的")

