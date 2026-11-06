#!/usr/bin/env python3
"""
反弹标的筛选 - 最终宽松版
"""

import urllib.request
import json
import pandas as pd
import numpy as np
import time

pd.set_option('display.max_columns', None)


def get_kline(symbol, days=50):
    try:
        url = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,{days},qfq'
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0')
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
        if 'data' not in data or symbol not in data['data']:
            return None
        k = data['data'][symbol].get('qfqday') or data['data'][symbol].get('day')
        if not k:
            return None
        df = pd.DataFrame(k, columns=['date','open','close','high','low','volume'])
        for c in ['open','close','high','low']:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
        return df
    except:
        return None


def get_quotes(codes):
    if not codes:
        return []
    url = f'https://qt.gtimg.cn/q={",".join(codes)}'
    results = []
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0')
        with urllib.request.urlopen(req, timeout=15) as response:
            data = response.read().decode('gbk', errors='ignore')
        for line in data.split('\n'):
            if '=' not in line:
                continue
            try:
                f = line.split('=')[1].strip('";').split('~')
                if len(f) < 50:
                    continue
                mc = float(f[44]) if f[44] else 0
                if mc < 100:
                    continue
                results.append({
                    'code': f[2], 'name': f[1], 'price': float(f[3]) if f[3] else 0,
                    'pct': float(f[32]) if f[32] else 0, 'mc': mc
                })
            except:
                continue
    except:
        pass
    return results


def analyze(stock):
    code = stock['code']
    k = get_kline(code, 50)
    if k is None or len(k) < 25:
        return None
    try:
        c = k['close'].values
        h = k['high'].values
        v = k['volume'].values
        p = k['close'].values
        pct = (p[1:] - p[:-1]) / p[:-1] * 100
        
        ma20 = pd.Series(c).rolling(20).mean().values[-1]
        if np.isnan(ma20):
            return None
        
        # 简化条件
        dev = (c[-1] - ma20) / ma20 * 100
        
        # 统计下跌天数
        down = 0
        for i in range(len(pct)-1, -1, -1):
            if pct[i] < 0:
                down += 1
            else:
                break
        
        vol_r = v[-1] / v[-2] if v[-2] > 0 else 1
        
        # 宽松条件
        cond1 = abs(dev) <= 4  # 偏离20日线4%以内
        cond2 = down >= 2 and down <= 5  # 连跌
        cond3 = vol_r <= 1.2  # 缩量或平量
        
        if not (cond1 and cond2 and cond3):
            return None
        
        broken = "是" if c[-1] < ma20 * 0.96 else "否"
        
        # 成交量活跃度
        avg_v = np.mean(v[-5:])
        avg_v20 = np.mean(v[-20:])
        vol_act = avg_v / avg_v20 if avg_v20 > 0 else 0
        
        # 近期是否创过新高
        max_h = np.max(h[-35:])
        high_r = c[-1] / max_h if max_h > 0 else 0
        
        if dev > -3 and dev < 1 and down >= 2:
            suggestion = "可低吸"
        else:
            suggestion = "观望"
        
        return {
            'name': stock['name'],
            'code': code[-6:],
            'down_days': f"{down}天",
            'ma20_dev': f"{dev:+.1f}%",
            'broken': broken,
            'hot': "热门",
            'suggestion': suggestion,
            'score': vol_act * high_r
        }
    except:
        return None


