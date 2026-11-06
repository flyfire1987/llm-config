"""
筛选反弹标的 - 精简版
只验证今日跌幅最大的前50只，控制总请求量，快速出结果
"""

import sys
sys.path.insert(0, '/root/.openclaw/workspace')

import pandas as pd
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')
import requests
import time

def parse_market_cap(s):
    if pd.isna(s): return 0.0
    s = str(s).strip()
    try: return float(s.replace('亿','').replace(',',''))
    except: return 0.0

def parse_pct(s):
    if pd.isna(s): return 0.0
    s = str(s).strip().replace('%','')
    try: return float(s)
    except: return 0.0

def get_kline_sina(code_full, datalen=25):
    time.sleep(0.6)
    url = (f'https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/'
           f'CN_MarketData.getKLineData?symbol={code_full}&scale=240&ma=no&datalen={datalen}')
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://finance.sina.com.cn/'
    }
    try:
        r = requests.get(url, timeout=12, headers=headers)
        return r.json() if r.status_code == 200 else None
    except:
        return None

# ── 1. 获取全市场行情 ────────────────────────────────────────────────
sys.stdout.write("[1] 获取全市场行情...\n"); sys.stdout.flush()
from stock_tencent import get_stocks_quote

pool = []
for i in range(600000, 601010): pool.append(f'sh{i:06d}')
for i in range(688000, 688700): pool.append(f'sh{i:06d}')
for i in range(1, 901): pool.append(f'sz{i:06d}')
for i in range(300001, 301000): pool.append(f'sz{i:06d}')
for i in range(2001, 2700): pool.append(f'sz{i:06d}')

sys.stdout.write(f"    代码池 {len(pool)} 只\n"); sys.stdout.flush()

all_dfs = []
for i in range(0, len(pool), 50):
    batch = pool[i:i+50]
    try:
        df_b = get_stocks_quote(batch)
        if df_b is not None and len(df_b) > 0:
            all_dfs.append(df_b)
    except: pass
    if i % 500 == 0:
        sys.stdout.write(f"    进度 {i}/{len(pool)}\n"); sys.stdout.flush()

df_spot = pd.concat(all_dfs, ignore_index=True)
df_spot['总市值亿'] = df_spot['总市值'].apply(parse_market_cap)
df_spot['今日涨跌幅'] = df_spot['涨跌幅'].apply(parse_pct)
df_spot = df_spot[df_spot['总市值亿'] >= 100].reset_index(drop=True)
df_spot['code_str'] = df_spot['代码'].astype(str).str.zfill(6)
df_spot['prefix'] = df_spot['code_str'].apply(lambda x: 'sh' if x.startswith('6') else 'sz')
sys.stdout.write(f"    ✓ 市值≥100亿：{len(df_spot)} 只\n"); sys.stdout.flush()

# ── 2. 预筛：今日跌幅最大的前100只（控制请求量）────────────────────────
drops = df_spot[df_spot['今日涨跌幅'] <= -3].sort_values('今日涨跌幅').head(100)
sys.stdout.write(f"    今日跌幅≥3%：{len(drops)} 只，取跌幅最大的100只验证\n"); sys.stdout.flush()

# ── 3. K线验证 ──────────────────────────────────────────────────────────
sys.stdout.write("[2] K线形态验证...\n"); sys.stdout.flush()

results = []
checked = 0

for _, row in drops.iterrows():
    code_str = row['code_str']
    name = row['名称']
    prefix = row['prefix']
    code_full = f'{prefix}{code_str}'
    
    kl = get_kline_sina(code_full, datalen=25)
    checked += 1
    
    if kl is None or len(kl) < 8:
        if checked % 20 == 0:
            sys.stdout.write(f"    已检验 {checked}/{len(drops)} 只，符合 {len(results)} 只\n"); sys.stdout.flush()
        continue
    
    try:
        closes = [float(d['close']) for d in kl]
        vols   = [float(d['volume']) for d in kl]
        pct    = [(closes[i]-closes[i-1])/closes[i-1]*100 for i in range(1, len(closes))]
        
        if len(pct) < 4:
            if checked % 20 == 0:
                sys.stdout.write(f"    已检验 {checked}/{len(drops)} 只，符合 {len(results)} 只\n"); sys.stdout.flush()
            continue
        
        last3 = pct[-3:]
        cum_drop = sum(last3)
        if cum_drop > -7:
            if checked % 20 == 0:
                sys.stdout.write(f"    已检验 {checked}/{len(drops)} 只，符合 {len(results)} 只\n"); sys.stdout.flush()
            continue
        
        y_pct = pct[-2]
        y_vol = vols[-2]
        
        avg_vol5 = np.mean(vols[-6:-1]) if len(vols) >= 6 else np.mean(vols)
        is_shrink = bool(y_vol < avg_vol5 * 0.7)
        is_star   = abs(y_pct) < 0.5
        is_small  = abs(y_pct) < 2
        
        if not (is_star or (is_small and is_shrink)):
            if checked % 20 == 0:
                sys.stdout.write(f"    已检验 {checked}/{len(drops)} 只，符合 {len(results)} 只\n"); sys.stdout.flush()
            continue
        
        ma_len = min(len(closes), 20)
        ma20   = np.mean(closes[-ma_len:])
        l_price = closes[-1]
        ma20_dist = round((l_price - ma20) / ma20 * 100, 2)
        
        is_active   = bool(vols[-1] > avg_vol5 * 1.2)
        broken_ma20 = bool(l_price < ma20 * 0.97)
        drop_days   = min(int(abs(cum_drop) / 3) + 1, 3)
        
        results.append({
            '股票名称': name,
            '代码': code_str,
            '回调天数': f"{drop_days}天",
            '距20日线': f"+{ma20_dist:.1f}%" if ma20_dist >= 0 else f"{ma20_dist:.1f}%",
            '是否有效跌破': '是' if broken_ma20 else '否',
            '操作建议': '可低吸' if (is_active and not broken_ma20) else '观望',
            '_cum_drop': round(cum_drop, 2),
        })
        sys.stdout.write(f"    ✓ {name}({code_str}) 近3日跌{cum_drop:.1f}%\n"); sys.stdout.flush()
    except:
        pass
    
    if checked % 20 == 0:
        sys.stdout.write(f"    已检验 {checked}/{len(drops)} 只，符合 {len(results)} 只\n"); sys.stdout.flush()

sys.stdout.write(f"    ✓ 符合条件 {len(results)} 只\n"); sys.stdout.flush()

# ── 4. 输出 ────────────────────────────────────────────────────────────────
if not results:
    sys.stdout.write("\n❌ 今日无符合条件的反弹标的\n"); sys.stdout.flush()
else:
    df_final = pd.DataFrame(results)
    df_final = df_final.sort_values('_cum_drop', ascending=False).head(20)
    df_final = df_final.drop(columns=['_cum_drop'])
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    header = "="*72
    title  = f"📊 筛选反弹标的  |  市值≥100亿  |  近3日跌幅≥7%  |  昨缩量企稳  |  {now}"
    output = f"\n{header}\n{title}\n{header}\n{df_final.to_markdown(index=False)}\n\n共 {len(df_final)} 只标的\n"
    sys.stdout.write(output); sys.stdout.flush()