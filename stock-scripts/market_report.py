import akshare as ak
import pandas as pd

# 获取大盘指数实时行情
print("=== 大盘指数 ===")
try:
    index_df = ak.index_zh_a_spot_em()
    major_indices = index_df[index_df['代码'].isin(['000001', '399001', '399006', '000688', '000016'])]
    print(major_indices[['代码', '名称', '最新价', '涨跌幅', '成交额']].to_string())
except Exception as e:
    print(f"获取失败: {e}")

print("\n=== 行业板块 ===")
try:
    sector_df = ak.stock_board_industry_name_em()
    top_sector = sector_df.head(15)[['名称', '涨跌幅', '成交额', '上涨家数', '下跌家数']]
    print(top_sector.to_string())
except Exception as e:
    print(f"获取失败: {e}")

print("\n=== 热点概念板块 ===")
try:
    concept_df = ak.stock_board_concept_name_em()
    top_concept = concept_df.head(15)[['名称', '涨跌幅', '成交额', '上涨家数', '下跌家数']]
    print(top_concept.to_string())
except Exception as e:
    print(f"获取失败: {e}")

print("\n=== 涨幅前十个股 ===")
try:
    stock_df = ak.stock_zh_a_spot_em()
    top_stocks = stock_df.sort_values('涨跌幅', ascending=False).head(10)[['代码', '名称', '最新价', '涨跌幅', '成交额']]
    print(top_stocks.to_string())
except Exception as e:
    print(f"获取失败: {e}")