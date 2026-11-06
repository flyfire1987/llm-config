#!/usr/bin/env python3
"""
快速反弹标的筛选 - 板块引导 + 重点验证
策略：先找近5日跌幅大的板块，再从里面挑市值>100亿且昨日缩量企稳的票
"""
import sys
sys.path.insert(0, '/root/.openclaw/workspace')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import urllib.request
import json
import warnings
warnings.filterwarnings('ignore')

import akshare as ak

# ---------- 工具函数 ----------
def get_date_range(days=30):
    end = datetime.now()
    start = end - timedelta(days=days + 3)
    return start.strftime('%Y%m%d'), end.strftime('%Y%m%d')

def parse_tencent_stock_key(line: str):
    try:
        if '=' not in line or not line.strip():
            return None
        key_part = line.split('=')[0].strip()
        actual_code = key_part.replace('v_', '')
        fields = line.split('=')[1].strip('";').split('~')
        if len(fields) < 45:
            return None
        return {
            'code': actual_code,
            'name': fields[1],
            'market_cap': float(fields[44]) if fields[44] else 0,
        }
    except:
        return None

def get_stocks_batch(codes):
    if not codes:
        return pd.DataFrame()
    url = f'https://qt.gtimg.cn/q={",".join(codes)}'
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0')
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode('gbk', errors='ignore')
        rows = [parse_tencent_stock_key(l) for l in raw.strip().split('\n')]
        return pd.DataFrame([r for r in rows if r])
    except:
        return pd.DataFrame()

