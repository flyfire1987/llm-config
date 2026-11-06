#!/usr/bin/env python3
"""
筛选反弹标的股票 - 使用腾讯接口和预设热门股票池
"""

import urllib.request
import json
import pandas as pd
import numpy as np
import time
import sys

pd.set_option('display.max_columns', None)


# 预设热门股票池（市值>100亿）
HOT_STOCKS = [
    'sh600519', 'sh601318', 'sh600036', 'sh600887', 'sh600030', 'sh601166', 'sh600016',
    'sh601012', 'sh600028', 'sh601857', 'sh600050', 'sh601668', 'sh600309', 'sh601899',
    'sh601166', 'sh600346', 'sh600104', 'sh600690', 'sh600585', 'sh600150',
    'sh000001', 'sz000001', 'sz000002', 'sz000333', 'sz000651', 'sz000858',
    'sh601766', 'sh601390', 'sh601989', 'sh600547', 'sh601121', 'sh600547',
    'sz002594', 'sz002475', 'sz002230', 'sz000568', 'sz002304', 'sz000726',
    'sh600760', 'sh600702', 'sh600059', 'sh600109', 'sh600735',
    'sh603259', 'sh603288', 'sh603501', 'sh603986', 'sh603799',
    'sh688008', 'sh688111', 'sh688036', 'sh688126', 'sh688185',
    'sh688981', 'sh688202', 'sh688027', 'sh688039', 'sh688041',
    'sz300750', 'sz300059', 'sz300033', 'sz300015', 'sz300014',
    'sz300122', 'sz300676', 'sz300496', 'sz300012', 'sz002475',
    'sh601688', 'sh601728', 'sh601608', 'sh601118', 'sh600570',
    'sh600031', 'sh600425', 'sh600489', 'sh600322', 'sh600208',
    'sh600522', 'sh600176', 'sh600011', 'sh600027', 'sh600406',
    'sh601211', 'sh601881', 'sh600015', 'sh601398', 'sh601939',
    'sh601288', 'sh601988', 'sh600000', 'sh601328', 'sh600015',
    'sh600036', 'sh601229', 'sh601818', 'sh600016', 'sh600018'
]


def get_tencent_kline(symbol, days=40):
    """获取腾讯K线数据"""
    try:
        url = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,{days},qfq'
        
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
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
                
                # 过滤市值<100亿
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


def analyze_rebound(stock):
    """分析单只股票是否符合反弹条件"""
    code = stock['code']
    name = stock['name']
    
    # 获取K线数据
    kline = get_tencent_kline(code, days=40)
    if kline is None or len(kline) < 30:
        return None
    
    try:
        closes = kline['close'].values
        highs = kline['high'].values
        volumes = kline['volume'].values
        
        current_price = closes[-1]
        
        # 条件1: 近30个交易日创过阶段新高
        max_high_30 = np.max(highs[-30:])
        if current_price < max_high_30 * 0.95:
            return None
        
        # 条件2: 连续下跌2-4天
        pct_changes = (closes[1:] - closes[:-1]) / closes[:-1] * 100
        consecutive_down = 0
        for i in range(len(pct_changes)-1, -1, -1):
            if pct_changes[i] < 0:
                consecutive_down += 1
            else:
                break
        
        if consecutive_down < 2 or consecutive_down > 4:
            return None
        
        # 条件3: 最近1天缩量
        if volumes[-1] >= volumes[-2]:
            return None
        
        # 条件4: 股价回踩20日均线±2%
        ma20 = pd.Series(closes).rolling(20).mean().values
        if np.isnan(ma20[-1]):
            return None
        
        ma20_price = ma20[-1]
        deviation = (current_price - ma20_price) / ma20_price * 100
        
        if abs(deviation) > 2:
            return None
        
        # 条件5: 成交量活跃
        avg_vol_5 = np.mean(volumes[-5:])
        avg_vol_20 = np.mean(volumes[-20:])
        if avg_vol_5 < avg_vol_20 * 0.7:
            return None
        
        # 是否有效跌破
        is_broken = "是" if current_price < ma20_price * 0.97 else "否"
        
        # 操作建议
        if deviation > -2 and deviation < 0.5:
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
            'vol_ratio': avg_vol_5 / avg_vol_20 if avg_vol_20 > 0 else 0,
            'new_high_ratio': current_price / max_high_30,
            'pct_chg': stock['pct_chg']
        }
        
    except Exception as e:
        return None


def main():
    print("=" * 60)
    print("🔍 反弹标的筛选开始")
    print("=" * 60)
    
    # 批量获取股票数据
    print("\n获取股票实时数据...")
    stocks = get_stock_batch(HOT_STOCKS)
    
    if not stocks:
        print("无法获取股票数据")
        return
    
    print(f"获取到 {len(stocks)} 只市值>100亿的股票")
    
    # 优先筛选近期有跌幅的股票
    stocks_with_decline = [s for s in stocks if s['pct_chg'] < 0]
    candidate_stocks = stocks_with_decline[:60] if stocks_with_decline else stocks[:60]
    
    print(f"\n开始筛选反弹标的（分析 {len(candidate_stocks)} 只候选股）...")
    
    results = []
    
    for i, stock in enumerate(candidate_stocks):
        if len(results) >= 25:
            break
        
        print(f"[{i+1}] 分析 {stock['name']} {stock['code']}...", end=" ", flush=True)
        
        result = analyze_rebound(stock)
        if result:
            results.append(result)
            print(f"✓")
        else:
            print("不符合")
        
        time.sleep(0.2)
    
    if not results:
        print("\n未筛选出符合条件的股票")
        return
    
    print(f"\n初步筛选出 {len(results)} 只符合初步条件的股票")
    
    # 按成交量活跃度排序
    results.sort(key=lambda x: (x['vol_ratio'], x['new_high_ratio']), reverse=True)
    final_results = results[:20]
    
    # 打印结果
    print("\n" + "=" * 80)
    print("📊 反弹标的筛选结果")
    print("=" * 80)
    print(f"\n| 股票名称 | 代码 | 回调天数 | 距20日线 | 是否有效跌破 | 热门板块 | 操作建议 |")
    print(f"|:--------:|:----:|:--------:|:--------:|:------------:|:--------:|:--------:|")
    
    for r in final_results:
        print(f"| {r['name']} | {r['code']} | {r['down_days']} | {r['ma20_dev']} | {r['broken']} | {r['hot_sector']} | {r['suggestion']} |")
    
    print(f"\n共筛选出 {len(final_results)} 只反弹标的")


if __name__ == "__main__":
    main()