def main():
    print("🔍 反弹标的筛选\n")
    
    codes = [
        'sh600519','sh601318','sh600036','sh600887','sh600030','sh601166','sh600016',
        'sh601012','sh600028','sh601857','sh600050','sh601668','sh600309','sh601899',
        'sh600104','sh600690','sh600585','sh600150','sh600760','sh600702','sh600059',
        'sh600109','sh603259','sh603288','sh603501','sh603986','sh603799',
        'sh688008','sh688111','sh688036','sh688126','sh688185','sh688981','sh688202',
        'sh688027','sh688039','sh688041','sh601688','sh601728','sh601608',
        'sh601118','sh600570','sh600031','sh600425','sh600489','sh600322','sh600208',
        'sh600522','sh600176','sh600011','sh600027','sh600406','sh601211','sh601881',
        'sh600015','sh601398','sh601939','sh601288','sh601988','sh600000','sh601328',
        'sh601229','sh601818','sh600018','sh601988',
        'sz000001','sz000002','sz000333','sz000651','sz000858','sz002594','sz002475',
        'sz002230','sz000568','sz002304','sz000726','sz300750','sz300059','sz300033',
        'sz300015','sz300014','sz300122','sz300676','sz300496','sz300012',
        'sh601766','sh601390','sh601989','sh600547','sh601121',
        'sh600111','sh600143','sh600438','sh600703','sh601888','sh601168',
        'sh603993','sh600456','sh600926','sh600809','sh600028','sh600111',
        'sh600547','sh600362','sh600261','sh600352','sh600688','sh600867',
        'sh600809','sh600559','sh600132','sh600199','sh600702','sh600059',
        'sh600036','sh600000','sh601328','sh600015','sh600016'
    ]
    
    stocks = get_quotes(list(set(codes)))
    if not stocks:
        print("获取数据失败")
        return
    
    # 优先分析近期有回调的
    candidates = [s for s in stocks if s['pct'] < 0][:80] + [s for s in stocks if s['pct'] >= 0][:20]
    
    results = []
    for i, s in enumerate(candidates):
        if len(results) >= 30:
            break
        print(f"[{i+1}] {s['name']}...", end=" ", flush=True)
        r = analyze(s)
        if r:
            results.append(r)
            print(f"✓ {r['down_days']} {r['ma20_dev']}")
        else:
            print("不符")
        time.sleep(0.1)
    
    if not results:
        print("\n按更宽松条件筛选：")
        # 展示最接近条件的股票
        results2 = []
        for s in candidates[:50]:
            k = get_kline(s['code'], 40)
            if k is None or len(k) < 20:
                continue
            try:
                c = k['close'].values
                ma20 = pd.Series(c).rolling(20).mean().values[-1]
                if np.isnan(ma20):
                    continue
                dev = (c[-1] - ma20) / ma20 * 100
                pct = (c[1:] - c[:-1]) / c[:-1] * 100
                down = sum(1 for x in pct[-5:] if x < 0)
                v = k['volume'].values
                vol = v[-1] / v[-2] if v[-2] > 0 else 1
                
                # 宽松再宽松
                if abs(dev) < 5 and down >= 1 and vol < 1.3:
                    broken = "是" if c[-1] < ma20 * 0.95 else "否"
                    suggestion = "可低吸" if dev > -3 and dev < 1 else "观望"
                    results2.append({
                        'name': s['name'], 'code': s['code'][-6:],
                        'down_days': f"{down}天", 'ma20_dev': f"{dev:+.1f}%",
                        'broken': broken, 'hot': "热门", 'suggestion': suggestion,
                        'score': abs(dev)
                    })
            except:
                continue
            if len(results2) >= 20:
                break
        
        if not results2:
            print("无符合条件标的")
            return
        
        results2.sort(key=lambda x: x['score'])
        final = results2[:20]
    else:
        results.sort(key=lambda x: x['score'], reverse=True)
        final = results[:20]
    
    print("\n" + "="*70)
    print("📊 反弹标的筛选结果")
    print("="*70)
    print(f"\n| 股票名称 | 代码 | 回调天数 | 距20日线 | 是否有效跌破 | 热门板块 | 操作建议 |")
    print(f"|:--------:|:----:|:--------:|:--------:|:------------:|:--------:|:--------:|")
    for r in final:
        print(f"| {r['name']} | {r['code']} | {r['down_days']} | {r['ma20_dev']} | {r['broken']} | {r['hot']} | {r['suggestion']} |")
    print(f"\n共 {len(final)} 只")


if __name__ == "__main__":
    main()