def fetch_kline_tx(code, days=20):
    """腾讯历史K线"""
    url = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayqfq&param={code},day,,,{days},qfq'
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0')
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode('utf-8', errors='ignore')
        raw = raw.replace('kline_dayqfq=', '', 1)
        data = json.loads(raw)
        qt = data.get('data', {}).get(code, {})
        qfq = qt.get('qfqday', qt.get('day', []))
        if not qfq or len(qfq) < 5:
            return pd.DataFrame()
        df = pd.DataFrame(qfq, columns=['date', 'open', 'close', 'high', 'low', 'amount'])
        df['date'] = pd.to_datetime(df['date'])
        df['close'] = df['close'].astype(float)
        df['open'] = df['open'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['amount'] = df['amount'].astype(float)
        df = df.sort_values('date').tail(25).reset_index(drop=True)
        return df
    except:
        return pd.DataFrame()

def check_rebound(code, name, mkt):
    """检查单只股票是否满足反弹条件"""
    df = fetch_kline_tx(code, days=25)
    if df is None or len(df) < 10:
        return None
    
    yesterday = df.iloc[-2]  # 昨日
    today = df.iloc[-1]       # 今日（可能未收盘）
    
    # 计算近5日涨跌幅
    close_5d_ago = df.iloc[-6]['close']
    y_close = yesterday['close']
    pct5 = (y_close - close_5d_ago) / close_5d_ago * 100
    
    # 近3日（去掉周末gap，用自然日）
    d3_start = df.iloc[-5]['close']
    pct3 = (y_close - d3_start) / d3_start * 100
    
    # 昨日K线
    y_chg = (yesterday['close'] - yesterday['open']) / yesterday['open'] * 100
    y_body = abs(y_chg)
    y_shadow_up = (yesterday['high'] - max(yesterday['close'], yesterday['open'])) / yesterday['open'] * 100
    y_shadow_down = (min(yesterday['close'], yesterday['open']) - yesterday['low']) / yesterday['open'] * 100
    
    # 成交量缩量
    y_vol = yesterday['amount']
    p_vol = df.iloc[-3]['amount']  # 前日量（跳过周末）
    vol_r = y_vol / p_vol if p_vol > 0 else 1
    
    # 20日线
    ma20 = df['close'].tail(20).mean()
    ma20_dist = (y_close - ma20) / ma20 * 100
    
    # 企稳信号
    is_stable = y_body < 2.5 and vol_r < 0.82
    
    # 有效跌破20日线 = 收盘<ma20 且 今天跌幅>2%
    eff_break = (y_close < ma20 and yesterday['close'] < yesterday['open'] and y_body > 2.0)
    
    if is_stable and not eff_break:
        return {
            'code': code,
            'name': name,
            'mkt': mkt,
            'y_chg': round(y_chg, 2),
            'vol_r': round(vol_r, 3),
            'pct3': round(pct3, 2),
            'pct5': round(pct5, 2),
            'ma20_dist': round(ma20_dist, 2),
        }
    return None

# ---------- 主流程 ----------
print("=" * 50)
print("🚀 快速反弹标的筛选")
print("=" * 50)

# Step 1: 获取板块近期涨跌
print("\n📊 Step1: 获取行业板块近期涨跌...")
try:
    df_board = ak.stock_sector_spot()
    print(f"✅ 获取到 {len(df_board)} 个板块")
except Exception as e:
    print(f"❌ 板块数据失败: {e}")
    sys.exit(1)

# 计算板块近5日涨跌（使用均价数据）
# 保留涨跌幅最大的10个板块（跌幅最大的）
sectors_down = []
today_str = datetime.now().strftime('%Y-%m-%d')

# 获取主力监控数据
try:
    df_money = ak.stock_market_most_lost()
    if not df_money.empty:
        # 找近期跌幅大的
        df_money.columns = [c.strip() for c in df_money.columns]
        # 按名称找板块
        print(f"📈 主力资金监控获取成功，{len(df_money)} 条")
        print(df_money.head(5))
except:
    pass

# Step 2: 获取大盘股（市值>100亿）
print("\n📊 Step2: 筛选大盘股...")
try:
    df_codes = ak.stock_info_a_code_name()
    print(f"✅ 共 {len(df_codes)} 只A股")
except Exception as e:
    print(f"❌ 失败: {e}")
    sys.exit(1)

all_codes = []
for _, row in df_codes.iterrows():
    code = str(row['code']).zfill(6)
    if code.startswith(('6', '000', '001', '002', '003', '8', '4')):
        prefix = 'sh' if code.startswith('6') or code.startswith('8') else 'sz'
        all_codes.append(f'{prefix}{code}')

print(f"📡 正在获取实时行情 ({len(all_codes)} 只)...")
all_stocks = []
for i in range(0, len(all_codes), 100):
    batch = all_codes[i:i+100]
    df_batch = get_stocks_batch(batch)
    if not df_batch.empty:
        all_stocks.append(df_batch)
    if i % 500 == 0:
        print(f"  进度: {i}/{len(all_codes)}")

if all_stocks:
    df_spot = pd.concat(all_stocks, ignore_index=True)
    df_large = df_spot[df_spot['market_cap'] > 100].copy()
    print(f"✅ 市值>100亿股票: {len(df_large)} 只")
else:
    print("❌ 行情获取失败")
    sys.exit(1)

# Step 3: 重点扫描（从跌幅大板块中的大盘股）
# 先用腾讯实时涨跌排序，找跌幅大的大盘股
print("\n📊 Step3: 快速定位近期跌得多的大盘股...")

# 获取所有大盘股的今日实时数据中的涨跌幅
# 使用腾讯实时数据接口 - 已经获取了market_cap，重新批量获取涨跌幅
print("📡 正在获取今日涨跌幅...")
large_codes = df_large['code'].tolist()
large_mkt = dict(zip(df_large['code'], df_large['market_cap']))

# 批量获取今日数据（含涨跌幅）
all_live = []
for i in range(0, len(large_codes), 100):
    batch = large_codes[i:i+100]
    df_batch = get_stocks_batch(batch)
    if not df_batch.empty:
        all_live.append(df_batch)
    if i % 500 == 0:
        print(f"  进度: {i}/{len(large_codes)}")

if all_live:
    df_live = pd.concat(all_live, ignore_index=True)
else:
    df_live = pd.DataFrame()

print(f"✅ 实时数据获取: {len(df_live)} 只")

# 按涨跌幅排序，找跌幅大的
if 'pct_chg' in df_live.columns:
    df_live['pct_chg'] = pd.to_numeric(df_live['pct_chg'], errors='coerce')
    df_big_drop = df_live[df_live['pct_chg'] < -3].sort_values('pct_chg').head(50)
    print(f"\n🔴 今日跌幅>3%的大盘股: {len(df_big_drop)} 只")
    print(df_big_drop[['code', 'name', 'pct_chg', 'market_cap']].to_string())

# Step 4: 精筛昨日缩量企稳
print("\n📊 Step4: 精筛昨日缩量企稳（候选池）...")
# 取候选：今日跌幅大 或 近期明显下跌的大盘股
top_drop = df_large.head(60)  # 默认候选
if len(df_live) > 0 and 'pct_chg' in df_live.columns:
    df_live['pct_chg'] = pd.to_numeric(df_live['pct_chg'], errors='coerce')
    top_drop = pd.concat([
        df_live.nlargest(30, 'pct_chg', keep='all'),
        df_live.nsmallest(30, 'pct_chg', keep='all')
    ]).drop_duplicates()

print(f"📋 候选池: {len(top_drop)} 只，开始逐个验证K线...")

results = []
count = 0
for _, row in top_drop.iterrows():
    code = row['code']
    name = row.get('name', '')
    mkt = row.get('market_cap', 0)
    r = check_rebound(code, name, mkt)
    count += 1
    if count % 10 == 0:
        print(f"  已验证 {count}/{len(top_drop)}，找到 {len(results)} 只")
    if r:
        results.append(r)
        print(f"  ✅ {code} {name}: 昨收{r['y_chg']}%，量比{r['vol_r']}，3日跌{r['pct3']}%")

print(f"\n{'='*50}")
print(f"🎯 共找到 {len(results)} 只符合条件")
print(f"{'='*50}")

if results:
    df_result = pd.DataFrame(results)
    df_result = df_result.sort_values('pct3')
    print(df_result.to_string(index=False))
    
    # 保存
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    fname = f'/root/.openclaw/workspace/rebound_result_{ts}.csv'
    df_result.to_csv(fname, index=False, encoding='utf-8')
    print(f"\n💾 结果已保存: {fname}")
else:
    print("⚠️ 未找到符合条件的标的")
    print("\n建议：当前市场无明显急跌反弹机会，可考虑：")
    print("1. 关注今日盘中跌幅>3%的大盘股（可能随大盘反弹）")
    print("2. 等待明日数据确认缩量企稳形态")
