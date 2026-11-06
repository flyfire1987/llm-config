#!/usr/bin/env python3
"""
A股反弹标的筛选 v2 - 扩大股票池，降低门槛
"""
import sys
sys.path.insert(0, '/root/.openclaw/workspace')
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import urllib.request
import json

print("=" * 70)
print("🔍 A股反弹标的筛选")
print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 70)

# 股票池：东方财富行业板块龙头 + 主要宽基成分股（扩大范围）
STOCK_POOL = [
    # 消费
    'sh600519','sh000858','sz000568','sh603288','sh600887','sh600197','sh000596',
    'sh600132','sh002304','sz000895','sh600305','sh603369','sh000869','sh600054',
    # 金融
    'sh600036','sh601318','sh600016','sh601166','sh601328','sh601288','sh601398',
    'sh601939','sh601088','sh601857','sh600030','sh601211','sh600837','sh600999',
    # 能源/工业
    'sh600028','sh601899','sh600489','sh600507','sh601600','sh600111','sh601225',
    'sh600188','sh601666','sh600583','sh600026','sh600115','sh600018','sh601919',
    # 科技/新能源
    'sz000333','sz002594','sz300750','sh601012','sh600690','sh600460','sh600406',
    'sh002415','sh600585','sh600031','sh601865','sh600089','sh603806','sh002466',
    'sz002812','sh600563','sh600933','sh603185','sh603659','sh688041','sh688126',
    'sh688008','sh688012','sh002049','sz000063','sh600570','sh600588','sh600276',
    # 医药
    'sh600196','sh603259','sh600521','sh000661','sh002007','sh300760','sh002252',
    'sh600329','sh600253','sh603707','sh002001','sh000513','sh300347','sh002422',
    # 基建/地产
    'sh601668','sh601186','sh601800','sh600048','sh600104','sh600153','sh600606',
    'sh601117','sh601669','sh600170','sh002146','sz000002','sz001979','sh600383',
    # 半导体/电子
    'sh688981','sh600584','sh002371','sh603501','sh002456','sh000725','sh600703',
    'sh002459','sh688399','sh688082','sh688126','sh002241','sh002475','sh600745',
    # 化工/材料
    'sh600309','sh600346','sh600486','sh600523','sh002601','sh002326','sh600496',
    'sh601216','sh600409','sh603260','sh002250','sh002648',
    # 军工
    'sh601989','sh600893','sh600316','sh600435','sh000738','sh601106','sh600760',
    'sh600765','sh002013','sh601117','sh600391',
    # 电力
    'sh600900','sh600905','sh600795','sh600863','sh600642','sh601016','sh600674',
    'sh600236','sh600886','sh000539','sh002608',
    # 运输/物流
    'sh601111','sh600115','sh601006','sh600026','sh600221','sh601919','sh600787',
    # TMT
    'sh601669','sh600588','sh600570','sh300496','sh688111','sh688036','sz002230',
    'sh603160','sh300033','sh002410','sh002439','sh002195','sh002558','sh300059',
    # 汽车
    'sh600104','sh600660','sh601127','sh600741','sh000625','sz002594','sh601238',
    'sz002048','sh600699','sh002126','sz000581',
    # 纺织/农业
    'sh600398','sh603055','sh002293','sz000403','sz000895','sh002311','sh002714',
    # 其他
    'sh600009','sh600583','sh600690','sh603806','sh601888','sh600977','sh601598',
    'sh603027','sh601066','sh601319','sh600000','sh601288','sh600050','sh601818',
    'sh600036','sh600016','sh600837','sh600999','sh601336','sh600135','sh002500',
]

# 去重
STOCK_POOL = list(dict.fromkeys(STOCK_POOL))
print(f"\n[1/3] 股票池: {len(STOCK_POOL)} 只")

# 获取K线并筛选
print("\n[2/3] 扫描K线数据...")
today_str = datetime.now().strftime('%Y%m%d')
start_date = (datetime.now() - timedelta(days=15)).strftime('%Y%m%d')

results = []
checked = 0
errors = 0

