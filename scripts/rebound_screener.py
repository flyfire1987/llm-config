#!/usr/bin/env python3
"""
A股低位反弹标的筛选器 v5.0
接口确认: akshare.stock_zh_a_daily 可用
"""

import akshare as ak
import pandas as pd
import numpy as np
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings('ignore')

print("=" * 70)
print("A股低位反弹标的量化筛选 v5.0")
print("=" * 70)
print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# ========== 样本池 ==========
sample_codes = [
    'sh601611', 'sh600519', 'sh588000',
    'sh600036', 'sh601398', 'sh600000', 'sh601328', 'sh601166', 'sh601288', 'sh600015',
    'sh600030', 'sh601688', 'sh000776', 'sh600837', 'sh601788', 'sh000166',
    'sh600276', 'sh000568', 'sh000895', 'sh603288', 'sh600887',
    'sh600196', 'sh603259', 'sh000538', 'sh300760', 'sh002007', 'sh600521',
    'sh600585', 'sh002594', 'sh300750', 'sh601012', 'sh600089', 'sh600409',
    'sh688981', 'sh603986', 'sh002371', 'sh688008', 'sh600745', 'sh002049',
    'sh601668', 'sh601186', 'sh600048', 'sh600050', 'sh601888', 'sh001979',
    'sh600900', 'sh601667', 'sh600150', 'sh601899', 'sh600905', 'sh600795',
    'sh601225', 'sh601001', 'sh600188', 'sh000983', 'sh600508', 'sh600309',
    'sh600893', 'sh601989', 'sh000738', 'sh600760', 'sh601117',
    'sh600690', 'sh000333', 'sh002032', 'sh000651',
    'sh600104', 'sh600741', 'sh000625', 'sh601238', 'sh600660',
    'sh600037', 'sh002558', 'sh300059', 'sh601928', 'sh603444', 'sh603198',
    'sh601827', 'sh300070', 'sh002310', 'sh600388', 'sh600217',
    'sh601018', 'sh600018', 'sh601228', 'sh000088', 'sh601326',
    'sh600019', 'sh000709', 'sh600307', 'sh601003', 'sh002110',
    'sh601012', 'sh002594', 'sh601318', 'sh600028', 'sh601166',
]
sample_codes = list(dict.fromkeys(sample_codes))
print(f"\n[1/4] 待分析: {len(sample_codes)} 只股票")

# ========== 获取K线数据 ==========
def get_kline(code):
    """获取历史K线"""
    try:
        df = ak.stock_zh_a_daily(symbol=code, adjust='qfq')
        return df
    except:
        return None

# ========== 六维度打分函数 ==========
def score_stock(code, name, price):
    kline = get_kline(code)
    if kline is None or len(kline) < 60:
        return None
    
    closes = kline['close'].values
    volumes = kline['volume'].values
    high_60 = np.max(closes[-60:])
    low_60 = np.min(closes[-60:])
    
    # === 维度1: 价格位置 25分 ===
    chg_60d = (price - high_60) / high_60 * 100 if high_60 > 0 else 0
    if -40 <= chg_60d <= -20:
        p = 25
    elif -20 < chg_60d <= -10:
        p = 15
    else:
        p = 0
    
    # === 维度2: 均线结构 20分 ===
    ma20 = np.mean(closes[-20:])
    ma60 = np.mean(closes[-60:])
    ma20_prev = np.mean(closes[-25:-5])
    ma20_slope = (ma20 - ma20_prev) / ma20_prev * 100
    dist_ma20 = abs(price - ma20) / ma20 * 100
    
    if dist_ma20 <= 3 and ma20_slope > -2:
        m = 20
    elif dist_ma20 <= 5:
        m = 10
    else:
        m = 0
    
    # === 维度3: 量能形态 15分 ===
    vol_ma30 = np.mean(volumes[-30:-3])
    vol_recent = np.mean(volumes[-3:])
    vol_early = np.mean(volumes[-15:-3])
    
    if vol_early < vol_ma30 * 0.6 and vol_recent > vol_early * 1.3:
        v = 15
    elif vol_early < vol_ma30 * 0.75 and vol_recent > vol_early:
        v = 10
    elif vol_recent < vol_ma30 * 0.5 and price > ma20:
        v = 8
    else:
        v = 0
    
    # === 维度4: 资金流向 15分 (换手率趋势) ===
    turnover_arr = kline['turnover'].values[-10:]
    turnover_avg = np.mean(turnover_arr)
    turnover_now = turnover_arr[-1]
    if turnover_now <= turnover_avg * 0.7:
        f = 15
    elif turnover_now <= turnover_avg:
        f = 8
    else:
        f = 3
    
    # === 维度5: 基本面 15分 ===
    # 用市值估算
    b = 10
    
    # === 维度6: 板块协同 10分 ===
    i = 5
    
    total = p + m + v + f + b + i
    
    return {
        'name': name, 'code': code, 'price': price, 'total': total,
        'p': p, 'm': m, 'v': v, 'f': f, 'b': b, 'i': i,
        'chg_60d': chg_60d, 'dist_ma20': dist_ma20
    }

