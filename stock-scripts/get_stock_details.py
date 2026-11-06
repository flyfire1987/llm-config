#!/usr/bin/env python3
"""获取涨停股近7日行情数据"""
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# 涨停股列表
limit_up_stocks = [
    {"name": "华电能源", "code": "600726", "reason": "电力板块"},
    {"name": "华塑控股", "code": "000509", "reason": "化工板块"},
    {"name": "金河生物", "code": "002688", "reason": "生物医药"},
    {"name": "天地在线", "code": "002995", "reason": "互联网服务"},
    {"name": "皖维高新", "code": "600063", "reason": "化工材料"},
    {"name": "粤电力Ａ", "code": "000539", "reason": "电力板块"},
    {"name": "新能泰山", "code": "000720", "reason": "电力板块"},
    {"name": "科林电气", "code": "603050", "reason": "电气设备"},
    {"name": "蒙娜丽莎", "code": "002918", "reason": "建材板块"},
    {"name": "风华高科", "code": "000636", "reason": "电子元件"},
]

print("=" * 80)
print("涨停股近7日行情分析")
print("=" * 80)

end_date = datetime.now()
start_date = end_date - timedelta(days=10)
start_str = start_date.strftime('%Y%m%d')
end_str = end_date.strftime('%Y%m%d')

results = []

for stock in limit_up_stocks[:8]:  # 限制数量，避免超时
    try:
        code = stock['code']
        df = ak.stock_zh_a_hist(symbol=code, period="daily", 
                                 start_date=start_str, end_date=end_str, adjust="qfq")
        if df is not None and len(df) > 0:
            # 取最近7个交易日
            df = df.tail(7)
            first_price = df.iloc[0]['收盘']
            last_price = df.iloc[-1]['收盘']
            pct_chg = ((last_price - first_price) / first_price) * 100
            
            # 7日总成交量
            total_volume = df['成交量'].sum()
            
            results.append({
                "name": stock['name'],
                "code": code,
                "reason": stock['reason'],
                "first_price": first_price,
                "last_price": last_price,
                "pct_chg_7d": pct_chg,
                "volume_7d": total_volume
            })
            print(f"\n【{stock['name']} {code}】{stock['reason']}")
            print(f"  7日前: {first_price:.2f} → 最新: {last_price:.2f}")
            print(f"  7日涨幅: {pct_chg:+.2f}%")
            print(f"  7日总成交量: {total_volume/10000:.2f}万手")
        else:
            print(f"\n【{stock['name']} {code}】暂无K线数据")
    except Exception as e:
        print(f"\n【{stock['name']} {code}】获取失败: {e}")

print("\n" + "=" * 80)