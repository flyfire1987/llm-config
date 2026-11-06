#!/usr/bin/env python3
"""
反弹标的筛选器 - 新浪接口版
筛选逻辑：
1. 近5日跌幅大（超跌）
2. RSI < 45（超卖）
3. 底部放量迹象
4. 偏离20日均线不超过40%
"""

import pandas as pd
import numpy as np
import urllib.request
import json
import time
from datetime import datetime

def get_sina_drop_list(pages=5):
    """获取新浪跌幅榜"""
    drop_list = []
    for page in range(1, pages + 1):
        try:
            url = f"https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page={page}&num=50&sort=changepercent&asc=1&node=hs_a&symbol=&_s_r_a=page"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            resp = urllib.request.urlopen(req, timeout=10)
            text = resp.read().decode('gbk')
            data = json.loads(text)
            drop_list.extend(data)
            time.sleep(0.5)
        except Exception as e:
            print(f"获取第{page}页失败: {e}")
            break
    return drop_list

def get_tencent_kline(code):
    """获取腾讯K线数据"""
    try:
        # 判断交易所前缀
        if code.startswith('sh') or code.startswith('sz'):
            tc_code = code
        elif len(code) == 6:
            if code.startswith('8') or code.startswith('4') or code.startswith('9'):
                tc_code = 'bj' + code
            elif code[0] in ['0', '2', '3']:
                tc_code = 'sz' + code
            else:
                tc_code = 'sh' + code
        else:
            return None
        
        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayhfq&param={tc_code},day,,,320,qfq"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=10)
        text = resp.read().decode()
        
        match = text.split('=', 1)
        if len(match) != 2:
            return None
        
        data = json.loads(match[1])
        code_key = list(data['data'].keys())[0]
        days = data['data'][code_key].get('qfqday', [])
        
        if not days:
            days = data['data'][code_key].get('day', [])
        
        if not days:
            return None
        
        df = pd.DataFrame(days, columns=['日期', '开盘', '收盘', '涨跌幅', '成交量', '成交额', '振幅'])
        df['收盘'] = pd.to_numeric(df['收盘'], errors='coerce')
        df['成交量'] = pd.to_numeric(df['成交量'], errors='coerce')
        return df.dropna()
    except Exception as e:
        return None

def calculate_rsi(prices, period=14):
    """计算RSI"""
    if len(prices) < period:
        return 50
    prices = pd.Series(prices)
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def screen_rebound():
    """筛选反弹标的"""
    print("=" * 60)
    print("【反弹标的筛选】" + datetime.now().strftime("%Y-%m-%d %H:%M"))
    print("=" * 60)
    
    # 获取大盘状态
    try:
        url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=1&num=3&sort=changepercent&asc=0&node=hs_a"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=10)
        text = resp.read().decode('gbk')
        data = json.loads(text)
        if data:
            print(f"\n大盘状态: {data[0]['name']} {data[0]['trade']} ({data[0]['changepercent']:+.2f}%)")
    except:
        pass
    
    # 获取跌幅榜
    print("\n📊 获取全市场跌幅数据...")
    drop_list = get_sina_drop_list(pages=5)
    print(f"获取到 {len(drop_list)} 只股票")
    
    if not drop_list:
        print("获取数据失败")
        return
    
    # 过滤ST和退市
    stocks = [s for s in drop_list if not any(x in s.get('name','') for x in ['ST', '退市', 'N'])]
    print(f"过滤ST后剩余 {len(stocks)} 只")
    
    print(f"\n🔍 分析跌幅榜前100只寻找反弹标的...")
    candidates = []
    
    for i, stock in enumerate(stocks[:100]):
        try:
            code = stock['code']
            name = stock['name']
            price = float(stock['trade'])
            pct_today = float(stock['changepercent'])
            
            # 跳过今日跌停或涨停
            if pct_today <= -9.5 or pct_today >= 9.5:
                continue
            
            # 获取K线
            kline = get_tencent_kline(code)
            if kline is None or len(kline) < 25:
                continue
            
            closes = kline['收盘'].values
            volumes = kline['成交量'].values
            
            if len(closes) < 10:
                continue
            
            # 计算指标
            ma20 = np.mean(closes[-20:]) if len(closes) >= 20 else np.mean(closes)
            ma5 = np.mean(closes[-5:])
            
            # 近5日涨跌幅
            pct_5d = (closes[-1] / closes[-6] - 1) * 100 if len(closes) >= 6 else 0
            # 近10日涨跌幅
            pct_10d = (closes[-1] / closes[-11] - 1) * 100 if len(closes) >= 11 else 0
            
            # RSI
            rsi = calculate_rsi(closes, 14)
            
            # 成交量放大
            vol_3 = np.mean(volumes[-3:])
            vol_10 = np.mean(volumes[-10:])
            vol_ratio = vol_3 / vol_10 if vol_10 > 0 else 0
            
            # 偏离20日均线
            price_dev = (closes[-1] - ma20) / ma20 * 100
            
            # 筛选条件
            # 1. 近5日跌幅 > 8% (超跌)
            # 2. RSI < 45 (超卖)
            # 3. 成交量放大 > 1.1
            # 4. 偏离20日均线 < 40%
            # 5. 今日未跌停
            
            if pct_5d < -8 and rsi < 45 and vol_ratio > 1.1 and abs(price_dev) < 40:
                # 计算综合评分
                score = 0
                score += (45 - rsi) * 2  # RSI越低加分
                score += vol_ratio * 5   # 量比越高加分
                score += min(abs(price_dev) / 3, 12)  # 偏离越大加分
                score += min(abs(pct_5d) / 2, 15)  # 跌幅越大加分
                
                candidates.append({
                    '代码': code,
                    '名称': name,
                    '最新价': f"{price:.2f}",
                    '今日涨跌': f"{pct_today:+.2f}%",
                    '5日涨跌': f"{pct_5d:+.1f}%",
                    '10日涨跌': f"{pct_10d:+.1f}%",
                    'RSI': f"{rsi:.1f}",
                    '量比': f"{vol_ratio:.2f}",
                    '偏离20日': f"{price_dev:+.1f}%",
                    '评分': f"{score:.1f}"
                })
            
            time.sleep(0.2)
            
            # 进度
            if (i + 1) % 20 == 0:
                print(f"  已分析 {i+1}/100 只，候选 {len(candidates)} 只")
                
        except Exception as e:
            continue
    
    # 按评分排序
    candidates.sort(key=lambda x: float(x['评分']), reverse=True)
    
    print(f"\n{'='*60}")
    print(f"【反弹标的精选】共筛选出 {len(candidates)} 只")
    print(f"{'='*60}")
    
    if candidates:
        result_df = pd.DataFrame(candidates)
        print(result_df.to_string(index=False))
        
        print(f"\n{'='*60}")
        print("【操作建议】")
        print("-" * 60)
        print("🎯 TOP5 重点关注，综合评分越高反弹概率越大")
        print("📋 筛选条件: RSI超卖(<45) + 底部放量(量比>1.1) + 5日超跌(>-8%)")
        print("⚠️ 注意: 近期市场波动大，务必严格止损！建议分批建仓")
        print("💡 突破20日均线可视为反弹确认信号")
    else:
        print("\n😔 未筛选到符合条件的标的")
        print("可能原因：市场整体强势或数据获取问题")

if __name__ == "__main__":
    screen_rebound()
