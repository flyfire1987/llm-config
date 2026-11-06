#!/usr/bin/env python3
"""反弹标的筛选 - v5 放宽条件"""
import urllib.request, json, pandas as pd, numpy as np, time, warnings, re
warnings.filterwarnings('ignore')

TODAY = '2026-04-16'

def get_all_codes():
    try:
        import akshare as ak
        df = ak.stock_info_a_code_name()
        result = []
        for _, row in df.iterrows():
            code = row['code']
            if code.startswith(('0', '3', '6')):
                prefix = 'sz' if code.startswith(('0', '3')) else 'sh'
                result.append({'code': code, 'name': row['name'], 'full': f"{prefix}{code}"})
        return result
    except Exception as e:
        print(f'akshare失败: {e}')
        return []

def batch_market_cap(codes_full, batch_size=80):
    results = []
    total = len(codes_full)
    for i in range(0, total, batch_size):
        batch = codes_full[i:i+batch_size]
        code_str = ','.join([c['full'] for c in batch])
        url = f'https://qt.gtimg.cn/q={code_str}'
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read().decode('gbk', errors='ignore')
            lines = data.strip().split('\n')
            for line in lines:
                if '=' not in line: continue
                parts = line.split('=')[1].strip('";').split('~')
                if len(parts) < 50: continue
                try:
                    mkt_cap = float(parts[44]) if parts[44] else 0
                    if mkt_cap < 100: continue
                    name = parts[1] if len(parts) > 1 else ''
                    price = float(parts[3]) if parts[3] else 0
                    pct_chg = float(parts[32]) if parts[32] else 0
                    turnover = float(parts[38]) if parts[38] else 0
                    results.append({
                        'code': parts[2] if len(parts) > 2 else '',
                        'name': name,
                        'price': price,
                        'pct_chg': pct_chg,
                        'turnover': turnover,
                        'market_cap': mkt_cap
                    })
                except: pass
        except: pass
        time.sleep(0.06)
    return pd.DataFrame(results)

