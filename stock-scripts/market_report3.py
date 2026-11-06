import akshare as ak

print("=== 行业板块 ===")
try:
    sector_df = ak.stock_board_industry_name_em()
    print(sector_df.columns.tolist())
    top = sector_df.sort_values('涨跌幅', ascending=False).head(20)
    print(top.to_string())
except Exception as e:
    print(f"失败: {e}")

print("\n=== 热点概念 ===")
try:
    concept_df = ak.stock_board_concept_name_em()
    print(concept_df.columns.tolist())
    top2 = concept_df.sort_values('涨跌幅', ascending=False).head(20)
    print(top2.to_string())
except Exception as e:
    print(f"失败: {e}")

print("\n=== 涨停股详情 ===")
try:
    zt = ak.stock_zt_pool_em(date="20260522")
    print(zt.columns.tolist())
    print(zt.head(15).to_string())
except Exception as e:
    print(f"涨停失败: {e}")

print("\n=== 炸板股 ===")
try:
    zt_strong = ak.stock_zt_pool_strong_em(date="20260522")
    print(zt_strong.columns.tolist())
    print(zt_strong.head(10).to_string())
except Exception as e:
    print(f"炸板失败: {e}")