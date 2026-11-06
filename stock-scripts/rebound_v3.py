#!/usr/bin/env python3
"""
反弹标的筛选脚本 v3 - 腾讯财经行情 + K线
"""

import pandas as pd
import numpy as np
import urllib.request
import re
import warnings
import sys
from datetime import datetime, timedelta

warnings.filterwarnings('ignore')

TODAY = datetime.now()
TODAY_STR = TODAY.strftime('%Y%m%d')
print(f"[{TODAY.strftime('%H:%M:%S')}] 开始筛选反弹标的...")

# ── 1. 获取全市场行情（腾讯财经批量接口）────────────────────────────────
def get_tencent_spot_batch():
    """获取全市场实时行情"""
    # 分批次请求：沪市 sh600xxx + 深市 sz000xxx + sz001xxx
    prefixes = []
    for i in range(600000, 605010):  # 沪市主板
        prefixes.append(f'sh{i}')
    for i in range(1, 280):  # 深市主板 000xxx
        prefixes.append(f'sz{str(i).zfill(6)}')
    for i in range(1, 850):  # 深市中小板 001xxx + 创业板
        prefixes.append(f'sz001{str(i).zfill(3)}')
    for i in range(300000, 300900):  # 创业板 300xxx
        prefixes.append(f'sz{i}')

    batch_size = 60
    all_data = []
    batch_errors = 0

    for i in range(0, len(prefixes), batch_size):
        batch = prefixes[i:i+batch_size]
        codes_str = ','.join(batch)
        url = f'https://qt.gtimg.cn/q={codes_str}'
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            with urllib.request.urlopen(req, timeout=12) as resp:
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
                    if not name or name in ('', 'null', 'None'):
                        continue
                    price = float(fields[3]) if fields[3] else 0
                    prev_close = float(fields[4]) if fields[4] else 0
                    pct_chg = float(fields[32]) if fields[32] else 0
                    high = float(fields[33]) if fields[33] else 0
                    low = float(fields[34]) if fields[34] else 0
                    vol = int(fields[6]) if fields[6] else 0
                    amount = float(fields[37]) * 10000 if fields[37] else 0
                    turnover = float(fields[38]) if fields[38] else 0
                    mkt_cap = float(fields[44]) if fields[44] else 0  # 亿
                    all_data.append({
                        'code': code_raw,
                        'name': name,
                        'price': price,
                        'prev_close': prev_close,
                        'pct_chg': pct_chg,
                        'high': high,
                        'low': low,
                        'volume': vol,
                        'amount': amount,
                        'turnover': turnover,
                        'market_cap_yi': mkt_cap,
                    })
                except:
                    continue
        except Exception as e:
            batch_errors += 1
            continue

    return pd.DataFrame(all_data), batch_errors

print("  正在获取全市场行情...")
df_all, batch_errors = get_tencent_spot_batch()
print(f"  获取到 {len(df_all)} 只股票，批次错误 {batch_errors}")

if len(df_all) == 0:
    print("行情获取失败")
    sys.exit(1)

# ── 2. 市值 > 100亿 ─────────────────────────────────────────────────────────
df_big = df_all[df_all['market_cap_yi'] > 100].copy()
print(f"  市值>100亿: {len(df_big)} 只")

# 过滤ST
df_big = df_big[~df_big['name'].str.contains('ST|退', na=False)]
df_big = df_big[df_big['name'] != '']
print(f"  剔除ST后: {len(df_big)} 只")

# ── 3. 今日跌幅候选人 ─────────────────────────────────────────────────────
candidates = df_big[df_big['pct_chg'] < 0].copy()
candidates = candidates.nsmallest(200, 'pct_chg')
print(f"  今日跌幅候选: {len(candidates)} 只")

# ── 4. K线获取函数 ─────────────────────────────────────────────────────────
def get_kline(sym):
    """获取腾讯K线数据"""
    url = (f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayhfq'
           f'&param={sym},day,,,320,qfq&r=0.1')
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0')
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode('utf-8', errors='ignore')

        # 解析 qfqday 数据
        start = raw.find('"qfqday":[[')
        if start < 0:
            start = raw.find('qfqday=[[')
        if start < 0:
            return None
        start_s = raw.find('[[', start)
        end_s = raw.find(']]', start_s) + 2
        segment = raw[start_s:end_s]

        items = re.findall(r'\[\"[^\"]+\"(?:,\"[^\"]+\")*\]', segment)
        records = []
        for item in items:
            parts = re.findall(r'\"([^\"]+)\"', item)
            if len(parts) >= 6:
                try:
                    records.append({
                        'date':   parts[0],
                        'open':   float(parts[1]),
                        'close':  float(parts[2]),
                        'high':   float(parts[3]),
                        'low':    float(parts[4]),
                        'volume': float(parts[5]),
                    })
                except:
                    continue
        return records
    except:
        return None

# ── 5. 主筛选循环 ───────────────────────────────────────────────────────────
results = []
kline_errors = 0
skipped = 0

