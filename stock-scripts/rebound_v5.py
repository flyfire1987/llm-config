#!/usr/bin/env python3
"""
筛选反弹标的股票 - 放宽条件
"""

import urllib.request
import json
import pandas as pd
import numpy as np
import time
import sys

pd.set_option('display.max_columns', None)


def get_tencent_kline(symbol, days=60):
    """获取腾讯K线数据"""
    try:
        url = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,{days},qfq'
        
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0')
        
        with urllib.request.urlopen(req, timeout=12) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        if 'data' not in data or symbol not in data['data']:
            return None
            
        kline_data = data['data'][symbol].get('qfqday', [])
        if not kline_data:
            kline_data = data['data'][symbol].get('day', [])
            
        if not kline_data:
            return None
            
        df = pd.DataFrame(kline_data, columns=['date', 'open', 'close', 'high', 'low', 'volume'])
        
        for col in ['open', 'close', 'high', 'low']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
        
        return df
        
    except Exception as e:
        return None


def get_stock_batch(codes):
    """批量获取股票实时数据"""
    if not codes:
        return []
    
    code_str = ','.join(codes)
    url = f'https://qt.gtimg.cn/q={code_str}'
    
    results = []
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0')
        with urllib.request.urlopen(req, timeout=20) as response:
            data = response.read().decode('gbk', errors='ignore')
        
        for line in data.split('\n'):
            if '=' not in line:
                continue
            try:
                parts = line.split('=')[1].strip('";')
                fields = parts.split('~')
                
                if len(fields) < 50:
                    continue
                
                code_raw = fields[2]
                name = fields[1]
                price = float(fields[3]) if fields[3] else 0
                pct_chg = float(fields[32]) if fields[32] else 0
                market_cap = float(fields[44]) if fields[44] else 0
                
                if market_cap < 100:
                    continue
                
                results.append({
                    'code': code_raw,
                    'name': name,
                    'price': price,
                    'pct_chg': pct_chg,
                    'market_cap': market_cap
                })
            except:
                continue
                
    except Exception as e:
        print(f"批量获取失败: {e}", file=sys.stderr)
    
    return results


def get_all_a_stocks():
    """获取全部A股（通过分页获取）"""
    all_stocks = []
    
    # 获取沪市
    for page in range(1, 6):
        url = f'https://push2.eastmoney.com/api/qt/clist/get?pn={page}&pz=100&po=1&np=1&fltt=2&invt=2&fid=f3&fs=m:0+t:6,m:0+t:80&fields=f2,f3,f12,f13,f14,f20'
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0')
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            if 'data' in data and 'diff' in data['data']:
                for item in data['data']['diff']:
                    mc = item.get('f20', 0)
                    if mc and mc > 100:
                        code = f"sh{item['f12']}" if item['f13'] == 1 else f"sz{item['f12']}"
                        all_stocks.append({
                            'code': code,
                            'name': item['f14'],
                            'price': item.get('f2', 0),
                            'pct_chg': item.get('f3', 0),
                            'market_cap': mc
                        })
        except:
            continue
    
    return all_stocks


def analyze_rebound(stock, debug=False):
    """分析单只股票是否符合反弹条件（放宽版）"""
    code = stock['code']
    name = stock['name']
    
    kline = get_tencent_kline(code, days=60)
    if kline is None or len(kline) < 30:
        return None
    
    try:
        closes = kline['close'].values
        highs = kline['high'].values
        volumes = kline['volume'].values
        
        current_price = closes[-1]
        
        # 条件1: 近30-60天创过阶段新高（放宽）
        max_high = np.max(highs[-40:])
        new_high_ratio = current_price / max_high
        if new_high_ratio < 0.92:  # 放宽到距高点8%以内
            if debug:
                print(f"  未创阶段新高: {new_high_ratio:.2%}")
            return None
        
        # 条件2: 连续下跌2-4天
        pct_changes = (closes[1:] - closes[:-1]) / closes[:-1] * 100
        consecutive_down = 0
        for i in range(len(pct_changes)-1, -1, -1):
            if pct_changes[i] < -0.3:  # 放宽条件，只要小跌也算
                consecutive_down += 1
            else:
                break
        
        if consecutive_down < 2:
            if debug:
                print(f"  下跌天数不足: {consecutive_down}")
            return None
        
        # 条件3: 最近1天缩量或平量
        vol_ratio = volumes[-1] / volumes[-2] if volumes[-2] > 0 else 1
        if vol_ratio > 1.15:  # 放宽，只要不大放量就行
            if debug:
                print(f"  放量过大: {vol_ratio:.2f}")
            return None
        
        # 条件4: 股价回踩20日均线±3%（放宽）
        ma20 = pd.Series(closes).rolling(20).mean().values
        if np.isnan(ma20[-1]):
            return None
        
        ma20_price = ma20[-1]
        deviation = (current_price - ma20_price) / ma20_price * 100
        
        if abs(deviation) > 3:  # 放宽到3%
            if debug:
                print(f"  偏离MA20: {deviation:.1f}%")
            return None
        
        # 条件5: 成交量不要太弱
        avg_vol_5 = np.mean(volumes[-5:])
        avg_vol_20 = np.mean(volumes[-20:])
        if avg_vol_5 < avg_vol_20 * 0.5:
            if debug:
                print(f"  成交量太弱")
            return None
        
        # 是否有效跌破
        is_broken = "是" if current_price < ma20_price * 0.96 else "否"
        
        # 操作建议
        if deviation > -2.5 and deviation < 1 and consecutive_down >= 2:
            suggestion = "可低吸"
        else:
            suggestion = "观望"
        
        return {
            'name': name,
            'code': code[-6:],
            'down_days': f"{consecutive_down}天",
            'ma20_dev': f"{deviation:+.1f}%",
            'broken': is_broken,
            'hot_sector': "热门概念",
            'suggestion': suggestion,
            'vol_ratio': avg_vol_5 / avg_vol_20,
            'new_high_ratio': new_high_ratio,
            'pct_chg': stock['pct_chg']
        }
        
    except Exception as e:
        if debug:
            print(f"  异常: {e}")
        return None


