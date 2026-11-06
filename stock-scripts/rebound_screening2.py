"""
筛选反弹标的 - 使用腾讯财经接口
"""

import sys
sys.path.insert(0, '/root/.openclaw/workspace')
from stock_tencent import get_stock_quote, get_stocks_quote
import requests
import re
import datetime
import time

def get_kline_tencent(code, count=20):
    """腾讯K线接口获取日K线"""
    url = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayqfq&param={code},day,,,{count},qfq'
    try:
        r = requests.get(url, timeout=8)
        text = r.text
        m = re.search(r'"day":\s*\[(.*?)\]', text, re.DOTALL)
        if not m:
            return None
        data = m.group(1)
        days = re.findall(r'\[(.*?)\]', data)
        result = []
        for d in days:
            parts = d.split(',')
            if len(parts) >= 6:
                try:
                    result.append({
                        'date': parts[0],
                        'open': float(parts[1]),
                        'close': float(parts[2]),
                        'high': float(parts[3]),
                        'low': float(parts[4]),
                        'volume': float(parts[5])
                    })
                except:
                    continue
        return result
    except Exception as e:
        return None

def get_tencent_realtime_batch(codes):
    """批量获取实时行情（腾讯）"""
    results = {}
    # 分批，每批50
    for i in range(0, len(codes), 50):
        batch = codes[i:i+50]
        try:
            df = get_stocks_quote(batch)
            if df is not None:
                for _, row in df.iterrows():
                    results[row['代码']] = row
            time.sleep(0.3)
        except:
            pass
    return results

def main():
    print("=" * 60)
    print("🔍 反弹标的筛选")
    print("=" * 60)
    
    print("\n📥 正在获取全市场股票实时行情（腾讯接口）...")
    
    # 使用腾讯接口获取全市场行情
    # 先用akshare获取股票列表（不拉详细数据，只取代码列表）
    import warnings
    warnings.filterwarnings('ignore')
    
    try:
        import akshare as ak
        # 获取全市场A股实时行情
        df_spot = ak.stock_zh_a_spot_em()
        print(f"  获取到 {len(df_spot)} 只股票")
    except Exception as e:
        print(f"  akshare接口失败: {e}")
        print("  尝试使用腾讯接口获取全市场...")
        # 用腾讯接口通过爬虫方式获取全市场列表
        try:
            r = requests.get('https://hq.sinajs.cn/list=s_sh000001', timeout=5, headers={'Referer': 'https://finance.sina.com.cn'})
            print(f"  腾讯Sina接口测试成功")
        except Exception as e2:
            print(f"  腾讯接口也失败: {e2}")
        return
    
    # 基本清洗
    df_spot['总市值'] = pd.to_numeric(df_spot['总市值'], errors='coerce')
    df_spot['成交额'] = pd.to_numeric(df_spot['成交额'], errors='coerce')
    df_spot['涨跌幅'] = pd.to_numeric(df_spot['涨跌幅'], errors='coerce')
    df_spot['最新价'] = pd.to_numeric(df_spot['最新价'], errors='coerce')
    
    # 筛选市值>=100亿
    df_big = df_spot[df_spot['总市值'] >= 100].copy()
    print(f"  市值>=100亿股票数: {len(df_big)}")
    
    if len(df_big) == 0:
        print("❌ 市值筛选无结果")
        return
    
    codes = df_big['代码'].tolist()
    
    # 准备结果
    candidates = []
    total = len(codes)
    
    print("\n📊 正在分析每只股票的K线形态...")
    
    for idx, code in enumerate(codes):
        if idx % 20 == 0:
            print(f"  进度: {idx+1}/{total} ({min(idx+20,total)}只)...")
        
        try:
            kline = get_kline_tencent(code, 25)
            if not kline or len(kline) < 8:
                continue
            
            # 计算各指标
            closes = [k['close'] for k in kline]
            vols = [k['volume'] for k in kline]
            
            # 最近7天
            recent7 = kline[-7:]
            recent5 = kline[-5:]
            
            # 连续下跌天数（最近几天每日收跌，不含最新）
            down_days = 0
            for j in range(len(recent7)-2, -1, -1):  # 从倒数第2条开始
                if recent7[j]['close'] < recent7[j+1]['close']:
                    down_days += 1
                else:
                    break
            
            if down_days < 4:
                continue
            
            # 最近1天是否缩量
            vol_today = recent7[-1]['volume']
            vol_yesterday = recent7[-2]['volume']
            if vol_today >= vol_yesterday:
                continue
            
            # 20日均线
            if len(kline) >= 20:
                ma20 = sum(c['close'] for c in kline[-20:]) / 20
            else:
                ma20 = sum(c['close'] for c in kline) / len(kline)
            
            price_today = recent7[-1]['close']
            ma20_pct = (price_today - ma20) / ma20 * 100
            
            # 回踩20日均线±3%
            if abs(ma20_pct) > 3:
                continue
            
            # 成交额>=1亿（今日）
            # 从akshare实时行情获取成交额
            row = df_big[df_big['代码'] == code].iloc[0]
            amount_today = row['成交额'] if pd.notna(row['成交额']) else 0
            if amount_today < 1e8:
                continue
            
            name = row['名称']
            if 'ST' in str(name) or '*' in str(name):
                continue
            
            candidates.append({
                '名称': name,
                '代码': code,
                '回调天数': f"{down_days}天",
                '距20日线': f"{ma20_pct:+.1f}%",
                '是否有效跌破': '否' if ma20_pct > -2 else '是',
                '成交额亿': amount_today / 1e8,
                '涨跌幅': row['涨跌幅'] if pd.notna(row['涨跌幅']) else 0,
                '最新价': price_today,
            })
            
            time.sleep(0.05)
            
        except Exception as e:
            continue
    
    print(f"\n✅ 初步筛选出 {len(candidates)} 只候选标的")
    
    # 按成交额排序（热度）
    candidates.sort(key=lambda x: x['成交额亿'], reverse=True)
    top20 = candidates[:20]
    
    print(f"\n📋 反弹标的筛选结果（TOP20）")
    print(f"| 股票名称 | 代码 | 回调天数 | 距20日线 | 是否有效跌破 | 成交额(亿) | 操作建议 |")
    print(f"|:--------:|:----:|:--------:|:--------:|:------------:|:----------:|:--------:|")
    
    for r in top20:
        advice = "可低吸" if r['是否有效跌破'] == '否' else "观望"
        print(f"| {r['名称']} | {r['代码']} | {r['回调天数']} | {r['距20日线']} | {r['是否有效跌破']} | {r['成交额亿']:.1f}亿 | {advice} |")
    
    print("\n⚠️ 仅供参考，不构成投资建议")

if __name__ == "__main__":
    import pandas as pd
    main()
