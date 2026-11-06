import akshare as ak
import pandas as pd
import sys
sys.stdout.reconfigure(encoding='utf-8')

stocks = [
    ("赤峰黄金", "600988"),
    ("晓程科技", "300139"),
    ("四川黄金", "001337"),
    ("新易盛", "300502"),
    ("贵州茅台", "600519"),
    ("中国核建", "601611"),
    ("英维克", "002837"),
    ("东方财富", "300059"),
]

print("=" * 70)
print("30分钟趋势 + 主力资金净流入 检测")
print("=" * 70)

for name, code in stocks:
    try:
        # 主力资金 - 单笔队列资金流向
        try:
            df_money = ak.stock_individual_fund_flow(stock=code, market="sh")
        except:
            try:
                df_money = ak.stock_individual_fund_flow(stock=code, market="sz")
            except:
                df_money = None

        # 30分钟K线
        try:
            df_kline = ak.stock_zh_index_daily(symbol="sh" + code)
            if df_kline is None or len(df_kline) < 6:
                # try using stock kline
                df_kline = ak.stock_zh_kline(symbol=code, period="30", adjust="qfq", start_date="20260511")
        except Exception as e:
            df_kline = None

        main_net = None
        trend = "未知"

        if df_money is not None and len(df_money) > 0:
            cols = df_money.columns.tolist()
            # 尝试找主力净流入相关列
            net_cols = [c for c in cols if '净' in c or 'net' in c.lower()]
            if net_cols:
                main_net = df_money[net_cols[0]].iloc[-1]

        if df_kline is not None and len(df_kline) >= 6:
            closes = df_kline['close'].tail(6).values
            diff = closes[-1] - closes[0]
            pct = diff / closes[0] * 100 if closes[0] != 0 else 0
            if pct > 1:
                trend = "📈上升"
            elif pct < -1:
                trend = "📉下降"
            else:
                trend = "➡️中性"
            # V型检测
            if len(closes) >= 6:
                c0, c1, c2, c3, c4, c5 = closes[0], closes[1], closes[2], closes[3], closes[4], closes[5]
                if c2 < c0 and c4 > c2 and c5 > c4:
                    trend = "V型反弹"
        else:
            trend = "数据不足"

        print(f"\n{name}({code})")
        print(f"  30分钟趋势: {trend}")
        print(f"  主力净流入: {main_net if main_net is not None else 'N/A'}")

    except Exception as e:
        print(f"\n{name}({code}) - 获取失败: {e}")
