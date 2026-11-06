#!/usr/bin/env python3
"""
板块粒度分析脚本
功能：采集行业板块资金流 + 涨跌幅，计算RSR排序，输出板块走势分析
"""

import pandas as pd
import akshare as ak
import sys
import os
from datetime import datetime, timedelta

# 输出编码
sys.stdout.reconfigure(encoding='utf-8')

def get_sector_data(indicator='今日'):
    """获取板块资金流排名"""
    try:
        df = ak.stock_sector_fund_flow_rank(indicator=indicator, sector_type='行业资金流')
        return df
    except Exception as e:
        print(f"[ERROR] 获取{indicator}数据失败: {e}")
        return None

def get_market_index():
    """获取大盘指数（沪深300）作为基准"""
    try:
        df = ak.stock_zh_index_spot_em(symbol="沪深重要指数")
        # 找沪深300
        hs300 = df[df['代码'] == '000300']
        if len(hs300) > 0:
            pct_str = str(hs300.iloc[0]['涨跌幅']).replace('%', '')
            return float(hs300.iloc[0]['最新价']), float(pct_str)
        # 备用：上证指数
        sh = df[df['代码'] == '000001']
        if len(sh) > 0:
            pct_str = str(sh.iloc[0]['涨跌幅']).replace('%', '')
            return float(sh.iloc[0]['最新价']), float(pct_str)
        return None, None
    except Exception as e:
        print(f"[WARN] 获取大盘指数失败: {e}")
        return None, None

def calc_rsr(df, benchmark_pct):
    """计算RSR（相对强度）= 板块涨幅 / 大盘涨幅"""
    if benchmark_pct == 0:
        return df
    df['RSR'] = df['今日涨跌幅'] / benchmark_pct
    return df

def analyze_sectors():
    """主分析流程"""
    result_lines = []
    result_lines.append("📊 **板块粒度分析日报**")
    result_lines.append(f"📅 分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    result_lines.append("")
    
    # 1. 获取大盘基准
    _, benchmark_pct = get_market_index()
    if benchmark_pct is None:
        benchmark_pct = 0  # 避免除零
    
    # 2. 获取今日、5日、10日数据
    df_today = get_sector_data('今日')
    df_5d = get_sector_data('5日')
    df_10d = get_sector_data('10日')
    
    if df_today is None or df_5d is None or df_10d is None:
        result_lines.append("❌ 数据获取失败，请检查网络")
        return "\n".join(result_lines)
    
    # 3. 计算RSR并排序
    df_today = calc_rsr(df_today.copy(), benchmark_pct)
    df_today = df_today.sort_values('今日涨跌幅', ascending=False)
    
    # 4. 计算5日、10日累计净流入（单位：亿）
    # 注意：不同时间段的列名前缀不同
    col_5d_net = '5日主力净流入-净额'
    col_10d_net = '10日主力净流入-净额'
    df_5d['5日净流入_亿'] = df_5d[col_5d_net] / 1e8
    df_10d['10日净流入_亿'] = df_10d[col_10d_net] / 1e8
    
    # 5. 合并数据
    df_merged = df_today[['序号', '名称', '今日涨跌幅', '今日主力净流入-净额', 
                          '今日主力净流入-净占比', 'RSR']].copy()
    df_merged['今日主力净流入_亿'] = df_merged['今日主力净流入-净额'] / 1e8
    
    # 与5日/10日数据合并
    df_5d_sub = df_5d[['名称', '5日净流入_亿']].rename(columns={'名称': '名称'})
    df_10d_sub = df_10d[['名称', '10日净流入_亿']].rename(columns={'名称': '名称'})
    
    df_merged = df_merged.merge(df_5d_sub, on='名称', how='left')
    df_merged = df_merged.merge(df_10d_sub, on='名称', how='left')
    
    # 填充NaN
    df_merged = df_merged.fillna(0)
    
    # 6. 分类信号
    
    # 🔴 强势板块：今日涨幅 > 2% + 5日净流入 > 0
    strong = df_merged[(df_merged['今日涨跌幅'] > 2) & (df_merged['5日净流入_亿'] > 0)]
    strong = strong.sort_values('今日涨跌幅', ascending=False).head(5)
    
    # 🟢 资金埋伏板块：5日+10日均净流入 > 0
    accumulating = df_merged[(df_merged['5日净流入_亿'] > 0) & (df_merged['10日净流入_亿'] > 0)]
    accumulating = accumulating.sort_values('10日净流入_亿', ascending=False).head(5)
    
    # 🔵 弱势板块：今日跌幅 > 2%
    weak = df_merged[df_merged['今日涨跌幅'] < -2].sort_values('今日涨跌幅').head(5)
    
    # 7. 格式输出
    result_lines.append(f"📌 大盘今日涨跌: {'+' if benchmark_pct >= 0 else ''}{benchmark_pct}%")
    result_lines.append("")
    
    # 强势板块
    result_lines.append("**🔥 强势板块（涨幅>2% + 5日资金流入）**")
    if len(strong) > 0:
        for _, row in strong.iterrows():
            net_inflow = row['今日主力净流入_亿']
            sign = '+' if net_inflow >= 0 else ''
            result_lines.append(
                f"  • {row['名称']}: 今日+{row['今日涨跌幅']:.2f}% | "
                f"今日主力净流入{sign}{net_inflow:.1f}亿 | RSR={row['RSR']:.2f}"
            )
    else:
        result_lines.append("  暂无")
    result_lines.append("")
    
    # 资金埋伏板块
    result_lines.append("**💰 资金埋伏板块（5日+10日均净流入）**")
    if len(accumulating) > 0:
        for _, row in accumulating.iterrows():
            result_lines.append(
                f"  • {row['名称']}: 今日+{row['今日涨跌幅']:.2f}% | "
                f"5日净流入{row['5日净流入_亿']:.1f}亿 | 10日净流入{row['10日净流入_亿']:.1f}亿"
            )
    else:
        result_lines.append("  暂无")
    result_lines.append("")
    
    # 弱势板块
    result_lines.append("**📉 弱势板块（跌幅>2%，谨慎）**")
    if len(weak) > 0:
        for _, row in weak.iterrows():
            net_inflow = row['今日主力净流入_亿']
            sign = '+' if net_inflow >= 0 else ''
            result_lines.append(
                f"  • {row['名称']}: 今日{row['今日涨跌幅']:.2f}% | "
                f"主力净流入{sign}{net_inflow:.1f}亿"
            )
    else:
        result_lines.append("  暂无")
    result_lines.append("")
    
    # 8. 全市场板块RSR TOP10
    result_lines.append("**📈 板块RSR排行（相对大盘强度）**")
    df_today_sorted = df_today.sort_values('RSR', ascending=False).head(10)
    for _, row in df_today_sorted.iterrows():
        result_lines.append(
            f"  {row['名称']}: 涨幅{row['今日涨跌幅']:+.2f}% | RSR={row['RSR']:.2f}"
        )
    
    result_lines.append("")
    result_lines.append("---")
    result_lines.append("📋 **数据来源**: 东方财富（akshare）")
    result_lines.append("⚠️ 仅供参考，不构成投资建议")
    
    return "\n".join(result_lines)

if __name__ == "__main__":
    result = analyze_sectors()
    print(result)
