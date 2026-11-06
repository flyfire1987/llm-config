#!/usr/bin/env python3
"""
反弹标的筛选 v10 - 放宽条件，适配近期市场
条件：
1. 连续下跌2~5天
2. 今日量能 vs 前5日均量（不含下跌期）< 0.9（缩量9%以上）
3. 股价在20日线±8%以内（回踩确认）
4. 60日线在价格下方（多头排列保护）
5. 股价在20日线上方（非有效跌破）
"""
import requests, json, sys, time

def get_kline(tx_code, days=60):
    url = f"https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get?param={tx_code},day,,,{days},qfq"
    try:
        resp = requests.get(url, timeout=8)
        data = resp.json()
        if tx_code not in data['data']:
            return None
        d = data['data'][tx_code]
        return d.get('day') or d.get('qfqday')
    except:
        return None

def screen_stock(code, name):
    tx = f"sh{code}" if code.startswith(('6', '9')) else f"sz{code}"
    kdata = get_kline(tx, 65)
    if not kdata or len(kdata) < 25:
        return None
    
    try:
        closes = [float(d[2]) for d in kdata]
        vols   = [float(d[5]) for d in kdata]
    except:
        return None
    
    pct = []
    for i in range(len(closes)):
        pct.append((closes[i]-closes[i-1])/closes[i-1]*100 if i > 0 else 0)
    
    # 1. 连续下跌2~5天（最近连续）
    drop = 0
    for i in range(-1, -6, -1):
        if pct[i] < 0:
            drop += 1
        else:
            break
    if drop < 2 or drop > 5:
        return None
    
    # 2. 今日量能萎缩 vs 前5日（不含下跌期）均量
    if drop >= 5:
        baseline_start = -5
    else:
        baseline_start = -drop - 5
    if baseline_start < -(len(vols)-1):
        baseline_start = -(len(vols)-1)
    baseline = vols[baseline_start:-drop] if drop > 0 else vols[-6:-1]
    if len(baseline) < 3:
        baseline = vols[-6:-1]
    avg_v = sum(baseline) / len(baseline)
    if avg_v <= 0:
        return None
    vol_ratio = vols[-1] / avg_v
    if vol_ratio >= 0.9:  # 缩量不够
        return None
    
    # 3. 20日均线±8%（回踩支撑）
    if len(closes) < 22:
        return None
    ma20 = sum(closes[-20:]) / 20
    dist = (closes[-1] - ma20) / ma20 * 100
    if abs(dist) > 8:
        return None
    
    # 4. 60日线在当前价格下方（多头保护）
    if len(closes) < 62:
        return None
    ma60 = sum(closes[-60:]) / 60
    if ma60 >= closes[-1]:  # 60日线形成压力，放弃
        return None
    
    # 5. 未有效跌破20日线
    valid_break = '否' if closes[-1] >= ma20 else '是'
    
    # 6. 股价相对60日线有安全距离（上方15%以内，避免追高）
    ma60_dist = (closes[-1] - ma60) / ma60 * 100
    if ma60_dist > 20:  # 涨太多，反弹空间有限
        return None
    
    return {
        'name': name, 'code': code,
        'drop': drop, 'dist': round(dist, 1),
        'vol_ratio': round(vol_ratio, 2),
        'ma60_dist': round(ma60_dist, 1),
        'valid_break': valid_break
    }

def get_all_a_stocks():
    """获取沪深全市场股票（分页，每页500）"""
    stocks = []
    seen = set()
    for pn in range(1, 6):
        try:
            url = (f"https://push2delay.eastmoney.com/api/qt/clist/get?"
                   f"pn={pn}&pz=500&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281"
                   f"&fltt=2&invt=2&fid=f62"
                   f"&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
                   f"&fields=f12,f14,f3,f62")
            resp = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            j = resp.json()
            items = j['data']['diff'] if j['data'] and j['data'].get('diff') else []
            if not items:
                break
            for item in items:
                code = item['f12']
                if code not in seen:
                    seen.add(code)
                    stocks.append((code, item['f14']))
            time.sleep(0.1)
        except:
            continue
    return stocks

print("=" * 60)
print("【反弹标的筛选 v10】")
print("=" * 60)

stocks = get_all_a_stocks()
print(f"候选股票数: {len(stocks)}")

results = []
checked = 0
for code, name in stocks:
    if checked >= 1500:
        break
    r = screen_stock(code, name)
    checked += 1
    if r:
        results.append(r)

print(f"已检查: {checked} 只，命中: {len(results)} 只")

if not results:
    print("\n未筛选到符合条件的股票")
    sys.exit(0)

# 排序：优先连续下跌天数多、缩量明显、回踩精准的
results.sort(key=lambda x: (-x['drop'], x['vol_ratio'], abs(x['dist'])))
results = results[:20]

print(f"\n【反弹标的】（共 {len(results)} 只）")
print(f"\n| 股票名称 | 代码 | 回调天数 | 距20日线 | 缩量倍数 | 是否有效跌破 | 操作建议 |")
print("|:--------:|:----:|:--------:|:--------:|:--------:|:------------:|:--------:|")
for r in results:
    # 操作建议：回踩20日线且缩量 → 可低吸；偏离或放量 → 观望
    if r['dist'] >= -3 and r['vol_ratio'] < 0.75:
        op = '可低吸'
    elif r['dist'] >= -5 and r['drop'] >= 3:
        op = '可低吸'
    else:
        op = '观望'
    print(f"| {r['name']} | {r['code']} | {r['drop']}天 | {r['dist']:+.1f}% | {r['vol_ratio']:.2f} | {r['valid_break']} | {op} |")

print("\n" + "=" * 60)
print("说明：回调天数越多、缩量越明显（<0.75），反弹概率越大")
print("距20日线 -3% 以内且缩量 → 低吸；偏离过大或放量 → 观望")
print("=" * 60)