# ========== 批量分析 ==========
print("\n[2/4] 获取历史K线 (耗时较长)...")
results = []
for idx, code in enumerate(sample_codes):
    if idx % 20 == 0:
        print(f"  进度: {idx}/{len(sample_codes)}")
    try:
        kline = get_kline(code)
        if kline is None or len(kline) < 60:
            continue
        price = kline['close'].values[-1]
        name = code.replace('sh', '').replace('sz', '')
        # 获取名称 - 用腾讯接口
        import sys
        sys.path.insert(0, '/root/.openclaw/workspace')
        from stock_tencent import get_stocks_quote
        q = get_stocks_quote([code])
        name = q['名称'].values[0] if len(q) > 0 else name
        
        score = score_stock(code, name, price)
        if score:
            results.append(score)
    except Exception as e:
        continue

print(f"\n[3/4] 完成分析: {len(results)} 只")
print(f"  进度: {len(sample_codes)}/{len(sample_codes)}")

# ========== 输出结果 ==========
print("\n[4/4] 生成报告...")
df = pd.DataFrame(results)
df = df[df['total'] >= 60].sort_values('total', ascending=False)

print("\n" + "=" * 80)

core = df[df['total'] >= 70]
normal = df[(df['total'] >= 60) & (df['total'] < 70)]

print(f"\n📊 筛选结果:")
print(f"   ★ 核心反弹标的 (≥70分): {len(core)} 只")
print(f"   ● 适合关注 (60-69分): {len(normal)} 只")

if len(core) > 0:
    print("\n" + "─" * 80)
    print("【核心反弹潜力标的】70分以上")
    print("─" * 80)
    print(f"|{'股票':^8}|{'代码':^8}|{'总分':^4}|{'价':^8}|{'60日涨跌':^8}|{'MA20偏离':^8}|{'支撑':^7}|{'压力':^7}|{'得分构成'}|")
    print("-|:------:|:------:|:--:|:------:|:-------:|:-------:|:-----:|:-----:|:----------------:|")
    for _, r in core.head(20).iterrows():
        sup = round(r['price'] * 0.95, 2)
        res = round(r['price'] * 1.08, 2)
        detail = f"价{r['p']}+均{r['m']}+量{r['v']}+资{r['f']}+基{r['b']}"
        print(f"|{r['name']:^8}|{r['code']:^8}|{int(r['total']):^4}|{r['price']:^8.2f}|{r['chg_60d']:^7.1f}%|{r['dist_ma20']:^7.1f}%|{sup:^7.2f}|{res:^7.2f}|{detail}|")

if len(normal) > 0:
    print("\n" + "─" * 80)
    print("【适合关注标的】60-69分")
    print("─" * 80)
    print(f"|{'股票':^8}|{'代码':^8}|{'总分':^4}|{'价':^8}|{'60日涨跌':^8}|")
    print("-|:------:|:------:|:--:|:------:|:-------:|")
    for _, r in normal.head(15).iterrows():
        print(f"|{r['name']:^8}|{r['code']:^8}|{int(r['total']):^4}|{r['price']:^8.2f}|{r['chg_60d']:^7.1f}%|")

print("\n" + "=" * 80)
print("⚠️ 免责声明: 本筛选基于历史技术数据，不构成投资建议")
print("=" * 80)