def get_kline(full_code, count=45):
    url = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayhfq&param={full_code},day,2026-02-01,{TODAY},{count},qfp'
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0')
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = resp.read().decode('utf-8', errors='ignore')
        json_str = data[data.index('=') + 1:]
        obj = json.loads(json_str)
        qfq_key = list(obj['data'].values())[0] if 'data' in obj else {}
        qfq_data = qfq_key.get('qfqday') or qfq_key.get('day') or []
        if not qfq_data: return None
        df = pd.DataFrame(qfq_data, columns=['date','open','close','high','low','volume'])
        for col in ['close','open','high','low','volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        return df.dropna().reset_index(drop=True)
    except:
        return None

def analyze(kline, mkt_info):
    if kline is None or len(kline) < 25: return None
    kline = kline.sort_values('date').tail(40).reset_index(drop=True)
    n = len(kline)
    if n < 20: return None

    ma20 = kline['close'].rolling(20).mean().iloc[-1]
    close = kline.iloc[-1]['close']
    dist = (close - ma20) / ma20 * 100
    if abs(dist) > 5: return None  # 放宽到±5%

    # 近30日高点
    recent_30 = kline.tail(30)
    high_val = recent_30['high'].max()
    offset = n - 30
    high_idx_global = recent_30['high'].idxmax() + offset
    days_ago = n - 1 - high_idx_global
    if days_ago < 2 or days_ago > 15: return None  # 放宽到15天
    pullback = (close - high_val) / high_val * 100
    if pullback >= 0 or pullback < -30: return None  # 放宽到-30%

    # 近5日整体下跌 OR 近3-4日内有2天以上在跌
    r5 = kline.tail(5)['close'].values
    r5_chg = (r5[-1] - r5[0]) / r5[0] * 100
    r4 = kline.tail(4)['close'].values
    r3 = kline.tail(3)['close'].values
    consec = sum(1 for i in range(len(r3)-1) if r3[i] > r3[i+1])
    consec_4 = sum(1 for i in range(len(r4)-1) if r4[i] > r4[i+1])
    if r5_chg >= 0 and consec < 2: return None  # 近5日上涨且近3日无连续下跌

    # 缩量回调：近3日均量 < 前5日均量
    vol_r = kline.tail(3)['volume'].mean()
    vol_p = kline.tail(8).iloc[:-3]['volume'].mean()
    if vol_p <= 0 or vol_r >= vol_p: return None  # 缩量才通过

    turnover = mkt_info.get('turnover', 0) if mkt_info else 0
    if turnover < 0.5: return None  # 换手率太低

    broken = '是' if dist < -2 else '否'
    return {
        'dist_ma20': round(dist, 1),
        'broken': broken,
        'drop_days': max(consec, consec_4),
        'recent_5_chg': round(r5_chg, 1),
        'pullback': round(pullback, 1),
        'turnover': turnover,
    }

SECTOR_MAP = [
    (re.compile('科技|智能|软件|数据|云|AI|互联网|网络|通信|5G'), 'AI科技'),
    (re.compile('医药|医疗|生物|健康'), '医药'),
    (re.compile('新能源|光伏|锂电|储能|电力|风电|水电'), '新能源'),
    (re.compile('芯片|半导体|集成电路|电子|计算机'), '半导体'),
    (re.compile('银行|证券|保险|金融'), '金融'),
    (re.compile('白酒|饮料|食品|消费|零售'), '消费'),
    (re.compile('军工|防务|航空|航天|国防'), '军工'),
    (re.compile('化工|材料|石油|能源|煤炭'), '化工'),
    (re.compile('汽车|整车|零部件'), '汽车'),
    (re.compile('地产|建筑|建材|钢铁|装修'), '地产基建'),
    (re.compile('传媒|教育|文化|旅游|酒店'), '文教传媒'),
    (re.compile('港口|航运|物流|运输'), '港口航运'),
]

def guess_sector(name):
    for pat, sector in SECTOR_MAP:
        if pat.search(name): return sector
    return '热门题材'

# ==== 主程序 ====
print('获取股票列表...')
all_stocks = get_all_codes()
print(f'共 {len(all_stocks)} 只')

print('批量获取市值...')
mkt_df = batch_market_cap(all_stocks)
print(f'市值>100亿: {len(mkt_df)} 只')

if len(mkt_df) == 0:
    print('无法获取市值数据，退出')
    exit(1)

mkt_dict = {row['code']: row for _, row in mkt_df.iterrows()}
print(f'开始K线分析 ({len(mkt_df)} 只)...')

results = []
for idx, (_, row) in enumerate(mkt_df.iterrows()):
    if (idx+1) % 200 == 0:
        print(f'  进度 {idx+1}/{len(mkt_df)}')
    kline = get_kline(row['code'])
    anal = analyze(kline, row.to_dict())
    if anal:
        results.append({
            'name': row['name'],
            'code': row['code'].replace('sh','').replace('sz',''),
            'drop_days': anal['drop_days'],
            'dist_ma20': f"{anal['dist_ma20']:+.1f}%",
            'broken': anal['broken'],
            'recent_5_chg': anal['recent_5_chg'],
            'turnover': anal['turnover'],
            'price': row['price'],
            'market_cap': row['market_cap'],
            'sector': guess_sector(row['name']),
        })
    time.sleep(0.04)

print(f'初筛通过: {len(results)} 只')

if not results:
    print('无符合条件的标的（近期市场偏强，符合条件的回调标的较少）')
else:
    results_df = pd.DataFrame(results)
    # 按近5日跌幅降序，取前20
    results_df = results_df.sort_values(['recent_5_chg','turnover'], ascending=[True, False]).head(20)
    
    out = []
    for _, r in results_df.iterrows():
        if float(r['dist_ma20'][:-1]) < -2:
            op = '观望'
        else:
            op = '可低吸'
        out.append(f"| {r['name']} | {r['code']} | {r['drop_days']}天 | {r['dist_ma20']} | {r['broken']} | {r['sector']} | {op} |")
    
    print()
    print("| 股票名称 | 代码 | 回调天数 | 距20日线 | 是否有效跌破 | 热门板块 | 操作建议 |")
    print("|:--------:|:----:|:--------:|:--------:|:------------:|:--------:|:--------:|")
    print('\n'.join(out))

print('\nDone.')
