#!/usr/bin/env python3
"""使用腾讯接口获取涨停股近7日行情"""
import sys
sys.path.insert(0, '/root/.openclaw/workspace')
from stock_tencent import get_stock_quote, get_stocks_quote
import warnings
warnings.filterwarnings('ignore')

# 涨停股列表（5月28日）
limit_up_stocks = [
    {"name": "华电能源", "code": "sh600726", "reason": "电力板块强势，受益于电力改革政策"},
    {"name": "大位科技", "code": "sh600589", "reason": "科技股反弹，人工智能题材活跃"},
    {"name": "华塑控股", "code": "sz000509", "reason": "化工板块回暖，产品价格上涨"},
    {"name": "金河生物", "code": "sz002688", "reason": "生物医药走强，业绩预增"},
    {"name": "天地在线", "code": "sz002995", "reason": "互联网服务反弹，云计算题材加持"},
    {"name": "皖维高新", "code": "sh600063", "reason": "化工新材料，国产替代概念"},
    {"name": "粤电力Ａ", "code": "sz000539", "reason": "电力板块持续受益于电价改革"},
    {"name": "新能泰山", "code": "sz000720", "reason": "电力央企整合预期，估值重塑"},
    {"name": "科林电气", "code": "sh603050", "reason": "电气设备国产化，智能电网概念"},
    {"name": "蒙娜丽莎", "code": "sz002918", "reason": "建材板块复苏，地产竣工改善"},
    {"name": "风华高科", "code": "sz000636", "reason": "电子元件需求回暖 MLCC周期向上"},
]

print("=" * 80)
print("涨停股行情数据（腾讯接口）")
print("=" * 80)

# 批量获取行情
codes = [s['code'] for s in limit_up_stocks]
print(f"\n查询 {len(codes)} 只股票...")

try:
    df = get_stocks_quote(codes)
    print("\n查询结果:")
    print(df.to_string())
except Exception as e:
    print(f"批量查询失败: {e}")
    # 逐个查询
    print("\n改为逐个查询...")
    for stock in limit_up_stocks:
        try:
            quote = get_stock_quote(stock['code'])
            print(f"\n【{stock['name']} {stock['code']}】{stock['reason']}")
            print(f"  当前价: {quote.get('price', 'N/A')}元")
            print(f"  涨跌幅: {quote.get('pct_chg', 'N/A')}%")
            print(f"  成交量: {quote.get('volume', 'N/A')}万手")
            print(f"  成交额: {quote.get('amount', 'N/A')}亿元")
        except Exception as e2:
            print(f"  查询失败: {e2}")

print("\n" + "=" * 80)