#!/usr/bin/env python3
"""
腾讯财经接口股票查询
备用数据源，当 akshare 东方财富接口不稳定时使用
"""

import urllib.request
import json
import pandas as pd
from typing import List, Optional


def parse_tencent_stock(raw_data: str) -> Optional[dict]:
    """解析腾讯股票数据"""
    try:
        if not raw_data or '=' not in raw_data:
            return None
            
        parts = raw_data.split('=')
        if len(parts) < 2:
            return None
            
        raw = parts[1].strip('";')
        fields = raw.split('~')
        
        # 确保有足够字段
        if len(fields) < 50:
            return None
            
        # 解析字段
        return {
            'code': fields[2] if len(fields) > 2 else '',
            'name': fields[1] if len(fields) > 1 else '',
            'price': float(fields[3]) if fields[3] else 0,         # 当前价
            'prev_close': float(fields[4]) if fields[4] else 0,    # 昨收
            'open': float(fields[5]) if fields[5] else 0,           # 今开
            'volume': int(fields[6]) if fields[6] else 0,          # 成交量(手)
            'change': float(fields[31]) if fields[31] else 0,      # 涨跌
            'pct_chg': float(fields[32]) if fields[32] else 0,     # 涨跌幅
            'high': float(fields[33]) if fields[33] else 0,        # 最高
            'low': float(fields[34]) if fields[34] else 0,         # 最低
            'amount': float(fields[37]) * 10000 if fields[37] else 0,  # 成交额(元)
            'turnover': float(fields[38]) if fields[38] else 0,    # 换手率
            'market_cap': float(fields[44]) if fields[44] else 0, # 总市值(亿)
            'float_market_cap': float(fields[45]) if fields[45] else 0,  # 流通市值(亿)
        }
    except Exception as e:
        print(f"Parse error: {e}")
        return None


def get_stock_quote(code: str) -> Optional[dict]:
    """
    获取单个股票实时行情
    
    Args:
        code: 股票代码，如 'sh601121' 或 'sz001337'
    
    Returns:
        股票行情字典，失败返回 None
    """
    # 转换格式: sh601121 -> 601121
    stock_code = code.replace('sh', '').replace('sz', '')
    
    url = f'https://qt.gtimg.cn/q={code}'
    
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        with urllib.request.urlopen(req, timeout=10) as response:
            data = response.read().decode('gbk', errors='ignore')
            
        return parse_tencent_stock(data)
        
    except Exception as e:
        print(f"Error fetching {code}: {e}")
        return None


def get_stocks_quote(codes: List[str]) -> pd.DataFrame:
    """
    批量获取股票实时行情
    
    Args:
        codes: 股票代码列表，如 ['sh601121', 'sz001337']
    
    Returns:
        包含所有股票行情的 DataFrame
    """
    if not codes:
        return pd.DataFrame()
        
    # 腾讯接口支持批量查询，用逗号分隔
    code_str = ','.join(codes)
    url = f'https://qt.gtimg.cn/q={code_str}'
    
    results = []
    
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        with urllib.request.urlopen(req, timeout=15) as response:
            data = response.read().decode('gbk', errors='ignore')
            
        # 解析多个股票数据
        for line in data.split('\n'):
            stock = parse_tencent_stock(line)
            if stock:
                results.append({
                    '代码': stock['code'],
                    '名称': stock['name'],
                    '当前价': round(stock['price'], 2),
                    '涨跌': round(stock['change'], 2),
                    '涨跌幅': f"{stock['pct_chg']:.2f}%",
                    '最高': round(stock['high'], 2),
                    '最低': round(stock['low'], 2),
                    '今开': round(stock['open'], 2),
                    '昨收': round(stock['prev_close'], 2),
                    '成交量': f"{stock['volume']/10000:.2f}万手",
                    '成交额': f"{stock['amount']/100000000:.2f}亿",
                    '换手率': f"{stock['turnover']:.2f}%",
                    '总市值': f"{stock['market_cap']:.2f}亿",
                })
            
    except Exception as e:
        print(f"Error: {e}")
        
    return pd.DataFrame(results)


def get_stock_by_name(name: str) -> Optional[str]:
    """
    根据股票名称模糊搜索股票代码
    
    Args:
        name: 股票名称关键词
    
    Returns:
        股票代码，如 'sh600489'
    """
    import urllib.parse
    
    # 使用东方财富搜索API
    url = f'https://searchapi.eastmoney.com/api/suggest/get?input={urllib.parse.quote(name)}&type=14&count=10'
    
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0')
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            
        if data.get('QuotationCodeTable', {}).get('Data'):
            stock = data['QuotationCodeTable']['Data'][0]
            code = stock['Code']
            # 判断市场: 6开头是沪市，0/3开头是深市
            if code.startswith('6'):
                return f'sh{code}'
            else:
                return f'sz{code}'
                
    except Exception as e:
        print(f"Search error: {e}")
        
    return None


if __name__ == '__main__':
    # 测试
    print("=== 测试单个股票查询 ===")
    quote = get_stock_quote('sz001337')
    if quote:
        print(f"四川黄金: {quote['price']}元, 涨跌: {quote['change']:.2f}, 涨跌幅: {quote['pct_chg']:.2f}%")
        print(f"最高: {quote['high']}, 最低: {quote['low']}, 成交量: {quote['volume']}")
    
    print("\n=== 测试批量查询 ===")
    df = get_stocks_quote(['sh600489', 'sh600547', 'sh600916', 'sz001337', 'sz000548'])
    if not df.empty:
        print(df[['代码', '名称', '当前价', '涨跌幅']].to_string(index=False))
    else:
        print("无数据")
