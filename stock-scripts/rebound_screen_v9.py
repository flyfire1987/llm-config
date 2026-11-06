#!/usr/bin/env python3
"""
反弹标的筛选 - v9 修复版
1. 获取沪深所有股票（含沪主板+科创板+深主板+创业板）
2. 筛选连续下跌2~4天、缩量、20日线±4%、60日线支撑
3. 成交量萎缩、股价在20日线上方
"""
import requests, json, sys, time

def get_kline(tx_code, days=50):
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
    kdata = get_kline(tx, 55)
    if not kdata or len(kdata) < 25:
        return None
    
    try:
        closes = [float(d[2]) for d in kdata]
        vols   = [float(d[5]) for d in kdata]
    except:
        return None
    
    # 涨跌百分比
    pct = []
    for i in range(len(closes)):
        pct.append((closes[i]-closes[i-1])/closes[i-1]*100 if i > 0 else 0)
    
    # 1. 连续下跌2~4天
    drop = 0
    for i in range(-1, -5, -1):
        if pct[i] < 0:
            drop += 1
        else:
            break
    if drop < 2 or drop > 4:
        return None
    
    # 2. 今日（最近一根K线）量能萎缩 vs 前5日均量（不含近drop天）
    start_idx = -drop - 5
    end_idx = -drop if drop > 0 else -1
    if start_idx < -(len(vols)-1):
        start_idx = -(len(vols)-1)
    baseline_vols = vols[start_idx:end_idx]
    if len(baseline_vols) < 3:
        baseline_vols = vols[-6:-1] if len(vols) > 5 else vols[:-1]
    avg_v = sum(baseline_vols) / len(baseline_vols)
    # 缩量超过20%
    if vols[-1] >= avg_v * 0.8:
        return None
    
    # 3. 20日均线±4%
    if len(closes) < 22:
        return None
    ma20 = sum(closes[-20:]) / 20
    dist = (closes[-1] - ma20) / ma20 * 100
    if abs(dist) > 4:
        return None
    
    # 4. 60日线在当前价格下方（多头趋势，不被60日线压制）
    if len(closes) < 62:
        return None
    ma60 = sum(closes[-60:]) / 60
    if ma60 >= closes[-1]:
        return None
    
    # 5. 股价在20日线上方（非有效跌破）
    valid_break = '否' if closes[-1] >= ma20 else '是'
    
    return {
        'name': name, 'code': code,
        'drop': drop, 'dist': round(dist, 1),
        'vol_ratio': round(vols[-1]/avg_v, 2),
        'ma60_diff': round((closes[-1]-ma60)/ma60*100, 1),
        'valid_break': valid_break
    }

def get_stocks_by_page(page, total_pages):
    """分页获取沪深股票"""
    all_stocks = []
    # 沪市主板 + 科创板
    for fs in ['m:1+t:2,m:1+t:23', 'm:0+t:6,m:0+t:80']:
        for pn in range(1, total_pages + 1):
            try:
                url = (f"https://push2delay.eastmoney.com/api/qt/clist/get?"
                       f"pn={pn}&pz=200&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281"
                       f"&fltt=2&invt=2&fid=f62&fs={fs}&fields=f12,f14,f3,f62")
                resp = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
                j = resp.json()
                items = j['data']['diff'] if j['data'] and j['data'].get('diff') else []
                if not items:
                    break
                all_stocks.extend([(item['f12'], item['f14']) for item in items])
                time.sleep(0.15)
            except:
                continue
    return all_stocks

def get_all_a_stocks():
    """获取全部A股列表"""
    stocks = []
    try:
        # 沪深全市场，分页获取，每页200
        pages = [1, 2, 3, 4, 5]
        for pn in pages:
            try:
                url = (f"https://push2delay.eastmoney.com/api/qt/clist/get?"
                       f"pn={pn}&pz=200&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281"
                       f"&fltt=2&invt=2&fid=f62&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
                       f"&fields=f12,f14,f3,f62")
                resp = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
                j = resp.json()
                items = j['data']['diff'] if j['data'] and j['data'].get('diff') else []
                if not items:
                    break
                stocks.extend([(item['f12'], item['f14']) for item in items])
                time.sleep(0.1)
            except:
                continue
    except:
        pass
    return stocks

print("=" * 60)
print("【反弹标的筛选 v9】")
print("=" * 60)

stocks = get_all_a_stocks()
if not stocks:
    print("获取股票列表失败，尝试备用方案...")
    # 备用：直接用东方财富热门股票
    try:
        url = "https://push2delay.eastmoney.com/api/qt/clist/get?pn=1&pz=500&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f62&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14,f3,f62"
        resp = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        j = resp.json()
        stocks = [(item['f12'], item['f14']) for item in (j['data']['diff'] if j['data'] and j['data'].get('diff') else [])]
    except:
        pass

if not stocks:
    print("无法获取股票列表")
    sys.exit(0)

print(f"候选股票数: {len(stocks)}")

results = []
checked = 0
for code, name in stocks:
    if checked >= 1000:  # 限制检查数量避免超时
        break
    r = screen_stock(code, name)
    checked += 1
    if r:
        results.append(r)

print(f"已检查: {checked} 只，命中: {len(results)} 只")

if not results:
    print("\n未筛选到符合条件的股票")
    sys.exit(0)

# 按连续下跌天数降序、距20日线距离升序排列
results.sort(key=lambda x: (-x['drop'], abs(x['dist'])))
results = results[:20]

print(f"\n【反弹标的】（共 {len(results)} 只）")
print(f"\n| 股票名称 | 代码 | 回调天数 | 距20日线 | 缩量倍数 | 是否有效跌破 | 操作建议 |")
print("|:--------:|:----:|:--------:|:--------:|:--------:|:------------:|:--------:|")
for r in results:
    # 操作建议
    if r['dist'] >= -2 and r['vol_ratio'] < 0.7:
        op = '可低吸'
    elif r['dist'] >= -3 and r['drop'] >= 3:
        op = '可低吸'
    else:
        op = '观望'
    print(f"| {r['name']} | {r['code']} | {r['drop']}天 | {r['dist']:+.1f}% | {r['vol_ratio']:.2f} | {r['valid_break']} | {op} |")

print("\n" + "=" * 60)
print("说明：缩量倍数 < 0.8 表示缩量明显；距20日线 ±4% 以内为回踩有效")
print("=" * 60)