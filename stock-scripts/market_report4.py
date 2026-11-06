import akshare as ak

# 获取行业涨跌幅排行
print("=== 行业板块 ===")
try:
    df = ak.stock_board_industry_name_em()
    print(df.columns.tolist())
    result = df.sort_values('涨跌幅', ascending=False).head(30)
    for _, row in result.iterrows():
        print(f"{row['名称']}: {row['涨跌幅']}%")
except Exception as e:
    print(f"失败: {e}")

print("\n=== 概念板块 ===")
try:
    df2 = ak.stock_board_concept_name_em()
    print(df2.columns.tolist())
    result2 = df2.sort_values('涨跌幅', ascending=False).head(30)
    for _, row in result2.iterrows():
        print(f"{row['名称']}: {row['涨跌幅']}%")
except Exception as e:
    print(f"失败: {e}")