#!/usr/bin/env python3
"""
板块数据获取（新版，多源）
主源：腾讯 qt.gtimg.cn（通过 data_source 模块）
旧 akshare 接口保留为 fallback
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 50)
print("板块数据")
print("=" * 50)


def get_top_movers_via_ak() -> tuple:
    """旧 akshare 路径 - 板块排行"""
    try:
        import warnings
        warnings.filterwarnings('ignore')
        import akshare as ak
        print("\n【行业板块排名 TOP20 按涨幅（akshare）】")
        df = ak.stock_sector_spot(indicator="涨幅")
        if df is not None and not df.empty:
            print(df.head(20).to_string())
        print("\n【概念板块排名 TOP20 按涨幅（akshare）】")
        df2 = ak.stock_concept_spot(indicator="涨幅")
        if df2 is not None and not df2.empty:
            print(df2.head(20).to_string())
        return True, None
    except Exception as e:
        return False, str(e)


def get_top_movers_via_tencent() -> tuple:
    """新版路径 - 通过腾讯拉取"""
    try:
        from data_source import get_stocks_multi_source
        print("\n【贵金属板块行情（腾讯源）】")
        # 关键板块的代表性个股
        precious = ["600988", "600547", "601899", "600489", "001337",
                    "002155", "601069", "002716", "000426"]
        data = get_stocks_multi_source(precious)
        if data:
            print(f"{'名称':<10} {'代码':<8} {'现价':<8} {'涨跌幅':<8} {'成交额(亿)':<10}")
            print("-" * 50)
            items = sorted(data.values(), key=lambda x: x.get("change_pct", 0), reverse=True)
            for it in items:
                turnover = it.get("turnover", 0)
                turnover_yi = turnover / 1e4 if turnover else 0
                print(f"{it['name']:<10} {it['code']:<8} {it['price']:<8.2f} "
                      f"{it['change_pct']:+.2f}%   {turnover_yi:.2f}")
            return True, None
        return False, "腾讯源无数据"
    except Exception as e:
        return False, str(e)


# 1. 先尝试新源
ok, err = get_top_movers_via_tencent()
if not ok:
    print(f"\n⚠️ 腾讯源失败: {err}")
    print("切换到 akshare（旧源）...")
    ok2, err2 = get_top_movers_via_ak()
    if not ok2:
        print(f"❌ akshare 也失败: {err2}")
        print("\n💡 建议:")
        print("  1. 检查东方财富是否解封（可能本机IP被ban）")
        print("  2. 重启服务器换公网IP")
        print("  3. 临时使用 web_search.py + data_source.py")

# 2. 补充：相关新闻
print("\n" + "=" * 50)
print("【相关新闻（搜狗）】")
print("=" * 50)
try:
    from web_search import search
    results = search("A股 贵金属板块 黄金股 走势", 5)
    if results and "error" not in results[0]:
        for i, r in enumerate(results, 1):
            print(f"{i}. {r['title']}")
            if r.get("url"):
                print(f"   {r['url'][:90]}")
    else:
        print("⚠️ 搜狗搜索暂不可用")
except Exception as e:
    print(f"❌ 搜索失败: {e}")

print("\n" + "=" * 50)
