#!/usr/bin/env python3
"""
更新大盘股列表
每个工作日16:00执行，拉取A股所有股票收盘市值，筛选>100亿的覆盖写入配置文件
"""
import urllib.request
import pandas as pd
from datetime import datetime, timedelta
import time
import warnings
warnings.filterwarnings('ignore')

CONFIG_FILE = "/root/.openclaw/workspace/data/big_cap_stocks.txt"

def get_all_stock_codes():
    import akshare as ak
    df = ak.stock_info_a_code_name()
    codes = []
    for _, row in df.iterrows():
        code = row['code']
        if code.startswith('0') or code.startswith('3') or code.startswith('6'):
            prefix = 'sz' if code.startswith(('0', '3')) else 'sh'
            codes.append({'code': code, 'name': row['name'], 'full_code': f"{prefix}{code}"})
    return codes

def batch_get_market_cap(codes_full, batch_size=80):
    """批量获取市值，返回市值>100亿的股票"""
    results = []
    total = len(codes_full)
    for i in range(0, total, batch_size):
        batch = codes_full[i:i+batch_size]
        code_str = ','.join([c['full_code'] for c in batch])
        url = f'https://qt.gtimg.cn/q={code_str}'
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read().decode('gbk', errors='ignore')
            lines = data.strip().split('\n')
            for line in lines:
                if '=' not in line:
                    continue
                parts = line.split('=')[1].strip('";').split('~')
                if len(parts) < 50:
                    continue
                try:
                    mkt_cap = float(parts[44]) if parts[44] else 0
                    if mkt_cap >= 100:  # 市值>100亿
                        full_code = parts[2] if len(parts) > 2 else ''
                        name = parts[1] if len(parts) > 1 else ''
                        price = float(parts[3]) if parts[3] else 0
                        results.append({
                            'code': full_code,
                            'name': name,
                            'price': price,
                            'market_cap': mkt_cap  # 亿元
                        })
                except:
                    pass
        except:
            pass
        if (i // batch_size + 1) % 10 == 0:
            print(f"  市值进度: {min(i+batch_size, total)}/{total}")
        time.sleep(0.06)
    return pd.DataFrame(results)

def main():
    today = datetime.now().strftime('%Y-%m-%d %H:%M')
    print(f"={'='*60}")
    print(f"更新大盘股列表 {today}")
    print(f"={'='*60}")

    print("\n[1/2] 获取A股股票列表...")
    all_stocks = get_all_stock_codes()
    print(f"  共 {len(all_stocks)} 只")

    print("\n[2/2] 批量获取市值（筛选>100亿）...")
    mkt_df = batch_get_market_cap(all_stocks, batch_size=80)
    print(f"  市值>100亿: {len(mkt_df)} 只")

    if len(mkt_df) == 0:
        print("无法获取市值数据，退出")
        exit(1)

    # 按市值降序排列
    mkt_df = mkt_df.sort_values('market_cap', ascending=False).reset_index(drop=True)

    # 写入配置文件（覆盖）
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        f.write(f"# 大盘股列表 | 更新于 {today} | 市值>100亿 | 共{len(mkt_df)}只\n")
        f.write("# code,name,market_cap(亿元)\n")
        for _, row in mkt_df.iterrows():
            code = row['code'].replace('sh', '').replace('sz', '')
            f.write(f"{code},{row['name']},{row['market_cap']:.2f}\n")

    print(f"\n✅ 已写入 {CONFIG_FILE}，共 {len(mkt_df)} 只大盘股")
    top5 = mkt_df.head(5)
    print("Top5 市值:")
    for _, r in top5.iterrows():
        print(f"  {r['name']} {r['code']} {r['market_cap']:.0f}亿")

if __name__ == "__main__":
    main()