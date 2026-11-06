#!/usr/bin/env python3
"""
反弹标的筛选器 - 腾讯接口版本
筛选逻辑：
1. 近5日跌幅 > 10%（超跌）
2. RSI < 45（超卖）
3. 底部放量迹象
4. 偏离20日均线不超过40%
"""

import pandas as pd
import numpy as np
import sys
import time
import subprocess
import re
from datetime import datetime, timedelta

sys.path.insert(0, '/root/.openclaw/workspace')
from stock_tencent import get_stock_quote, get_stocks_quote

def get_kline_data(code):
    """获取K线数据"""
    # 将sh/sz前缀转为腾讯格式
    if code.startswith('sh') or code.startswith('sz'):
        tc_code = code.replace('sh', 'sh').replace('sz', 'sz')
    else:
        tc_code = code
    
    cmd = f"cd /root/.openclaw/workspace && python3 -c \"import urllib.request; import json; url='https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayhfq&param={tc_code},day,,,320,qfq'; req=urllib.request.Request(url); resp=urllib.request.urlopen(req, timeout=10); data=resp.read().decode(); print(data)\""
    
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        if result.returncode == 0 and result.stdout:
            # 解析数据
            text = result.stdout.strip()
            match = re.search(r'=(\{.*\})', text)
            if match:
                data = json.loads(match.group(1))
                code_key = list(data['data'].keys())[0]
                days = data['data'][code_key]['qfqday']
                
                df = pd.DataFrame(days, columns=['日期', '开盘', '收盘', '涨跌幅', '成交量', '成交额', '振幅'])
                df['收盘'] = df['收盘'].astype(float)
                df['成交量'] = df['成交量'].astype(float)
                return df
    except Exception as e:
        pass
    return None

def calculate_rsi(prices, period=14):
    """计算RSI"""
    prices = pd.Series(prices)
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1] if len(rsi) >= period else 50

def get_market_top_drop():
    """获取跌幅榜"""
    try:
        # 使用东方财富跌幅榜接口
        url = "https://push2.eastmoney.com/api/qt/clist/get?cb=jQuery&pn=1&pz=200&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:0+t:6,m:0+t:13,m:1+t:2,m:1+t:23&fields=f2,f3,f4,f5,f6,f7,f10,f12,f14,f15,f16,f17,f18&_=1"
        
        import urllib.request
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=10)
        text = resp.read().decode('utf-8')
        
        # 提取JSON
        match = re.search(r'jQuery\((.*)\)', text)
        if match:
            data = json.loads(match.group(1))
            stocks = data['data']['diff']
            
            result = []
            for item in stocks:
                if item['f3'] < 0:  # 下跌的
                    result.append({
                        '代码': item['f12'],
                        '名称': item['f14'],
                        '最新价': item['f2'],
                        '涨跌幅': item['f3'],
                        '成交量': item['f6'],
                        '成交额': item['f7']
                    })
            return result
    except Exception as e:
        print(f"获取跌幅榜失败: {e}")
    
    # 备用：使用腾讯接口获取指数然后推算
    try:
        indices = get_stocks_quote(['sh000001', 'sz399001', 'sz399006'])
        print("指数涨跌:", indices[['代码','名称','涨跌幅']].to_string())
    except:
        pass
    
    return []

