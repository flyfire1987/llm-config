#!/usr/bin/env python3
"""财经早报数据采集脚本"""
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

print("=" * 60)
print("财经早报数据采集")
print("=" * 60)

# 1. 获取今日A股市场概况
print("\n【1. A股市场概况】")
try:
    index_df = ak.stock_zh_index_spot_em()
    # 沪深主要指数
    major_indices = index_df[index_df['代码'].isin(['000001', '399001', '399006', '000016', '000688'])]
    for _, row in major_indices.iterrows():
        print(f"{row['名称']}: {row['最新价']}  涨跌幅: {row['涨跌幅']}%")
except Exception as e:
    print(f"获取指数失败: {e}")

# 2. 获取今日涨停股
print("\n【2. 今日涨停股（前20）】")
try:
    limit_up_df = ak.stock_zt_pool_em(date=datetime.now().strftime('%Y%m%d'))
    if limit_up_df is not None and len(limit_up_df) > 0:
        print(f"今日涨停数: {len(limit_up_df)}")
        for _, row in limit_up_df.head(20).iterrows():
            print(f"  {row['名称']} {row['代码']} | 原因: {row.get('涨停统计', '—')}")
    else:
        print("今日暂无涨停数据（可能非交易日或数据延迟）")
except Exception as e:
    print(f"获取涨停板失败: {e}")

# 3. 获取今日热门板块
print("\n【3. 热门板块涨跌】")
try:
    sector_df = ak.stock_sector_spot()
    if sector_df is not None:
        # 涨跌幅前10
        top_gainers = sector_df.nlargest(10, '涨跌幅')
        print("涨幅前10板块:")
        for _, row in top_gainers.iterrows():
            print(f"  {row['名称']}: +{row['涨跌幅']}%")
except Exception as e:
    print(f"获取板块数据失败: {e}")

# 4. 获取大盘资金流向
print("\n【4. 大盘资金流向】")
try:
    money_df = ak.stock_individual_fund_flow(stock="000001", market="sh")
    if money_df is not None and len(money_df) > 0:
        print(money_df.tail(5).to_string())
except Exception as e:
    print(f"获取资金流向失败: {e}")

# 5. 获取近期强势股
print("\n【5. 近5日强势股（主力净流入前10）】")
try:
    # 个股资金流向排行
    stock_flow = ak.stock_individual_fund_flow_rank(indicator="今日")
    if stock_flow is not None and len(stock_flow) > 0:
        top_flow = stock_flow.head(10)
        print(top_flow[['代码', '名称', '最新价', '涨跌幅', '主力净流入']].to_string())
except Exception as e:
    print(f"获取强势股失败: {e}")

print("\n" + "=" * 60)
print("数据采集完成")
print("=" * 60)