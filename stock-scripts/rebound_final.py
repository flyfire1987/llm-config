#!/usr/bin/env python3
"""
反弹标的筛选脚本 - 腾讯接口版（修复版）
条件：
1. 市值 > 100亿
2. 昨日缩量企稳（|涨跌幅|<2.5% + 成交量<前日80%）
3. 未有效跌破20日线
"""

import sys
sys.path.insert(0, '/root/.openclaw/workspace')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import urllib.request
import warnings
warnings.filterwarnings('ignore')

import akshare as ak
from typing import List, Optional

# ---------- 腾讯实时行情：提取原始代码标识 ----------
def parse_tencent_stock_key(line: str) -> Optional[dict]:
    """从腾讯API原始行解析，key中含sh/sz前缀"""
    try:
        if '=' not in line or not line.strip():
            return None
        key_part = line.split('=')[0].strip()   # e.g. v_sh601318 或 sh601318
        actual_code = key_part.replace('v_', '')  # 去掉v_前缀
        
        fields = line.split('=')[1].strip('";').split('~')
        if len(fields) < 45:
            return None
        
        return {
            'code': actual_code,   # 保留原始 sh/sz 前缀
            'name': fields[1],
            'market_cap': float(fields[44]) if fields[44] else 0,
            'float_market_cap': float(fields[45]) if fields[45] else 0,
        }
    except:
        return None

def get_stocks_batch(codes: List[str]) -> pd.DataFrame:
    if not codes:
        return pd.DataFrame()
    url = f'https://qt.gtimg.cn/q={",".join(codes)}'
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode('gbk', errors='ignore')
        rows = []
        for line in raw.strip().split('\n'):
            rec = parse_tencent_stock_key(line)
            if rec:
                rows.append(rec)
        return pd.DataFrame(rows)
    except:
        return pd.DataFrame()

def get_date_range(days=30):
    end = datetime.now()
    start = end - timedelta(days=days + 3)
    return start.strftime('%Y%m%d'), end.strftime('%Y%m%d')

# ---------- 主流程 ----------
print("📡 正在获取A股股票列表...")
try:
    df_codes = ak.stock_info_a_code_name()
    print(f"✅ 共 {len(df_codes)} 只A股")
except Exception as e:
    print(f"❌ 获取失败: {e}")
    sys.exit(1)

# 构建带市场前缀代码
all_codes = []
for _, row in df_codes.iterrows():
    code = str(row['code']).zfill(6)
    if code.startswith('6'):
        all_codes.append(f'sh{code}')
    elif code.startswith('00') or code.startswith('30'):
        all_codes.append(f'sz{code}')
    elif code.startswith('8') or code.startswith('4'):
        all_codes.append(f'bj{code}')

print(f"📊 待扫描: {len(all_codes)} 只")

# ---------- 批量获取市值，筛选>100亿 ----------
print("📡 正在批量获取实时行情...")
all_stocks = []
for i in range(0, len(all_codes), 100):
    batch = all_codes[i:i+100]
    df_batch = get_stocks_batch(batch)
    if not df_batch.empty:
        all_stocks.append(df_batch)
    if i % 1000 == 0:
        print(f"  进度: {i}/{len(all_codes)}")

if not all_stocks:
    print("❌ 行情获取失败")
    sys.exit(1)

df_spot = pd.concat(all_stocks, ignore_index=True)
df_large = df_spot[df_spot['market_cap'] > 100].copy()
print(f"✅ 市值>100亿股票共 {len(df_large)} 只")

if df_large.empty:
    print("❌ 无符合市值条件股票")
    sys.exit(1)

# ---------- K线分析 ----------
print("📊 正在分析K线形态...")

start_date, end_date = get_date_range(30)
results = []
skipped = 0
found = 0

total = len(df_large)

for idx, (_, row) in enumerate(df_large.iterrows()):
    code = row['code']       # 带sh/sz前缀
    name = row['name']
    mkt = row['market_cap']
    
    if not (code.startswith('sh') or code.startswith('sz')):
        skipped += 1
        continue
    
    if (idx + 1) % 400 == 0:
        print(f"  分析进度: {idx+1}/{total}，已找到 {found} 只")
    
    try:
        df_k = ak.stock_zh_a_hist_tx(
            symbol=code,
            start_date=start_date,
            end_date=end_date,
            adjust='qfq'
        )
        
        if df_k is None or len(df_k) < 4:
            skipped += 1
            continue
        
        df_k['pct_chg'] = df_k['close'].pct_change() * 100
        df_s = df_k.tail(5).reset_index(drop=True)
        
        yesterday = df_s.iloc[-2]
        prev_day = df_s.iloc[-3]
        
        y_chg = yesterday['pct_chg']
        y_vol = yesterday.get('amount', 0)
        p_vol = prev_day.get('amount', 0)
        
        # 条件1: 昨日小阴小阳
        if abs(y_chg) > 2.5:
            skipped += 1
            continue
        
        # 计算MA20
        closes = df_k['close'].tolist()
        if len(closes) >= 20:
            ma20 = np.mean(closes[-20:])
        else:
            ma20 = np.mean(closes)
        latest_close = closes[-1]
        ma20_dist = (latest_close - ma20) / ma20 * 100
        
        eff_break = "是" if latest_close < ma20 * 0.95 else "否"
        
        # 近5日累计
        pct5 = df_s['pct_chg'].tail(5).sum() if len(df_s) >= 5 else 0
        
        vol_r = y_vol / p_vol if p_vol > 0 else 1
        advice = "可低吸" if eff_break == "否" and abs(y_chg) < 1.5 else "观望"
        
        # 纯数字代码
        raw_code = code.replace('sh','').replace('sz','').replace('bj','')
        
        results.append({
            '名称': name,
            '代码': raw_code,
            '回调天数': '3-5天',
            '距20日线': f"{ma20_dist:+.1f}%",
            '有效跌破20日线': eff_break,
            '热门板块': '—',
            '操作建议': advice,
            '近5日跌幅': f"{pct5:+.1f}%",
            '昨收涨跌幅': f"{y_chg:+.2f}%",
            '缩量比': f"{vol_r:.2f}",
            '成交额亿': mkt,  # 用市值排序（足够近似）
        })
        found += 1
        
    except Exception as e:
        skipped += 1
        continue

print(f"\n📈 符合条件股票: {found} 只 (跳过 {skipped} 只)")

if not results:
    print("❌ 未筛选到符合条件的股票")
    sys.exit(0)

# 排序取前20
df_result = pd.DataFrame(results)
df_result = df_result.sort_values('成交额亿', ascending=False).head(20)

# ---------- 输出 ----------
print("\n" + "="*75)
print("🔍 反弹标的筛选结果 (市值>100亿，昨缩量小K线企稳，未有效跌破20日线)")
print("="*75)

header = "| 股票名称 | 代码 | 回调天数 | 距20日线 | 是否有效跌破 | 热门板块 | 操作建议 |"
sep = "|:--------:|:----:|:--------:|:--------:|:------------:|:--------:|:--------:|"
print(header)
print(sep)

for _, row in df_result.iterrows():
    print(f"| {row['名称']} | {row['代码']} | {row['回调天数']} | {row['距20日线']} | {row['有效跌破20日线']} | {row['热门板块']} | {row['操作建议']} |")

print(f"\n共筛选出 {len(df_result)} 只标的")
print("⚠️ 仅供参考，不构成投资建议")