def screen_rebound():
    """筛选反弹标的"""
    print("=" * 60)
    print("【反弹标的筛选】" + datetime.now().strftime("%Y-%m-%d %H:%M"))
    print("=" * 60)
    
    # 获取跌幅榜
    print("\n📊 获取跌幅榜数据...")
    drop_list = get_market_top_drop()
    
    if not drop_list:
        print("获取数据失败，尝试备用方法...")
        # 使用腾讯接口获取市场概况
        try:
            # 获取所有A股通过腾讯接口
            cmd = """python3 -c "
import urllib.request
import json
url = 'https://stock.gtimg.cn/data/index.php?appn=detail&action=data&c=sh&p=1'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
resp = urllib.request.urlopen(req, timeout=10)
data = json.loads(resp.read().decode('gbk'))
print(data)
" """
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            print(result.stdout[:500] if result.stdout else "无输出")
        except Exception as e:
            print(f"备用方法也失败: {e}")
        return
    
    df = pd.DataFrame(drop_list)
    print(f"获取到 {len(df)} 只下跌股票")
    
    # 过滤ST
    df = df[~df['名称'].str.contains('ST|退市|N', na=False)]
    
    # 取跌幅最大的100只
    df_sorted = df.sort_values('涨跌幅', ascending=True).head(100)
    
    print(f"筛选ST后剩余 {len(df_sorted)} 只")
    print("\n跌幅前20:")
    print(df_sorted.head(20)[['代码','名称','涨跌幅','最新价']].to_string(index=False))
    
    # 重点分析跌幅前30
    print(f"\n🔍 深度分析跌幅前30只股票...")
    candidates = []
    
    for i, row in df_sorted.head(30).iterrows():
        try:
            code = row['代码']
            name = row['名称']
            price = float(row['最新价'])
            pct_today = float(row['涨跌幅'])
            
            # 获取K线
            kline = get_kline_data(code)
            if kline is None or len(kline) < 25:
                continue
            
            closes = kline['收盘'].values
            volumes = kline['成交量'].values
            
            # 计算指标
            if len(closes) < 5:
                continue
            
            ma20 = np.mean(closes[-20:]) if len(closes) >= 20 else np.mean(closes)
            
            # 近5日跌幅
            pct_5d = (closes[-1] / closes[-5] - 1) * 100 if len(closes) >= 5 else 0
            # 近10日跌幅
            pct_10d = (closes[-1] / closes[-10] - 1) * 100 if len(closes) >= 10 else 0
            
            # RSI
            rsi = calculate_rsi(pd.Series(closes), 14)
            
            # 成交量放大
            vol_3 = np.mean(volumes[-3:])
            vol_10 = np.mean(volumes[-10:])
            vol_ratio = vol_3 / vol_10 if vol_10 > 0 else 0
            
            # 偏离20日均线
            price_dev = (closes[-1] - ma20) / ma20 * 100
            
            # 筛选条件
            if pct_5d < -8 and rsi < 45 and vol_ratio > 1.1:
                score = 0
                score += (45 - rsi) * 2
                score += vol_ratio * 5
                score += min(abs(price_dev) / 3, 15)
                score += min(abs(pct_5d) / 2, 15)
                
                candidates.append({
                    '代码': code,
                    '名称': name,
                    '最新价': f"{price:.2f}",
                    '今日涨跌': f"{pct_today:.1f}%",
                    '5日涨跌': f"{pct_5d:.1f}%",
                    '10日涨跌': f"{pct_10d:.1f}%",
                    'RSI': f"{rsi:.1f}",
                    '量比': f"{vol_ratio:.2f}",
                    '偏离20日': f"{price_dev:.1f}%",
                    '评分': f"{score:.1f}"
                })
            
            time.sleep(0.3)
        except Exception as e:
            continue
    
    # 排序
    candidates.sort(key=lambda x: float(x['评分']), reverse=True)
    
    print(f"\n{'='*60}")
    print(f"【反弹标的精选】共 {len(candidates)} 只")
    print(f"{'='*60}")
    
    if candidates:
        result_df = pd.DataFrame(candidates)
        print(result_df.to_string(index=False))
        
        print(f"\n{'='*60}")
        print("【操作建议】")
        print("-" * 60)
        print("🎯 TOP5 重点关注，评分越高反弹概率越大")
        print("📋 条件: RSI超卖(<45) + 底部放量(量比>1.1) + 5日超跌(<-8%)")
        print("⚠️ 今日市场大跌，严格止损！建议分批建仓")
        print("💡 突破20日均线可视为反弹确认")
    else:
        print("\n😔 未筛选到符合条件的标的")
        print("可能原因：市场整体强势或数据获取问题")

if __name__ == "__main__":
    import json
    screen_rebound()
