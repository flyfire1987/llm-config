#!/usr/bin/env python3
"""快速获取A股数据"""
import sys
sys.path.insert(0, '/root/.openclaw/workspace')

from stock_tencent import get_stocks_quote, get_stock_quote

print("=" * 50)
print("A股复盘数据 (腾讯接口)")
print("=" * 50)

# 大盘指数
print("\n【大盘指数】")
indices = [
    ('上证指数', 'sh000001'),
    ('深证成指', 'sz399001'),
    ('创业板指', 'sz399006'),
    ('科创50', 'sh000688'),
]
for name, code in indices:
    try:
        q = get_stock_quote(code)
        pct = q.get('pct_chg', 'N/A')
        trend = '多头' if float(pct) > 0 else '空头' if float(pct) < 0 else '震荡'
        print(f"{name}: {q.get('price','N/A')} | {pct}% | {trend}")
    except Exception as e:
        print(f"{name}: 获取失败")

# 持仓个股
print("\n【持仓个股】")
holdings = [
    ('科创50ETF华夏', 'sh588000'),
    ('贵州茅台', 'sh600519'),
    ('新易盛', 'sz300502'),
    ('创业板ETF广发', 'sz159952'),
    ('英维克', 'sz002837'),
    ('中国核建', 'sh601611'),
]
try:
    codes = [h[1] for h in holdings]
    df = get_stocks_quote(codes)
    for _, row in df.iterrows():
        print(f"{row['name']}({row['code']}): {row['price']} | {row['pct_chg']}%")
except Exception as e:
    print(f"批量获取失败: {e}")
    for name, code in holdings:
        try:
            q = get_stock_quote(code)
            print(f"{name}({code}): {q.get('price','N/A')} | {q.get('pct_chg','N/A')}%")
        except:
            print(f"{name}: 失败")

print("\n=" * 50)