"""
筛选反弹标的 - 腾讯/Sina接口版
"""

import requests
import re
import datetime
import time
import json

# 腾讯K线接口
def get_kline_tencent(code, count=25):
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

# Sina实时报价接口
def get_sina_stocks_batch(codes):
    """Sina批量获取实时行情"""
    # codes格式: sh600000,sz000001
    query = ','.join(codes)
    url = f'https://hq.sinajs.cn/list={query}'
    headers = {
        'Referer': 'https://finance.sina.com.cn',
        'User-Agent': 'Mozilla/5.0'
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.encoding = 'gbk'
        text = r.text
        return text
    except Exception as e:
        return None

def parse_sina_stock(raw):
    """解析Sina单条股票数据"""
    try:
        if '=""' in raw or '=' not in raw:
            return None
        parts = raw.split('=')
        if len(parts) < 2:
            return None
        data = parts[1].strip('";\r\n ')
        if not data:
            return None
        fields = data.split(',')
        if len(fields) < 32:
            return None
        name = fields[0]
        code = fields[2] if len(fields) > 2 else ''
        price = float(fields[3]) if fields[3] else 0
        prev_close = float(fields[4]) if fields[4] else 0
        pct_chg = 0
        if prev_close > 0:
            pct_chg = (price - prev_close) / prev_close * 100
        volume = float(fields[8]) if fields[8] else 0  # 成交量(手)
        amount = float(fields[9]) if fields[9] else 0   # 成交额(元)
        high = float(fields[4]) if fields[4] else price
        low = float(fields[5]) if fields[5] else price
        return {
            'name': name,
            'code': code,
            'price': price,
            'pct_chg': pct_chg,
            'volume': volume,
            'amount': amount,
            'high': high,
            'low': low,
        }
    except:
        return None

def get_market_cap_tencent(code):
    """腾讯接口获取单只股票总市值"""
    url = f'https://qt.gtimg.cn/q={code}'
    try:
        r = requests.get(url, timeout=5)
        r.encoding = 'gbk'
        text = r.text
        m = re.search(r'~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)~([^~]+)', text)
        if not m:
            return None
        # 市值在字段44
        fields = text.split('~')
        if len(fields) > 44 and fields[44]:
            try:
                return float(fields[44])
            except:
                pass
        return None
    except:
        return None

def main():
    print("=" * 60)
    print("🔍 反弹标的筛选")
    print("=" * 60)
    
    # 生成全市场股票代码列表
    print("\n📋 生成股票列表...")
    
    # 沪市主板: 600000-603999 (约4000只)
    # 科创板: 688000-688999
    # 深市主板: 000000-001999
    # 中小板: 002000-002999
    # 创业板: 300000-300999
    
    codes = []
    # 沪市
    for i in range(600000, 604000):
        codes.append(f'sh{i}')
    # 科创板
    for i in range(688000, 689000):
        codes.append(f'sh{i}')
    # 深市主板
    for i in range(0, 2000):
        codes.append(f'sz{i:06d}')
    # 中小板
    for i in range(2000, 3000):
        codes.append(f'sz{i:06d}')
    # 创业板
    for i in range(300000, 301000):
        codes.append(f'sz{i}')
    
    print(f"  待筛选股票数量: {len(codes)}")
    
    # 分批获取实时行情，每批100只
    all_data = {}
    batch_size = 100
    
    print("\n📥 正在获取实时行情...")
    
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i+batch_size]
        if i % 500 == 0:
            print(f"  进度: {i+1}/{len(codes)}...")
        
        text = get_sina_stocks_batch(batch)
        if text:
            lines = text.strip().split('\n')
            for line in lines:
                parsed = parse_sina_stock(line)
                if parsed and parsed['price'] > 0:
                    all_data[parsed['code']] = parsed
        
        time.sleep(0.2)
    
    print(f"  获取到实时行情: {len(all_data)} 只")
    
    # 筛选有市值数据的股票（市值>=100亿）
    # 腾讯接口逐只获取市值太慢，用成交量估算：成交额>=1亿的视为活跃股票
    
    # 过滤：价格>0，成交额>=1亿，涨跌幅有数据
    active_stocks = {
        code: data for code, data in all_data.items()
        if data['price'] > 0 and data['amount'] >= 1e8
    }
    
    print(f"  成交额>=1亿活跃股: {len(active_stocks)} 只")
    
    if len(active_stocks) > 300:
        # 取成交额最大的300只进行分析（覆盖热门股）
        sorted_stocks = sorted(
            active_stocks.items(),
            key=lambda x: x[1]['amount'],
            reverse=True
        )[:300]
        active_stocks = dict(sorted_stocks)
        print(f"  选取成交额TOP300进行分析")
    
    candidates = []
    total = len(active_stocks)
    
    print(f"\n📊 正在分析K线形态 ({total}只)...")
    
    for idx, (code, data) in enumerate(active_stocks.items()):
        if idx % 30 == 0:
            print(f"  K线分析进度: {idx+1}/{total}...")
        
        try:
            kline = get_kline_tencent(code, 25)
            if not kline or len(kline) < 8:
                continue
            
            recent7 = kline[-7:]
            
            # 连续下跌天数
            down_days = 0
            for j in range(len(recent7)-2, -1, -1):
                if recent7[j]['close'] < recent7[j+1]['close']:
                    down_days += 1
                else:
                    break
            
            if down_days < 4:
                continue
            
            # 缩量回调
            vol_today = recent7[-1]['volume']
            vol_yesterday = recent7[-2]['volume']
            if vol_today >= vol_yesterday:
                continue
            
            # 20日均线
            if len(kline) >= 20:
                ma20 = sum(k['close'] for k in kline[-20:]) / 20
            else:
                ma20 = sum(k['close'] for k in kline) / len(kline)
            
            price_today = recent7[-1]['close']
            ma20_pct = (price_today - ma20) / ma20 * 100
            
            # 回踩20日均线±3%
            if abs(ma20_pct) > 3:
                continue
            
            # 成交额>=2亿（热门标的）
            if data['amount'] < 2e8:
                continue
            
            name = data['name']
            if 'ST' in str(name) or '*' in str(name):
                continue
            
            candidates.append({
                '名称': name,
                '代码': code,
                '回调天数': f"{down_days}天",
                '距20日线': f"{ma20_pct:+.1f}%",
                '是否有效跌破': '否' if ma20_pct > -2 else '是',
                '成交额亿': data['amount'] / 1e8,
                '涨跌幅': data['pct_chg'],
                '最新价': price_today,
            })
            
            time.sleep(0.05)
            
        except Exception as e:
            continue
    
    print(f"\n✅ 初步筛选出 {len(candidates)} 只候选标的")
    
    # 按成交额排序
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
    main()
