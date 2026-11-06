#!/usr/bin/env python3
"""
A股历史数据本地数据库
- 存储所有A股日K线数据
- 保持30天滚动数据
- SQLite存储
"""

import akshare as ak
import pandas as pd
import sqlite3
import os
from datetime import datetime, timedelta
import time
import requests

# 配置
DB_PATH = "/root/.openclaw/workspace/data/stock_history.db"
KEEP_DAYS = 30
RETRY_DELAY = 0.2  # 重试延迟

# ============ 1. 初始化数据库 ============
def init_db():
    """初始化数据库表"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 股票日K线表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            amount REAL,
            change_pct REAL,
            turnover REAL,
            amplitude REAL,
            updated_at TEXT,
            UNIQUE(stock_code, trade_date)
        )
    """)
    
    # 股票基本信息表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_info (
            code TEXT PRIMARY KEY,
            name TEXT,
            industry TEXT,
            list_date TEXT,
            market TEXT,
            updated_at TEXT
        )
    """)
    
    # 创建索引
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_code_date ON stock_daily(stock_code, trade_date)")
    
    conn.commit()
    conn.close()
    print(f"✅ 数据库初始化完成: {DB_PATH}")

# ============ 2. 获取股票列表 ============
def get_stock_list():
    """获取A股所有股票列表"""
    try:
        df = ak.stock_info_a_code_name()
        print(f"获取到 {len(df)} 只股票")
        return df
    except Exception as e:
        print(f"获取股票列表失败: {e}")
        return None

# ============ 3. 获取单只股票历史数据 ============
def get_stock_history(stock_code, days=30, max_retries=5):
    """获取单只股票历史数据，带重试机制"""
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=days+30)).strftime("%Y%m%d")
    
    for attempt in range(max_retries):
        try:
            # 根据代码判断市场
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
            else:
                pass
    
    return None

# ============ 4. 保存数据 ============
def save_stock_data(df, conn):
    """保存股票数据到数据库"""
    if df is None or len(df) == 0:
        return 0
    
    df['updated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 使用INSERT OR REPLACE
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

# ============ 5. 清理过期数据 ============
def cleanup_old_data(conn):
    """清理30天前的数据"""
    cutoff_date = (datetime.now() - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM stock_daily WHERE trade_date < ?", (cutoff_date,))
    deleted = cursor.rowcount
    conn.commit()
    return deleted

# ============ 6. 保存股票基本信息 ============
def save_stock_info(stock_list, conn):
    """保存股票基本信息"""
    if stock_list is None:
        return
    
    df = stock_list.copy()
    df['updated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df.to_sql('stock_info', conn, if_exists='replace', index=False)
    print(f"✅ 保存了 {len(df)} 只股票基本信息")

# ============ 7. 主程序 ============
def main():
    print("=" * 50)
    print("A股历史数据同步开始")
    print("=" * 50)
    
    # 初始化数据库
    init_db()
    conn = sqlite3.connect(DB_PATH)
    
    # 获取股票列表
    print("\n📋 获取股票列表...")
    stock_list = get_stock_list()
    
    if stock_list is not None:
        # 保存基本信息
        save_stock_info(stock_list, conn)
        
        # 获取所有股票代码
        codes = stock_list['code'].tolist()  # 全部股票
        
        print(f"\n📥 开始同步 {len(codes)} 只股票数据...")
        
        success = 0
        failed = 0
        
        for i, code in enumerate(codes):
            try:
                df = get_stock_history(code, KEEP_DAYS)
                if df is not None:
                    save_stock_data(df, conn)
                    success += 1
                else:
                    failed += 1
                    
                if (i + 1) % 50 == 0:
                    print(f"进度: {i+1}/{len(codes)}, 成功: {success}, 失败: {failed}")
                    
                time.sleep(RETRY_DELAY)  # 避免请求过快
                
            except Exception as e:
                failed += 1
                if (i + 1) % 50 == 0:
                    print(f"❌ {code}: {str(e)[:50]}")
        
        print(f"\n📊 同步完成: 成功 {success}, 失败 {failed}")
    
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
    
    print(f"\n📈 数据库统计:")
    print(f"   总记录数: {total:,}")
    print(f"   股票数量: {stocks}")
    
    conn.close()
    print(f"\n✅ 完成! 数据库位置: {DB_PATH}")

if __name__ == "__main__":
    main()