def main():
    print("=" * 60)
    print("🔍 反弹标的筛选开始")
    print("=" * 60)
    
    # 获取候选股票
    print("\n获取A股股票数据...")
    
    # 使用更活跃的候选股
    candidate_codes = [
        'sh600519', 'sh601318', 'sh600036', 'sh600887', 'sh600030', 'sh601166', 'sh600016',
        'sh601012', 'sh600028', 'sh601857', 'sh600050', 'sh601668', 'sh600309', 'sh601899',
        'sh600104', 'sh600690', 'sh600585', 'sh600150', 'sh600760', 'sh600702', 'sh600059',
        'sh600109', 'sh600735', 'sh603259', 'sh603288', 'sh603501', 'sh603986', 'sh603799',
        'sh688008', 'sh688111', 'sh688036', 'sh688126', 'sh688185', 'sh688981', 'sh688202',
        'sh688027', 'sh688039', 'sh688041', 'sh688981', 'sh601688', 'sh601728', 'sh601608',
        'sh601118', 'sh600570', 'sh600031', 'sh600425', 'sh600489', 'sh600322', 'sh600208',
        'sh600522', 'sh600176', 'sh600011', 'sh600027', 'sh600406', 'sh601211', 'sh601881',
        'sh600015', 'sh601398', 'sh601939', 'sh601288', 'sh601988', 'sh600000', 'sh601328',
        'sh600015', 'sh601229', 'sh601818', 'sh600016', 'sh600018', 'sh601988',
        'sz000001', 'sz000002', 'sz000333', 'sz000651', 'sz000858', 'sz002594', 'sz002475',
        'sz002230', 'sz000568', 'sz002304', 'sz000726', 'sz300750', 'sz300059', 'sz300033',
        'sz300015', 'sz300014', 'sz300122', 'sz300676', 'sz300496', 'sz300012',
        'sh601766', 'sh601390', 'sh601989', 'sh600547', 'sh601121', 'sh601166',
        'sh601688', 'sh601728', 'sh601608', 'sh601118', 'sh600570', 'sh600031',
        'sh600346', 'sh600104', 'sh600150', 'sh600809', 'sh600519', 'sh601857',
        'sh600028', 'sh601012', 'sh600111', 'sh600143', 'sh600438', 'sh600703',
        'sh601888', 'sh601899', 'sh601168', 'sh603993', 'sh600456', 'sh600926'
    ]
    
    stocks = get_stock_batch(list(set(candidate_codes)))
    
    if not stocks:
        print("获取股票数据失败")
        return
    
    print(f"获取到 {len(stocks)} 只股票")
    
    # 优先筛选近期有调整的股票
    decline_stocks = [s for s in stocks if s['pct_chg'] < 0]
    all_stocks = decline_stocks + [s for s in stocks if s['pct_chg'] >= 0]
    candidate_stocks = all_stocks[:100]
    
    print(f"开始筛选（分析 {len(candidate_stocks)} 只）...")
    
    results = []
    for i, stock in enumerate(candidate_stocks):
        if len(results) >= 30:
            break
        
        print(f"[{i+1}] {stock['name']}...", end=" ", flush=True)
        
        result = analyze_rebound(stock, debug=False)
        if result:
            results.append(result)
            print(f"✓ {result['down_days']} {result['ma20_dev']}")
        else:
            print("不符合")
        
        time.sleep(0.15)
    
    if not results:
        print("\n未筛选出符合条件的股票")
        return
    
    # 排序：优先成交量活跃、接近新高的
    results.sort(key=lambda x: (x['vol_ratio'], x['new_high_ratio']), reverse=True)
    final_results = results[:20]
    
    print("\n" + "=" * 80)
    print("📊 反弹标的筛选结果")
    print("=" * 80)
    print(f"\n| 股票名称 | 代码 | 回调天数 | 距20日线 | 是否有效跌破 | 热门板块 | 操作建议 |")
    print(f"|:--------:|:----:|:--------:|:--------:|:------------:|:--------:|:--------:|")
    
    for r in final_results:
        print(f"| {r['name']} | {r['code']} | {r['down_days']} | {r['ma20_dev']} | {r['broken']} | {r['hot_sector']} | {r['suggestion']} |")
    
    print(f"\n共 {len(final_results)} 只")


if __name__ == "__main__":
    main()
