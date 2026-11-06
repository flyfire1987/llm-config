import sys
sys.path.insert(0, '/root/.openclaw/workspace')
from stock_tencent import get_stock_quote, get_stocks_quote, get_stock_by_name

print("=== 大盘指数 ===")
indices = [
    ('sh000001', '上证指数'),
    ('sz399001', '深证成指'),
    ('sz399006', '创业板指'),
    ('sh000688', '科创50'),
    ('sh000016', '上证50'),
]
for code, name in indices:
    try:
        q = get_stock_quote(code)
        print(f"{name}: {q['price']}  涨跌幅: {q['pct_chg']}%  成交额: {q['amount']}亿")
    except Exception as e:
        print(f"{name}: 获取失败 {e}")

print("\n=== 行业涨幅前15 ===")
try:
    import akshare as ak
    sector_df = ak.stock_board_industry_name_em()
    cols = sector_df.columns.tolist()
    print(cols)
    top = sector_df.head(15)
    print(top.to_string())
except Exception as e:
    print(f"行业板块失败: {e}")

print("\n=== 热点概念前15 ===")
try:
    concept_df = ak.stock_board_concept_name_em()
    cols2 = concept_df.columns.tolist()
    print(cols2)
    top2 = concept_df.head(15)
    print(top2.to_string())
except Exception as e:
    print(f"概念板块失败: {e}")

print("\n=== 今日涨停个股（前20）===")
try:
    limit_up = ak.stock_zt_pool_em(date="20260522")
    print(limit_up.head(20)[['代码','名称','涨停价','流通市值','涨停统计','连板数']].to_string())
except Exception as e:
    print(f"涨停榜失败: {e}")

print("\n=== 今日跌停个股（前10）===")
try:
    limit_down = ak.stock_zt_pool_strong_em(date="20260522")
    print(limit_down.head(10)[['代码','名称','最新价','跌停价','流通市值']].to_string())
except Exception as e:
    print(f"跌停榜失败: {e}")