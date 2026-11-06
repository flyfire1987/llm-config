import akshare as ak

# 获取涨停股详情
print("=== 今日涨停 ===")
try:
    zt = ak.stock_zt_pool_em(date="20260522")
    cols = zt.columns.tolist()
    print(cols)
    top = zt.head(20)
    for _, row in top.iterrows():
        print(f"{row['代码']} {row['名称']} 涨幅:{row['涨跌幅']}% 成交额:{row['成交额']}亿 行业:{row.get('所属行业','')}")
except Exception as e:
    print(f"涨停失败: {e}")

print("\n=== 强势股 ===")
try:
    strong = ak.stock_zt_pool_strong_em(date="20260522")
    print(strong.columns.tolist())
    top2 = strong.head(20)
    for _, row in top2.iterrows():
        print(f"{row['代码']} {row['名称']} 涨幅:{row['涨跌幅']}% 成交额:{row['成交额']}亿 行业:{row.get('所属行业','')}")
except Exception as e:
    print(f"强势股失败: {e}")