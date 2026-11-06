#!/usr/bin/env python3
"""A股板块复盘数据获取"""
import sys
sys.path.insert(0, '/root/.openclaw/workspace')

import warnings
warnings.filterwarnings('ignore')

print("=" * 60)
print("A股板块复盘数据获取")
print("=" * 60)

# 1. 获取大盘指数
print("\n【一、大盘指数】")
try:
    import akshare as ak
    
    # 指数实时行情
    index_df = ak.stock_zh_index_spot_em()
    # 筛选主要指数
    indices = {
        '上证指数': '000001',
        '深证成指': '399001', 
        '创业板指': '399006',
        '科创50': '000688'
    }
    
    for name, code in indices.items():
        try:
            df = index_df[index_df['代码'] == code]
            if not df.empty:
                print(f"{name}: {df.iloc[0]['最新价']} | 涨跌幅: {df.iloc[0]['涨跌幅']}%")
            else:
                print(f"{name}: 数据未找到")
        except Exception as e:
            print(f"{name}: 获取失败 - {e}")
            
except Exception as e:
    print(f"AKShare获取失败: {e}")
    # 使用腾讯接口备用
    try:
        from stock_tencent import get_stock_quote
        for name, code in indices.items():
            try:
                market = 'sh' if code.startswith('0') else 'sz'
                quote = get_stock_quote(f'{market}{code}')
                print(f"{name}: {quote.get('price','N/A')} | {quote.get('pct_chg','N/A')}%")
            except:
                print(f"{name}: 获取失败")
    except Exception as e2:
        print(f"腾讯接口也失败: {e2}")

# 2. 行业板块排名
print("\n【二、行业板块排名】")
try:
    # 获取行业板块涨跌排行
    sector_df = ak.stock_sector_spot(indicator="涨幅")
    if sector_df is not None and not sector_df.empty:
        print(sector_df.head(20).to_string())
    else:
        # 备用方法
        sector_rank = ak.stock_industry_board_rank(indicator="涨幅", sector_name="行业板块")
        print(sector_rank.head(20).to_string())
except Exception as e:
    print(f"板块排名获取失败: {e}")
    # 尝试获取板块行情
    try:
        board_df = ak.stock_zh_a_spot_em()
        # 筛选行业板块（通常有板块标识）
        print("通过股票数据间接获取...")
    except:
        pass

# 3. 强势/弱势板块
print("\n【三、强势板块 TOP10】")
try:
    strong_df = ak.stock_sector_spot(indicator="涨幅")
    if strong_df is not None:
        print(strong_df.head(10).to_string())
except Exception as e:
    print(f"获取失败: {e}")

print("\n【四、弱势板块 TOP10】")
try:
    weak_df = ak.stock_sector_spot(indicator="跌幅")
    if weak_df is not None:
        print(weak_df.head(10).to_string())
except Exception as e:
    print(f"获取失败: {e}")

# 4. 持仓个股数据
print("\n【五、持仓个股】")
holdings = [
    ('科创50ETF华夏', 'sh588000'),
    ('贵州茅台', 'sh600519'),
    ('新易盛', 'sz300502'),
    ('创业板ETF广发', 'sz159952'),
    ('英维克', 'sz002837'),
    ('中国核建', 'sh601611'),
]

try:
    from stock_tencent import get_stocks_quote
    codes = [h[1] for h in holdings]
    df = get_stocks_quote(codes)
    print(df.to_string())
except Exception as e:
    print(f"腾讯接口获取失败: {e}")
    # 备用：逐个获取
    try:
        from stock_tencent import get_stock_quote
        for name, code in holdings:
            try:
                q = get_stock_quote(code)
                print(f"{name}({code}): {q.get('price','N/A')} | {q.get('pct_chg','N/A')}%")
            except:
                print(f"{name}: 获取失败")
    except:
        pass

print("\n" + "=" * 60)
print("数据获取完成")
print("=" * 60)