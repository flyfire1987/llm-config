#!/usr/bin/env python3
"""
腾讯财经接口 - A股实时行情
作为首选数据源
修复：始终使用正确计算涨跌幅
"""

import requests
import re
from datetime import datetime

# 股票代码映射
CODES = {
    "688256": "sh688256",  # 寒武纪
    "002281": "sz002281",  # 光迅科技
    "300059": "sz300059",  # 东方财富
    "001270": "sz001270",  # ST铖昌
    "600759": "sh600759",  # 洲际油气
    "600938": "sh600938",  # 中国海油
    "300170": "sz300170",  # 汉得信息
    "300750": "sz300750",  # 宁德时代
    "002594": "sz002594",  # 比亚迪
    "600519": "sh600519",  # 贵州茅台
}

def get_price(code):
    """获取单只股票价格"""
    if code not in CODES:
        return None
    
    url = f"https://qt.gtimg.cn/q={CODES[code]}"
    
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            text = resp.text
            pattern = f'{CODES[code]}="([^"]+)"'
            match = re.search(pattern, text)
            if match:
                fields = match.group(1).split('~')
                if len(fields) > 4:
                    price = float(fields[3])
                    prev_close = float(fields[4])
                    # 始终正确计算涨跌幅
                    pct = (price - prev_close) / prev_close * 100
                    return {
                        'code': code,
                        'name': fields[1],
                        'price': price,
                        'prev_close': prev_close,
                        'change': price - prev_close,
                        'pct': pct,
                    }
    except:
        pass
    
    return None

def get_all_prices():
    """获取所有股票价格"""
    if not CODES:
        return []
    
    url = "https://qt.gtimg.cn/q=" + ",".join(CODES.values())
    
    results = []
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            text = resp.text
            
            for code, qcode in CODES.items():
                pattern = f'{qcode}="([^"]+)"'
                match = re.search(pattern, text)
                if match:
                    fields = match.group(1).split('~')
                    if len(fields) > 4:
                        price = float(fields[3])
                        prev_close = float(fields[4])
                        pct = (price - prev_close) / prev_close * 100
                        results.append({
                            'code': code,
                            'name': fields[1],
                            'price': price,
                            'prev_close': prev_close,
                            'pct': pct,
                        })
    except Exception as e:
        print(f"Error: {e}")
    
    return results

if __name__ == "__main__":
    print("=" * 60)
    print(f"腾讯财经行情 - {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 60)
    
    prices = get_all_prices()
    
    if prices:
        for p in prices:
            bar = "🟢" if p['pct'] > 0 else "🔴"
            print(f"{p['name']:10s} {p['code']} {p['price']:>8.2f} {bar}{p['pct']:>+6.2f}%  昨收:{p['prev_close']:.2f}")
    else:
        print("获取失败")
    
    print("=" * 60)