for _, row in candidates.iterrows():
    code = str(row['code']).zfill(6)
    name = row['name']

    if code.startswith('6'):
        sym = f'sh{code}'
    else:
        sym = f'sz{code}'

    kdata = get_kline(sym)
    if kdata is None or len(kdata) < 8:
        kline_errors += 1
        continue

    try:
        # 取最后6条（含今日）
        recent = kdata[-6:]
        closes  = [x['close'] for x in recent]
        opens   = [x['open']  for x in recent]
        highs   = [x['high']  for x in recent]
        lows    = [x['low']   for x in recent]
        vols    = [x['volume'] for x in recent]

        price_3d_ago = closes[-4]  # 3交易日前
        price_yesterday = closes[-2]
        price_today = closes[-1]

        if price_3d_ago == 0 or np.isnan(price_3d_ago):
            skipped += 1
            continue

        drop_3d = (price_today - price_3d_ago) / price_3d_ago * 100

        # 近3日跌幅 > 7%
        if drop_3d > -7:
            skipped += 1
            continue

        # 昨日止跌企稳
        y_open, y_close = opens[-2], closes[-2]
        y_high, y_low   = highs[-2], lows[-2]
        if y_open == 0:
            skipped += 1
            continue
        y_body   = abs(y_close - y_open) / y_open * 100
        y_range  = (y_high - y_low) / y_open * 100
        y_upper  = (y_high - max(y_close, y_open)) / y_open * 100
        y_lower  = (min(y_close, y_open) - y_low) / y_open * 100
        # 止跌企稳：实体<2.5%，振幅<5%，上下影不太长
        stabilized = (y_body < 2.5) and (y_range < 5.0) and (y_upper < 2.0) and (y_lower < 2.0)
        # 额外：昨日跌幅明显收窄（今日跌幅绝对值 < 昨日跌幅绝对值的70%）
        if len(closes) >= 3:
            today_drop = abs((closes[-1] - closes[-2]) / closes[-2] * 100) if closes[-2] != 0 else 0
            yest_drop  = abs((closes[-2] - closes[-3]) / closes[-3] * 100) if closes[-3] != 0 else 0
            narrowing = (yest_drop == 0) or (today_drop < yest_drop * 0.7)
            stabilized = stabilized and narrowing

        # 成交量活跃：近3日均量 > 前5日均量*0.7
        avg_3d  = np.nanmean(vols[-3:])
        avg_5p  = np.nanmean(vols[-5:-3]) if len(vols) >= 5 else avg_3d
        vol_active = (avg_3d > avg_5p * 0.6) if avg_5p > 0 else True

        # 20日均线
        all_closes = [x['close'] for x in kdata]
        ma20 = np.nanmean(all_closes[-20:]) if len(all_closes) >= 20 else np.nanmean(all_closes)
        ma20_dist = (price_today - ma20) / ma20 * 100 if (ma20 and ma20 != 0) else 0

        # 有效跌破
        price_3d_close = closes[-4]
        broken_ma20 = (price_today < ma20) and (price_3d_close > ma20) if ma20 else False

        # 回调天数
        drop_days = 0
        for i in range(len(closes)-1, 0, -1):
            if closes[i] < closes[i-1]:
                drop_days += 1
            else:
                break

        # 操作建议
        # 可低吸：止跌确认 + 未有效跌破（修复宽松版）
        if stabilized and not broken_ma20:
            suggestion = "可低吸"
        elif stabilized and broken_ma20 and (ma20_dist > -8):
            suggestion = "可低吸"
        else:
            suggestion = "观望"

        results.append({
            '股票名称':   name,
            '代码':      code,
            '回调天数':  drop_days,
            '近3日跌幅': f"{drop_3d:.1f}%",
            '距20日线':  f"{ma20_dist:+.1f}%",
            '是否有效跌破': '是' if broken_ma20 else '否',
            '热门板块':  '—',
            '操作建议':  suggestion,
            '_sort_k':   0 if suggestion == '可低吸' else 1,
            '_drop':     drop_3d,
            '_ma20_d':   ma20_dist,
        })

    except Exception as e:
        kline_errors += 1
        continue

print(f"  K线分析完成: {len(results)} 只满足条件, {kline_errors} 只失败, {skipped} 只跳过")

if not results:
    print("没有找到符合条件的反弹标的")
    sys.exit(0)

df_result = pd.DataFrame(results)
df_result = df_result.sort_values(['_sort_k', '_drop'], ascending=[True, True])
df_result = df_result.head(20)

header = "| 股票名称 | 代码 | 回调天数 | 近3日跌幅 | 距20日线 | 是否有效跌破 | 热门板块 | 操作建议 |"
sep    = "|:--------:|:----:|:--------:|:--------:|:--------:|:------------:|:--------:|:--------:|"

lines = [header, sep]
for _, row in df_result.iterrows():
    lines.append(f"| {row['股票名称']} | {row['代码']} | {row['回调天数']}天 | {row['近3日跌幅']} | {row['距20日线']} | {row['是否有效跌破']} | {row['热门板块']} | {row['操作建议']} |")

print("\n" + '\n'.join(lines))
print(f"\n共筛选出 {len(df_result)} 只标的")

