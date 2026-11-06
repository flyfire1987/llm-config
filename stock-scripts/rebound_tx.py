#!/usr/bin/env python3
"""反弹标的筛选 - 腾讯接口 + 自适应市场条件"""
import json, urllib.request, pandas as pd, numpy as np
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings; warnings.filterwarnings('ignore')

# ---------- 腾讯行情 ----------
def parse_key(line):
    try:
        if '=' not in line or not line.strip(): return None
        k = line.split('=')[0].strip().replace('v_', '')
        f = line.split('=')[1].strip('";').split('~')
        if len(f) < 45: return None
        return {'code': k, 'name': f[1], 'price': float(f[3] or 0),
                'pct': float(f[32] or 0), 'amount': float(f[37] or 0)}
    except: return None

def get_batch(codes):
    if not codes: return pd.DataFrame()
    url = f'https://qt.gtimg.cn/q={",".join(codes)}'
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0')
        req.add_header('Referer', 'https://finance.qq.com')
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode('gbk', errors='ignore')
        rows = [parse_key(l) for l in raw.strip().split('\n')]
        return pd.DataFrame([x for x in rows if x])
    except: return pd.DataFrame()

# ---------- 腾讯K线 ----------
def kline(code, days=30):
    url = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayqfq&param={code},day,,,{days},qfq'
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0')
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read().decode('utf-8', errors='ignore').replace('kline_dayqfq=', '', 1)
        d = json.loads(raw).get('data', {}).get(code, {})
        q = d.get('qfqday', d.get('day', []))
        if not q or len(q) < 8: return pd.DataFrame()
        df = pd.DataFrame(q, columns=['date','open','close','high','low','vol'])
        for c in ['open','close','high','low','vol']: df[c] = pd.to_numeric(df[c], errors='coerce')
        df = df.sort_values('date').tail(30).reset_index(drop=True).dropna()
        return df
    except: return pd.DataFrame()

def rsi(closes, p=14):
    if len(closes) < p: return 50
    s = pd.Series(closes)
    delta = s.diff()
    gain = delta.where(delta > 0, 0).rolling(p).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(p).mean()
    return float((100 - 100 / (1 + gain / (loss + 1e-10))).iloc[-1])

# ---------- 筛选 ----------
def check(code, name, today_pct):
    df = kline(code, 30)
    if df is None or len(df) < 12: return None
    c = df['close'].values.tolist()
    v = df['vol'].values.tolist()
    if len(c) < 10: return None

    yes_c = c[-2]   # 昨日收盘
    today_c = c[-1] # 今日

    # 近5日涨跌（跳过周末用-6）
    d5 = c[-6] if len(c) >= 6 else yes_c
    pct5 = (yes_c - d5) / d5 * 100 if d5 > 0 else 0

    # RSI
    rsi14 = rsi(c, 14)
    rsi5 = rsi(c, 5)

    # 昨日K线
    yes_o = df.iloc[-2]['open']
    yes_h = df.iloc[-2]['high']
    yes_l = df.iloc[-2]['low']
    yes_c_v = df.iloc[-2]['close']
    yes_v = df.iloc[-2]['vol']
    y_chg = (yes_c_v - yes_o) / yes_o * 100 if yes_o > 0 else 0
    y_body = abs(y_chg)

    # 量比：昨日量 vs 10日均量
    avg_v = np.mean(v[-11:-1]) if len(v) >= 11 else np.mean(v[:-1])
    vol_r = yes_v / avg_v if avg_v > 0 else 1

    # 20日线
    ma20 = np.mean(c[-20:]) if len(c) >= 20 else np.mean(c)
    ma20_dist = (yes_c_v - ma20) / ma20 * 100 if ma20 > 0 else 0

    # 企稳信号
    is_stable = y_body < 2.0 and vol_r < 0.9
    # 有效跌破
    eff_break = (yes_c_v < ma20 and y_chg < -1.5)

    if 'ST' in name or '*' in name: return None

    # 条件A: 近5日跌超5% + RSI<50 + 企稳
    # 条件B: 近5日跌超8% + RSI<55
    # 条件C: RSI<40 + 偏离<10%
    cond_a = pct5 < -5 and rsi14 < 50 and is_stable
    cond_b = pct5 < -8 and rsi14 < 55
    cond_c = rsi14 < 40 and abs(ma20_dist) < 10

    if not (cond_a or cond_b or cond_c): return None

    score = (40 - rsi14) * 2
    if not eff_break:
        score += (0.9 - vol_r) * 10 + abs(pct5)
    else:
        score += (40 - rsi14)

    return {
        'name': name, 'code': code,
        '今日涨跌': f"{today_pct:+.2f}%",
        '近5日涨跌': f"{pct5:+.1f}%",
        'RSI5': f"{rsi5:.1f}", 'RSI14': f"{rsi14:.1f}",
        '昨K实体': f"{y_body:.1f}%", '量比': f"{vol_r:.2f}",
        '距20日线': f"{ma20_dist:+.1f}%",
        '是否有效跌破': "是" if eff_break else "否",
        '操作': "可低吸" if not eff_break else "观望",
        'score': score,
    }

