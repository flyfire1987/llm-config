#!/usr/bin/env python3
"""
A股历史数据本地数据库 - 增量同步版本
只同步失败的股票，快速更新
"""

import akshare as ak
import sqlite3
import os
from datetime import datetime, timedelta
import time

# 配置
DB_PATH = "/root/.openclaw/workspace/data/stock_history.db"
KEEP_DAYS = 30
RETRY_DELAY = 0.2

# ============ 1. 获取失败的股票列表 ============
def get_failed_stocks():
    """获取失败的股票列表（未同步或数据较少的）"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 获取已同步的股票
    cursor.execute("SELECT DISTINCT stock_code FROM stock_daily")
    synced = set(row[0] for row in cursor.fetchall())
    
    # 获取总股票列表
    cursor.execute("SELECT code FROM stock_info")
    all_codes = [row[0] for row in cursor.fetchall()]
    
    conn.close()
    
    # 找出未同步的
    failed = [code for code in all_codes if code not in synced]
    return failed

# ============ 2. 获取单只股票历史数据 ============
def get_stock_history(stock_code, days=30, max_retries=2):
    """获取单只股票历史数据"""
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=days+30)).strftime("%Y%m%d")
    
    for attempt in range(max_retries):
        try:
            if stock_code.startswith("6"):
                symbol = stock_code
            elif stock_code.startswith(("0", "3")):
                symbol = stock_code
            elif stock_code.startswith("8") or stock_code.startswith("4"):
                symbol = stock_code
            else:
                return None
                
            df = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="qfq"
            )
            
            if df is not None and len(df) > 0:
                df = df.rename(columns={
                    '日期': 'trade_date',
                    '股票代码': 'stock_code',
                    '开盘': 'open',
                    '收盘': 'close',
                    '最高': 'high',
                    '最低': 'low',
                    '成交量': 'volume',
                    '成交额': 'amount',
                    '涨跌幅': 'change_pct',
                    '换手率': 'turnover',
                    '振幅': 'amplitude'
                })
                df['stock_code'] = stock_code
                df = df[['stock_code', 'trade_date', 'open', 'high', 'low', 'close', 
                         'volume', 'amount', 'change_pct', 'turnover', 'amplitude']]
                return df
                
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(RETRY_DELAY)
                continue
    
    return None

# ============ 3. 保存数据 ============
def save_stock_data(df, conn):
    """保存股票数据到数据库"""
    if df is None or len(df) == 0:
        return 0
    
    df['updated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df.to_sql('stock_daily', conn, if_exists='append', index=False)
    
    # 去重
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM stock_daily 
        WHERE id NOT IN (
            SELECT MAX(id) FROM stock_daily 
            GROUP BY stock_code, trade_date
        )
    """)
    conn.commit()
    
    return len(df)

# ============ 4. 清理过期数据 ============
def cleanup_old_data(conn):
    """清理30天前的数据"""
    cutoff_date = (datetime.now() - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM stock_daily WHERE trade_date < ?", (cutoff_date,))
    deleted = cursor.rowcount
    conn.commit()
    return deleted

# ============ 主程序 ============
def main():
    print("=" * 50)
    print("A股历史数据 - 增量同步")
    print("=" * 50)
    
    if not os.path.exists(DB_PATH):
        print("❌ 数据库不存在，请先运行完整同步")
        return
    
    conn = sqlite3.connect(DB_PATH)
    
    # 获取失败的股票
    print("\n📋 查找未同步的股票...")
    failed_codes = get_failed_stocks()
    print(f"未同步: {len(failed_codes)} 只")
    
    if not failed_codes:
        print("✅ 所有股票已同步完成！")
        conn.close()
        return
    
    # 同步失败的股票（限制100只，防止超时）
    codes_to_sync = failed_codes[:100]
    print(f"\n📥 开始增量同步 {len(codes_to_sync)} 只股票...")
    
    success = 0
    failed = 0
    
    for i, code in enumerate(codes_to_sync):
        try:
            df = get_stock_history(code, KEEP_DAYS)
            if df is not None:
                save_stock_data(df, conn)
                success += 1
            else:
                failed += 1
                
            if (i + 1) % 20 == 0:
                print(f"进度: {i+1}/{len(codes_to_sync)}, 成功: {success}, 失败: {failed}")
                
            time.sleep(RETRY_DELAY)
            
        except Exception as e:
            failed += 1
    
    print(f"\n📊 增量同步完成: 成功 {success}, 失败 {failed}")
    
    # 清理过期数据
    print("\n🧹 清理过期数据...")
    deleted = cleanup_old_data(conn)
    print(f"删除 {deleted} 条过期数据")
    
    # 统计
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM stock_daily")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(DISTINCT stock_code) FROM stock_daily")
    stocks = cursor.fetchone()[0]
    
    print(f"\n📈 当前数据库统计:")
    print(f"   总记录数: {total:,}")
    print(f"   股票数量: {stocks}")
    
    conn.close()
    print(f"\n✅ 完成!")

if __name__ == "__main__":
    main()