for code in STOCK_POOL:
    try:
        # 获取K线
        kline_url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_varkline=qfq&param={code},day,,,15,qfq&r=0.1"
        with urllib.request.urlopen(kline_url, timeout=8) as resp:
            raw = resp.read().decode('utf-8')
        
        kdata = json.loads(raw)
        day_data = kdata.get('data', {}).get(code, {}).get('qfqday', [])
        if not day_data or len(day_data) < 5:
            day_data = kdata.get('data', {}).get(code, {}).get('day', [])
        
        if not day_data or len(day_data) < 5:
            continue
        
        closes = [float(d[2]) for d in day_data]
        volumes = [float(d[5]) if len(d) > 5 else 0 for d in day_data]
        dates = [d[0] for d in day_data]
        
        n = len(closes)
        # 近3日
        c0, c1, c2 = closes[-3], closes[-4] if len(closes) > 3 else closes[-2], closes[-5] if len(closes) > 4 else closes[-3]
        
        # 3日跌幅: 从第1天到第3天
        cum_drop = (closes[-1] / closes[-3] - 1) * 100 if len(closes) >= 3 else 0
        
        # 近3日每日涨跌
        day1_pct = (closes[-1] / closes[-2] - 1) * 100 if len(closes) >= 2 else 0
        day2_pct = (closes[-2] / closes[-3] - 1) * 100 if len(closes) >= 3 else 0
        day3_pct = (closes[-3] / closes[-4] - 1) * 100 if len(closes) >= 4 else 0
        
        # 昨日是否止跌（小阴小阳/十字星，成交量萎缩）
        last_pct = day1_pct
        last_vol = volumes[-1]
        prev_vol = volumes[-2] if len(volumes) >= 2 else last_vol
        vol_ratio = last_vol / prev_vol if prev_vol > 0 else 1
        
        volume_shrink = vol_ratio < 0.85
        stable = abs(last_pct) < 1.8  # 昨日涨跌幅<1.8%
        not_dropping = day1_pct > -2.0  # 昨日不再暴跌
        
        # 20日线
        ma20_arr = pd.Series(closes).rolling(20).mean()
        ma20 = ma20_arr.iloc[-1] if len(ma20_arr) >= 20 else None
        current_price = closes[-1]
        
        if ma20 is not None:
            ma20_distance = (current_price / ma20 - 1) * 100
            broken_ma20 = current_price < ma20 * 0.97
        else:
            ma20_distance = 0
            broken_ma20 = False
        
        # 筛选条件: 近3日跌幅>5%，且昨日已止跌（缩量小K线）
        if cum_drop < -5 and volume_shrink and stable and not_dropping:
            # 获取名称
            try:
                info_url = f"https://qt.gtimg.cn/q={code}"
                with urllib.request.urlopen(info_url, timeout=5) as resp:
                    info_raw = resp.read().decode('gbk')
                name = info_raw.split('~')[1] if '~' in info_raw else code
            except:
                name = code
            
            results.append({
                '股票名称': name,
                '代码': code,
                '3日跌幅': round(cum_drop, 1),
                '昨日涨跌': round(last_pct, 1),
                '距20日线': round(ma20_distance, 1),
                '有效跌破': '是' if broken_ma20 else '否',
                '操作建议': '观望' if broken_ma20 else '可低吸',
                '换手率低': '是' if vol_ratio < 0.6 else '否',
            })
    except Exception as e:
        errors += 1
        continue
    
    checked += 1
    if checked % 40 == 0:
        print(f"  已扫描 {checked}/{len(STOCK_POOL)} 只... (结果:{len(results)})")

print(f"\n  完成扫描 {checked} 只, 错误 {errors} 只")
print(f"  初步符合: {len(results)} 只")

# 排序输出
print("\n[3/3] 生成报告...")
print("=" * 75)

if not results:
    print("⚠️ 今日未筛选出符合条件的反弹标的")
    print("说明: 近3日跌幅>5%且已止跌的股票数量为0")
    print("可能市场整体偏弱或已出现反弹，注意风险")
else:
    result_df = pd.DataFrame(results)
    # 按热度（跌幅大的优先）
    result_df = result_df.sort_values('3日跌幅', ascending=True).head(20)
    
    print(f"\n| 股票名称 | 代码 | 3日跌幅 | 距20日线 | 有效跌破 | 操作建议 |")
    print("|:--------:|:----:|:-------:|:--------:|:--------:|:--------:|")
    for _, row in result_df.iterrows():
        name = row['股票名称']
        code = row['代码']
        drop = row['3日跌幅']
        ma20d = row['距20日线']
        broken = row['有效跌破']
        advice = row['操作建议']
        
        ma20_str = f"{'+' if ma20d > 0 else ''}{ma20d}%"
        drop_str = f"{drop}%"
        advice_icon = "✅" if advice == "可低吸" else "👀"
        print(f"| {name} | {code} | {drop_str} | {ma20_str} | {broken} | {advice_icon}{advice} |")

print("\n" + "=" * 75)
print("⚠️ 仅供参考，不构成投资建议，投资有风险，决策需谨慎")