# ---------- 主流程 ----------
print("=" * 60)
print(f"🔍 反弹标的筛选  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 60)

# 大盘股
print("\n📥 加载大盘股...")
big = pd.read_csv('/root/.openclaw/workspace/data/big_cap_stocks.txt', comment='#')
big.columns = ['code', 'name', 'mkt']
big['code'] = big['code'].astype(str).str.zfill(6)
big['tx'] = big['code'].apply(lambda c: ('sh'+c if c.startswith(('6','8')) else ('sz'+c if c.startswith(('0','2','3')) else None)))
big = big[big['tx'].notna()]
print(f"✅ >100亿: {len(big)} 只")

# 实时行情
print("📡 获取实时行情...")
dfs = []
for i in range(0, len(big), 100):
    batch = big['tx'].tolist()[i:i+100]
    dfb = get_batch(batch)
    if not dfb.empty: dfs.append(dfb)
    if i % 500 == 0: print(f"  {i}/{len(big)}")
    import time; time.sleep(0.2)

if not dfs: print("❌ 行情失败"); exit(1)
df_live = pd.concat(dfs, ignore_index=True)
print(f"✅ 行情 {len(df_live)} 只")

# 大盘指数
idx = {'sh000001':'上证','sz399001':'深证','sz399006':'创业板'}
df_i = get_batch(list(idx.keys()))
if not df_i.empty:
    print("\n📊 大盘:")
    for _, r in df_i.iterrows():
        if r['code'] in idx: print(f"  {idx[r['code']]}: {r['price']} ({r['pct']:+.2f}%)")

# 候选
df_live['pct'] = pd.to_numeric(df_live['pct'], errors='coerce').fillna(0)
df_drop = df_live[df_live['pct'] < 0]
top_drop = df_drop.nsmallest(60, 'pct', keep='all')
top_amt = df_live.nlargest(140, 'amount', keep='all')
candidates = pd.concat([top_drop, top_amt]).drop_duplicates()
print(f"\n📋 候选 {len(candidates)} 只精筛...")

name_map = dict(zip(big['tx'], big['name']))
results = []
done = 0

def worker(row):
    return check(row['code'], name_map.get(row['code'], row.get('name','')), float(row['pct']))

with ThreadPoolExecutor(max_workers=30) as ex:
    futures = {ex.submit(worker, row): i for i, (_, row) in enumerate(candidates.iterrows())}
    for f in as_completed(futures):
        done += 1
        if done % 20 == 0: print(f"  已验证 {done}/{len(candidates)}, 候选 {len(results)}")
        r = f.result()
        if r: results.append(r)

print(f"\n✅ 符合条件: {len(results)} 只")
if not results: print("⚠️ 今日市场无符合条件标的"); exit(0)

results.sort(key=lambda x: x['score'], reverse=True)
top20 = results[:20]

print(f"\n{'='*60}")
print(f"📋 反弹标的 TOP20（市值>100亿）")
print(f"{'='*60}")
print(f"| 股票名称 | 代码 | 今日涨跌 | 近5日涨跌 | RSI5 | RSI14 | 昨K实体 | 量比 | 距20日线 | 有效跌破 | 操作 |")
print(f"|:--------:|:----:|:-------:|:--------:|:----:|:-----:|:------:|:----:|:--------:|:--------:|:----:|")
for r in top20:
    print(f"| {r['name']} | {r['code']} | {r['今日涨跌']} | {r['近5日涨跌']} | {r['RSI5']} | {r['RSI14']} | {r['昨K实体']} | {r['量比']} | {r['距20日线']} | {r['是否有效跌破']} | {r['操作']} |")
print(f"\n💡 条件A: RSI<50 + 昨缩量小K(实体<2%+量比<0.9) + 近5日跌超5%")
print(f"   条件B: 近5日跌超8% + RSI<55")
print(f"   条件C: RSI<40 + 偏离20日<10%")
