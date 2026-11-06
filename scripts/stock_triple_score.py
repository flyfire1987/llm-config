#!/usr/bin/env python3
"""
stock_triple_score.py - 个股三向评分（追高+反弹+震荡）
================================================================

【三向分数】
1. 追高分数（Chase）: 动能+量能+资金+龙头
2. 反弹分数（Rebound）: 超跌+超卖+止跌+估值
3. 震荡分数（Range）: 区间+量能+支撑压力

【数据源】
- 实时行情: stock_tencent.get_stocks_quote
- K线: data_source.get_kline
- 资金流: morning_news_report.get_main_fund_flow / 重试东方财富
- 板块/新闻: morning_news_report
- 财务: 暂用东方财富F10（akshare 备选）

【输出】
- 终端打印 Markdown 报告
- 支持单只/多只分析
"""

import sys
import os
import json
import time
import warnings
from datetime import datetime
from typing import List, Dict, Optional, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

sys.path.insert(0, '/root/.openclaw/workspace')
sys.path.insert(0, '/root/.openclaw/workspace/scripts')

from stock_tencent import get_stocks_quote, get_stock_by_name
import data_source
import morning_news_report as morning
from morning_news_report import NEWS_TO_STOCKS


# ==========================================
# 1. 数据获取层
# ==========================================

def get_quote_safe(code: str) -> Optional[Dict]:
    """获取实时行情（带重试）"""
    for _ in range(3):
        try:
            df = get_stocks_quote([code])
            if df is not None and len(df) > 0:
                row = df.iloc[0]
                pct_str = str(row['涨跌幅']).replace('%', '')
                turnover_str = str(row['换手率']).replace('%', '')
                amount_str = str(row['成交额'])
                return {
                    'code': code,
                    'name': row['名称'],
                    'price': float(row['当前价']),
                    'change': float(row['涨跌']),
                    'pct': float(pct_str),
                    'open': float(row['今开']),
                    'high': float(row['最高']),
                    'low': float(row['最低']),
                    'prev_close': float(row['昨收']),
                    'turnover_pct': float(turnover_str),
                    'amount_yi': float(amount_str.replace('亿', '').replace(',', '')) if '亿' in amount_str else 0,
                }
        except Exception as e:
            time.sleep(0.5)
    return None


def get_kline_safe(code: str, count: int = 60) -> Optional[pd.DataFrame]:
    """获取K线（带重试）"""
    raw_code = code.replace('sh', '').replace('sz', '')
    for _ in range(3):
        try:
            df = data_source.get_kline(raw_code, count=count)
            if df is not None and len(df) > 0:
                return df
        except Exception as e:
            time.sleep(0.5)
    return None


def get_fund_flow_safe(code: str) -> Optional[Dict]:
    """获取资金流（主力净流入 + 大单占比）
    多源重试：早报脚本 → 东方财富push2 → 腾讯
    """
    raw_code = code.replace('sh', '').replace('sz', '')
    result = {}

    # 方法1: morning_news_report 的 get_main_fund_flow（重试3次）
    for retry in range(3):
        try:
            main_flow = morning.get_main_fund_flow(raw_code)
            if main_flow is not None and main_flow != 0:
                result['main_inflow_yi'] = main_flow / 1e8
                break
        except Exception:
            time.sleep(0.5)

    # 方法2: 东方财富 detail 接口（重试3次）
    for retry in range(3):
        try:
            import requests
            secid = f"1.{raw_code}" if raw_code.startswith(('6', '5')) else f"0.{raw_code}"
            url = 'https://push2.eastmoney.com/api/qt/stock/get'
            params = {
                'secid': secid,
                'fields': 'f57,f58,f60,f62,f71,f84,f85,f86,f168,f169,f170',
                '_': int(time.time() * 1000),
            }
            r = requests.get(url, params=params, headers={
                'User-Agent': 'Mozilla/5.0',
                'Referer': 'https://quote.eastmoney.com/',
            }, timeout=5)
            if r.status_code == 200:
                j = r.json()
                d = j.get('data', {})
                if d:
                    super_big = d.get('f84', 0) or 0
                    big = d.get('f85', 0) or 0
                    total_main = (super_big + big) / 1e8
                    amount = (d.get('f60', 0) or 0) / 1e8
                    if amount > 0:
                        big_ratio = abs(total_main) / amount * 100
                    else:
                        big_ratio = 0
                    result['main_inflow_yi'] = result.get('main_inflow_yi', total_main)
                    result['big_ratio_pct'] = big_ratio
                    result['amount_yi'] = amount
                    break
        except Exception:
            time.sleep(0.5)
    return result if result else None


def get_related_news(code: str, name: str = None) -> List[Dict]:
    """获取关联新闻（来自早报抓到的数据）"""
    related = []
    try:
        # 抓一次新闻
        all_news = morning.fetch_all_news()
        ranked = morning.rank_news(all_news)
        raw_code = code.replace('sh', '').replace('sz', '')
        for n in ranked:
            # 代码匹配
            for stock_name, c in n.get('stocks', []):
                if c == raw_code:
                    related.append(n)
                    break
            else:
                # 名称匹配
                if name and name in n.get('title', ''):
                    related.append(n)
        return related
    except Exception:
        return []


def get_industry(code: str) -> Optional[Dict]:
    """获取个股所属行业及板块涨跌"""
    raw_code = code.replace('sh', '').replace('sz', '')
    # 方法1: akshare
    try:
        import akshare as ak
        info = ak.stock_individual_info_em(symbol=raw_code)
        if info is not None and len(info) > 0:
            info_dict = dict(zip(info['item'], info['value']))
            industry = info_dict.get('行业', '')
            if industry:
                return {'industry': industry, 'info': info_dict}
    except Exception:
        pass
    # 方法2: 静态映射表（主流股票 + 持仓股）
    industry_map = {
        '300751': '光伏设备',
        '002594': '新能源汽车',
        '600519': '白酒',
        '000858': '白酒',
        '601318': '保险',
        '002025': '航天航空',
        '601611': '建筑装饰',
        '300024': '机器人',
        '688017': '机器人',
        '600988': '贵金属',
        '001337': '贵金属',
        '002716': '贵金属',
        '300139': '贵金属',
        '002929': '通信服务',
        '300166': '大数据/IT服务',
    }
    if raw_code in industry_map:
        return {'industry': industry_map[raw_code], 'info': {}}
    return {'industry': '未知', 'info': {}}


# ==========================================
# 2. 技术指标计算层
# ==========================================

def calc_rsi(close: pd.Series, period: int = 14) -> float:
    """RSI 指标"""
    if len(close) < period + 1:
        return 50.0
    diff = close.diff()
    gain = diff.where(diff > 0, 0)
    loss = -diff.where(diff < 0, 0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])


def calc_kdj(df: pd.DataFrame, n: int = 9) -> Tuple[float, float, float]:
    """KDJ 指标"""
    if len(df) < n:
        return 50.0, 50.0, 50.0
    low_n = df['low'].rolling(n).min()
    high_n = df['high'].rolling(n).max()
    rsv = (df['close'] - low_n) / (high_n - low_n).replace(0, 1e-10) * 100
    k = rsv.ewm(alpha=1/3, adjust=False).mean()
    d = k.ewm(alpha=1/3, adjust=False).mean()
    j = 3 * k - 2 * d
    return float(k.iloc[-1]), float(d.iloc[-1]), float(j.iloc[-1])


def calc_macd(close: pd.Series) -> Tuple[float, float, float]:
    """MACD 指标 (DIF, DEA, MACD柱)"""
    if len(close) < 26:
        return 0.0, 0.0, 0.0
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    macd_bar = (dif - dea) * 2
    return float(dif.iloc[-1]), float(dea.iloc[-1]), float(macd_bar.iloc[-1])


def calc_boll(close: pd.Series, period: int = 20) -> Tuple[float, float, float]:
    """布林带 (中轨, 上轨, 下轨)"""
    if len(close) < period:
        price = float(close.iloc[-1])
        return price, price, price
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = mid + 2 * std
    lower = mid - 2 * std
    return float(mid.iloc[-1]), float(upper.iloc[-1]), float(lower.iloc[-1])


# ==========================================
# 3. 评分层
# ==========================================

def score_chase(quote: Dict, kline: pd.DataFrame, fund: Optional[Dict], industry: str, news: List) -> Dict:
    """追高分数（0-100）"""
    scores = {}

    # 3.1 趋势强度 (30)
    pct_today = quote['pct']
    if len(kline) >= 5:
        pct_5d = (kline['close'].iloc[-1] / kline['close'].iloc[-5] - 1) * 100
    else:
        pct_5d = 0
    if len(kline) >= 20:
        pct_20d = (kline['close'].iloc[-1] / kline['close'].iloc[-20] - 1) * 100
    else:
        pct_20d = 0

    trend_score = 0
    if pct_today >= 9.5: trend_score += 15
    elif pct_today >= 5: trend_score += 10
    elif pct_today >= 2: trend_score += 5
    if pct_5d >= 15: trend_score += 10
    elif pct_5d >= 8: trend_score += 7
    elif pct_5d >= 3: trend_score += 4
    if pct_20d >= 30: trend_score += 5
    elif pct_20d >= 15: trend_score += 3
    scores['趋势强度'] = min(trend_score, 30)

    # 3.2 量能配合 (25)
    amount_yi = quote.get('amount_yi', 0)
    turnover = quote['turnover_pct']
    volume_score = 0
    if amount_yi >= 10: volume_score += 12
    elif amount_yi >= 5: volume_score += 8
    elif amount_yi >= 2: volume_score += 5
    elif amount_yi >= 1: volume_score += 3
    if 3 <= turnover <= 10: volume_score += 8
    elif 1 <= turnover < 3 or 10 < turnover <= 15: volume_score += 5
    elif turnover > 15: volume_score += 3
    # 量比
    if len(kline) >= 5:
        avg_vol_5d = kline['volume'].iloc[-6:-1].mean()
        vol_ratio = kline['volume'].iloc[-1] / avg_vol_5d if avg_vol_5d > 0 else 1
        if vol_ratio >= 2: volume_score += 5
        elif vol_ratio >= 1.5: volume_score += 3
        elif vol_ratio >= 1: volume_score += 1
    scores['量能配合'] = min(volume_score, 25)

    # 3.3 资金推动 (20)
    main_inflow = (fund or {}).get('main_inflow_yi', 0)
    big_ratio = (fund or {}).get('big_ratio_pct', 0)
    money_score = 0
    if main_inflow >= 2: money_score += 15
    elif main_inflow >= 1: money_score += 12
    elif main_inflow >= 0.3: money_score += 8
    elif main_inflow >= 0: money_score += 4
    if big_ratio >= 30: money_score += 5
    elif big_ratio >= 15: money_score += 3
    scores['资金推动'] = min(money_score, 20)

    # 3.4 动能指标 (15)
    momentum = 0
    if len(kline) >= 26:
        dif, dea, macd_bar = calc_macd(kline['close'])
        if dif > dea and macd_bar > 0: momentum += 8
        elif dif > dea: momentum += 5
        # 柱状增长
        if len(kline) >= 27:
            prev_bar = (kline['close'].ewm(span=12, adjust=False).mean().iloc[-2] -
                        kline['close'].ewm(span=26, adjust=False).mean().iloc[-2]) * 2 - \
                       (kline['close'].ewm(span=12, adjust=False).mean().iloc[-3] -
                        kline['close'].ewm(span=26, adjust=False).mean().iloc[-3]) * 2
            if macd_bar > prev_bar: momentum += 2
        # 均线多头
        if len(kline) >= 20:
            ma5 = kline['close'].iloc[-5:].mean()
            ma10 = kline['close'].iloc[-10:].mean()
            ma20 = kline['close'].iloc[-20:].mean()
            if ma5 > ma10 > ma20: momentum += 5
            elif ma5 > ma10: momentum += 2
    scores['动能指标'] = min(momentum, 15)

    # 3.5 龙头属性 (10)
    leader_score = 0
    if len(news) >= 2: leader_score += 5
    elif len(news) >= 1: leader_score += 3
    # 行业热点加成
    hot_industries = ['机器人', '人工智能', '新能源', '半导体', 'AI', '航天', '黄金', '有色金属']
    for hot in hot_industries:
        if hot in industry:
            leader_score += 5
            break
    scores['龙头属性'] = min(leader_score, 10)

    total = sum(scores.values())
    return {'total': total, 'breakdown': scores}


def score_rebound(quote: Dict, kline: pd.DataFrame, fund: Optional[Dict], industry: str, news: List) -> Dict:
    """反弹分数（0-100）"""
    scores = {}

    # 3.1 超跌程度 (30)
    pct_today = quote['pct']
    if len(kline) >= 5:
        pct_5d = (kline['close'].iloc[-1] / kline['close'].iloc[-5] - 1) * 100
    else:
        pct_5d = 0
    if len(kline) >= 20:
        pct_20d = (kline['close'].iloc[-1] / kline['close'].iloc[-20] - 1) * 100
    else:
        pct_20d = 0
    # 距60日高点
    if len(kline) >= 60:
        high_60d = kline['high'].iloc[-60:].max()
        drawdown = (kline['close'].iloc[-1] / high_60d - 1) * 100
    else:
        drawdown = 0

    fall_score = 0
    if pct_5d <= -15: fall_score += 12
    elif pct_5d <= -10: fall_score += 9
    elif pct_5d <= -5: fall_score += 6
    elif pct_5d <= -3: fall_score += 3
    if pct_20d <= -25: fall_score += 10
    elif pct_20d <= -15: fall_score += 7
    elif pct_20d <= -8: fall_score += 4
    if drawdown <= -40: fall_score += 8
    elif drawdown <= -25: fall_score += 5
    elif drawdown <= -15: fall_score += 3
    scores['超跌程度'] = min(fall_score, 30)

    # 3.2 超卖信号 (25)
    oversold = 0
    if len(kline) >= 14:
        rsi = calc_rsi(kline['close'], 14)
        if rsi <= 20: oversold += 12
        elif rsi <= 30: oversold += 8
        elif rsi <= 40: oversold += 4
    if len(kline) >= 9:
        k, d, j = calc_kdj(kline, 9)
        if j < 0: oversold += 8
        elif j < 10: oversold += 5
        elif j < 20: oversold += 3
    if len(kline) >= 20:
        mid, upper, lower = calc_boll(kline['close'], 20)
        if quote['price'] <= lower * 1.02: oversold += 5
    scores['超卖信号'] = min(oversold, 25)

    # 3.3 止跌信号 (20)
    stop_fall = 0
    if pct_today > 0: stop_fall += 5
    if pct_today >= 3: stop_fall += 5
    # 下影线
    body = abs(quote['price'] - quote['open'])
    lower_shadow = min(quote['price'], quote['open']) - quote['low']
    if lower_shadow > body * 2 and lower_shadow > 0: stop_fall += 5
    # 放量
    if len(kline) >= 6:
        avg_vol_5d = kline['volume'].iloc[-6:-1].mean()
        vol_ratio = kline['volume'].iloc[-1] / avg_vol_5d if avg_vol_5d > 0 else 1
        if vol_ratio >= 1.5: stop_fall += 5
    scores['止跌信号'] = min(stop_fall, 20)

    # 3.4 估值修复 (15)
    valuation = 0
    # 简化：用行业 PE 范围判断（暂用历史PE分位估算）
    if pct_20d <= -20: valuation += 8
    elif pct_20d <= -10: valuation += 5
    if drawdown <= -30: valuation += 7
    elif drawdown <= -15: valuation += 4
    scores['估值修复'] = min(valuation, 15)

    # 3.5 资金异动 (10)
    money = 0
    main_inflow = (fund or {}).get('main_inflow_yi', 0)
    if main_inflow > 0: money += 6
    if main_inflow >= 0.5: money += 4
    scores['资金异动'] = min(money, 10)

    total = sum(scores.values())
    return {'total': total, 'breakdown': scores}


def score_range(quote: Dict, kline: pd.DataFrame, fund: Optional[Dict], industry: str, news: List) -> Dict:
    """震荡分数（0-100）"""
    scores = {}

    # 3.1 区间特征 (30)
    if len(kline) >= 10:
        high_10d = kline['high'].iloc[-10:].max()
        low_10d = kline['low'].iloc[-10:].min()
        amplitude_10d = (high_10d / low_10d - 1) * 100 if low_10d > 0 else 0
    else:
        amplitude_10d = 0
    if len(kline) >= 20:
        high_20d = kline['high'].iloc[-20:].max()
        low_20d = kline['low'].iloc[-20:].min()
        range_20d = (high_20d / low_20d - 1) * 100 if low_20d > 0 else 0
    else:
        range_20d = 0
    pct_today = quote['pct']

    range_score = 0
    if 3 <= amplitude_10d <= 8: range_score += 15
    elif 1 <= amplitude_10d < 3 or 8 < amplitude_10d <= 12: range_score += 10
    elif amplitude_10d > 12: range_score += 5
    if 5 <= range_20d <= 15: range_score += 10
    elif 3 <= range_20d < 5 or 15 < range_20d <= 20: range_score += 7
    # BOLL 中轨附近
    if len(kline) >= 20:
        mid, upper, lower = calc_boll(kline['close'], 20)
        if abs(quote['price'] - mid) / mid < 0.03: range_score += 5
    scores['区间特征'] = min(range_score, 30)

    # 3.2 量能特征 (25)
    turnover = quote['turnover_pct']
    vol_score = 0
    if 3 <= turnover <= 6: vol_score += 15
    elif 1.5 <= turnover < 3 or 6 < turnover <= 10: vol_score += 10
    elif 1 <= turnover < 1.5: vol_score += 5
    # 5日均量稳定
    if len(kline) >= 6:
        vols = kline['volume'].iloc[-5:]
        cv = vols.std() / vols.mean() if vols.mean() > 0 else 1
        if cv < 0.3: vol_score += 10
        elif cv < 0.5: vol_score += 5
    scores['量能特征'] = min(vol_score, 25)

    # 3.3 趋势中性 (20)
    neutral = 0
    if len(kline) >= 20:
        ma5 = kline['close'].iloc[-5:].mean()
        ma10 = kline['close'].iloc[-10:].mean()
        ma20 = kline['close'].iloc[-20:].mean()
        # 均线缠绕
        ma_spread = (max(ma5, ma10, ma20) - min(ma5, ma10, ma20)) / ma20
        if ma_spread < 0.03: neutral += 12
        elif ma_spread < 0.05: neutral += 8
        elif ma_spread < 0.08: neutral += 4
        # MACD 柱体极小
        if len(kline) >= 26:
            dif, dea, macd_bar = calc_macd(kline['close'])
            if abs(macd_bar) < abs(dif) * 0.1: neutral += 8
            elif abs(macd_bar) < abs(dif) * 0.3: neutral += 4
    scores['趋势中性'] = min(neutral, 20)

    # 3.4 位置特征 (15)
    position = 0
    if len(kline) >= 20:
        high_20d = kline['high'].iloc[-20:].max()
        low_20d = kline['low'].iloc[-20:].min()
        if high_20d > low_20d:
            current_pos = (quote['price'] - low_20d) / (high_20d - low_20d)
            if current_pos <= 0.3: position += 8  # 接近下沿
            elif current_pos >= 0.7: position += 5
            elif 0.4 <= current_pos <= 0.6: position += 3
    scores['位置特征'] = min(position, 15)

    # 3.5 支撑压力 (10)
    support = 0
    # 简化：振幅不大 + 成交稳定 = 支撑压力清晰
    if 2 <= amplitude_10d <= 10: support += 5
    # 离整数关口近
    price = quote['price']
    round_num = round(price / 10) * 10
    if abs(price - round_num) / price < 0.03: support += 5
    scores['支撑压力'] = min(support, 10)

    total = sum(scores.values())
    return {'total': total, 'breakdown': scores}


# ==========================================
# 4. 综合决策
# ==========================================

def make_decision(chase: int, rebound: int, rng: int) -> Tuple[str, str, str]:
    """根据三个分数生成操作建议"""
    if chase >= 70 and rebound < 40 and rng < 40:
        return '🟢 追涨', '30-50%', '强势追高标的'
    elif 50 <= chase < 70 and rebound < 40 and rng < 40:
        return '🟢 谨慎追涨', '10-20%', '可适量追涨'
    elif chase < 40 and rebound >= 70 and rng < 40:
        return '🟡 抄底反弹', '20-30%', '超跌反弹机会'
    elif chase < 40 and 50 <= rebound < 70 and rng < 40:
        return '🟡 试探建仓', '10-15%', '可能企稳'
    elif chase < 40 and rebound < 40 and rng >= 70:
        return '🔵 高抛低吸', '滚动仓', '典型震荡区间'
    elif chase < 40 and rebound < 40 and 50 <= rng < 70:
        return '🔵 区间操作', '30-50%', '可做T'
    elif chase < 40 and rebound < 40 and rng < 40:
        return '🔴 空仓观望', '0%', '方向不明，等待'
    else:
        # 多个分数都高（强博弈）或都不高不低
        if chase >= 60 and rebound >= 60:
            return '🟣 强博弈', '减仓', '强反弹后追高，风险大'
        elif chase >= 50 and rng >= 50:
            return '🟣 突破在即', '观察', '可能向上突破'
        else:
            return '⚪ 继续观察', '持有', '当前信号不明确'


# ==========================================
# 5. 报告生成
# ==========================================

def analyze_stock(code: str, name: str = None) -> str:
    """分析单只股票，返回 Markdown 报告"""
    # 自动识别市场
    if not code.startswith(('sh', 'sz')):
        if code.startswith(('6', '5')):
            code = f'sh{code}'
        else:
            code = f'sz{code}'

    raw_code = code.replace('sh', '').replace('sz', '')

    lines = []
    lines.append(f'# 🎯 {name or "?"}（{raw_code}）三向评分')
    lines.append(f'生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    lines.append('')

    # 数据获取
    print(f'  获取行情...', flush=True)
    quote = get_quote_safe(code)
    if not quote:
        return f'❌ 获取行情失败: {code}'

    print(f'  获取K线...', flush=True)
    kline = get_kline_safe(code, 60)
    if kline is None or len(kline) < 20:
        lines.append(f'⚠️ K线数据不足（{len(kline) if kline is not None else 0} 条），技术指标可能不准确')
        if kline is None:
            kline = pd.DataFrame()

    print(f'  获取资金流...', flush=True)
    fund = get_fund_flow_safe(code)

    print(f'  获取板块/新闻...', flush=True)
    industry_info = get_industry(code)
    industry = (industry_info or {}).get('industry', '未知')
    news = get_related_news(code, name)

    # 速览
    lines.append('## 速览')
    lines.append('| 项目 | 数值 |')
    lines.append('|------|------|')
    lines.append(f'| 当前价 | {quote["price"]}元 |')
    lines.append(f'| 涨跌幅 | {quote["pct"]:+.2f}% |')
    lines.append(f'| 换手率 | {quote["turnover_pct"]:.2f}% |')
    lines.append(f'| 成交额 | {quote["amount_yi"]:.2f}亿 |')
    main_inflow_disp = f'{(fund or {}).get("main_inflow_yi", 0):+.2f}亿' if fund else 'N/A'
    lines.append(f'| 主力净流入 | {main_inflow_disp} |')
    lines.append(f'| 所属行业 | {industry} |')
    lines.append(f'| 关联新闻 | {len(news)} 条 |')
    lines.append('')

    # 计算三向分数
    print(f'  计算追高分数...', flush=True)
    chase = score_chase(quote, kline, fund, industry, news)
    print(f'  计算反弹分数...', flush=True)
    rebound = score_rebound(quote, kline, fund, industry, news)
    print(f'  计算震荡分数...', flush=True)
    rng = score_range(quote, kline, fund, industry, news)

    # 综合决策
    action, position, desc = make_decision(chase['total'], rebound['total'], rng['total'])

    def rating(s):
        if s >= 80: return '⭐⭐⭐⭐⭐'
        if s >= 60: return '⭐⭐⭐⭐'
        if s >= 40: return '⭐⭐⭐'
        if s >= 20: return '⭐⭐'
        return '⭐'

    # 分数总表
    lines.append('## 三向分数')
    lines.append('| 分数 | 数值 | 评级 |')
    lines.append('|------|------|------|')
    lines.append(f'| 🔴 追高分数 | {chase["total"]}/100 | {rating(chase["total"])} |')
    lines.append(f'| 🟡 反弹分数 | {rebound["total"]}/100 | {rating(rebound["total"])} |')
    lines.append(f'| 🔵 震荡分数 | {rng["total"]}/100 | {rating(rng["total"])} |')
    lines.append('')

    # 决策
    lines.append('## 综合决策')
    lines.append(f'**操作建议**: {action}')
    lines.append(f'**建议仓位**: {position}')
    lines.append(f'**理由说明**: {desc}')
    lines.append('')

    # 追高拆解
    lines.append('## 🔴 追高分数拆解')
    for k, v in chase['breakdown'].items():
        lines.append(f'- {k}: {v}')
    lines.append(f'- **总分: {chase["total"]}/100**')
    lines.append('')

    # 反弹拆解
    lines.append('## 🟡 反弹分数拆解')
    for k, v in rebound['breakdown'].items():
        lines.append(f'- {k}: {v}')
    lines.append(f'- **总分: {rebound["total"]}/100**')
    lines.append('')

    # 震荡拆解
    lines.append('## 🔵 震荡分数拆解')
    for k, v in rng['breakdown'].items():
        lines.append(f'- {k}: {v}')
    lines.append(f'- **总分: {rng["total"]}/100**')
    lines.append('')

    # 技术指标详情
    if len(kline) >= 20:
        lines.append('## 📊 技术指标')
        k, d, j = calc_kdj(kline, 9)
        rsi = calc_rsi(kline['close'], 14)
        dif, dea, macd_bar = calc_macd(kline['close'])
        mid, upper, lower = calc_boll(kline['close'], 20)
        lines.append('| 指标 | 数值 | 信号 |')
        lines.append('|------|------|------|')
        rsi_sig = '超买' if rsi > 70 else '超卖' if rsi < 30 else '中性'
        kdj_sig = '金叉' if k > d else '死叉'
        macd_sig = '金叉' if dif > dea and macd_bar > 0 else '死叉' if dif < dea and macd_bar < 0 else '弱势'
        boll_pos = '上轨' if quote['price'] >= upper else '下轨' if quote['price'] <= lower else '中轨'
        lines.append(f'| RSI(14) | {rsi:.1f} | {rsi_sig} |')
        lines.append(f'| KDJ | K={k:.1f} D={d:.1f} J={j:.1f} | {kdj_sig} |')
        lines.append(f'| MACD | DIF={dif:.3f} DEA={dea:.3f} | {macd_sig} |')
        lines.append(f'| BOLL | {lower:.2f} / {mid:.2f} / {upper:.2f} | {boll_pos} |')
        lines.append('')

    # 关联新闻
    if news:
        lines.append('## 📰 关联新闻')
        for n in news[:5]:
            lines.append(f'- {n["title"]}')
            if n.get('source'):
                lines.append(f'  来源: {n["source"]} | 重要性: {n.get("score", 0):.1f}/10')
        lines.append('')

    lines.append('---')
    lines.append('⚠️ 仅供参考，不构成投资建议')

    return '\n'.join(lines)


# ==========================================
# 6. 主流程
# ==========================================

def load_holdings() -> List[Dict]:
    """从 data/holdings.txt 加载持仓列表"""
    holdings_path = '/root/.openclaw/workspace/data/holdings.txt'
    holdings = []
    try:
        with open(holdings_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split(',')
                if len(parts) >= 3:
                    name, code, cost = parts[0].strip(), parts[1].strip(), float(parts[2].strip())
                    holdings.append({'name': name, 'code': code, 'cost': cost})
    except Exception as e:
        print(f'⚠️ 加载持仓文件失败: {e}')
    return holdings


def analyze_holdings() -> str:
    """分析所有持仓股票，返回汇总报告"""
    holdings = load_holdings()
    if not holdings:
        return '❌ 未加载到任何持仓'

    print(f'加载到 {len(holdings)} 只持仓')
    print()

    results = []
    for h in holdings:
        name, code, cost = h['name'], h['code'], h['cost']
        # 补全市场前缀
        if not code.startswith(('sh', 'sz')):
            full_code = ('sh' if code.startswith(('6', '5')) else 'sz') + code
        else:
            full_code = code
        raw_code = full_code.replace('sh', '').replace('sz', '')

        print(f'分析: {name} ({full_code})...', flush=True)
        try:
            quote = get_quote_safe(full_code)
            if not quote:
                print(f'  ⚠️ {name} 获取行情失败，跳过')
                continue

            kline_raw = get_kline_safe(full_code, 60)
            kline = kline_raw if (kline_raw is not None and len(kline_raw) > 0) else pd.DataFrame()
            fund = get_fund_flow_safe(full_code)
            industry_info = get_industry(full_code)
            industry = (industry_info or {}).get('industry', '未知')
            news = get_related_news(full_code, name)

            # 三向分数
            chase = score_chase(quote, kline, fund, industry, news)
            rebound = score_rebound(quote, kline, fund, industry, news)
            rng = score_range(quote, kline, fund, industry, news)
            action, position, desc = make_decision(chase['total'], rebound['total'], rng['total'])

            # 盈亏计算
            current_price = quote['price']
            profit_pct = (current_price / cost - 1) * 100 if cost > 0 else 0
            profit_amount = (current_price - cost) * 100  # 假设 100 股

            results.append({
                'name': name,
                'code': raw_code,
                'cost': cost,
                'price': current_price,
                'pct': quote['pct'],
                'profit_pct': profit_pct,
                'profit_amount': profit_amount,
                'chase': chase['total'],
                'rebound': rebound['total'],
                'rng': rng['total'],
                'action': action,
                'position': position,
                'desc': desc,
                'industry': industry,
                'main_inflow': (fund or {}).get('main_inflow_yi', 0),
                'news_count': len(news),
            })
        except Exception as e:
            print(f'  ❌ {name} 分析失败: {e}')
            continue

    if not results:
        return '❌ 所有持仓分析都失败'

    # 生成汇总报告
    lines = []
    lines.append(f'# 📊 持仓分析报告（{len(results)} 只）')
    lines.append(f'生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    lines.append('')

    # 综合总览表
    lines.append('## 🎯 三向分数总览')
    lines.append('| 股票 | 当前价 | 今日 | 盈亏% | 追高 | 反弹 | 震荡 | 操作建议 | 仓位 |')
    lines.append('|------|--------|------|-------|------|------|------|----------|------|')
    # 按追高分数排序（机会优先）
    for r in sorted(results, key=lambda x: max(x['chase'], x['rebound'], x['rng']), reverse=True):
        emoji_price = '🟢' if r['pct'] > 0 else '🔴'
        emoji_pft = '🟢' if r['profit_pct'] > 0 else '🔴'
        lines.append(
            f'| {r["name"]}({r["code"]}) | {r["price"]:.2f} | {emoji_price}{r["pct"]:+.2f}% | {emoji_pft}{r["profit_pct"]:+.1f}% | '
            f'{r["chase"]} | {r["rebound"]} | {r["rng"]} | {r["action"]} | {r["position"]} |'
        )
    lines.append('')

    # 总盈亏
    total_pft = sum(r['profit_amount'] for r in results)
    total_pft_pct = sum(r['profit_pct'] for r in results) / len(results) if results else 0
    emoji_total = '🟢' if total_pft > 0 else '🔴'
    lines.append(f'## 💰 总盈亏（按100股估算）')
    lines.append(f'**总盈亏**: {emoji_total} {total_pft:+.0f} 元 | 平均: {emoji_total} {total_pft_pct:+.2f}%')
    lines.append('')

    # 按操作建议分类
    lines.append('## 📋 操作建议分组')
    groups = {}
    for r in results:
        action_key = r['action'].split(' ')[0]  # 提取 emoji
        if action_key not in groups:
            groups[action_key] = []
        groups[action_key].append(r)

    action_labels = {
        '🟢': '🟢 追涨组',
        '🟡': '🟡 抄底/试探组',
        '🔵': '🔵 震荡/做T组',
        '🔴': '🔴 空仓/回避组',
        '🟣': '🟣 强博弈/突破组',
        '⚪': '⚪ 观察组',
    }
    for emoji, group in groups.items():
        label = action_labels.get(emoji, emoji)
        names = '、'.join([f'{r["name"]}({r["chase"]}/{r["rebound"]}/{r["rng"]})' for r in group])
        lines.append(f'- **{label}** ({len(group)} 只): {names}')
    lines.append('')

    # 关键信号
    lines.append('## 🔍 关键信号')
    # 追高机会（追高≥60）
    chase_top = [r for r in results if r['chase'] >= 60]
    if chase_top:
        lines.append(f'**追涨机会** (追高≥60): {", ".join([f"{r["name"]}({r["chase"]})" for r in chase_top])}')
    # 抄底机会（反弹≥60）
    rebound_top = [r for r in results if r['rebound'] >= 60]
    if rebound_top:
        lines.append(f'**抄底机会** (反弹≥60): {", ".join([f"{r["name"]}({r["rebound"]})" for r in rebound_top])}')
    # 减仓信号（追高≥60 且 反弹≥60）
    risk_top = [r for r in results if r['chase'] >= 60 and r['rebound'] >= 60]
    if risk_top:
        lines.append(f'**强博弈风险** (追高+反弹双高): {", ".join([f"{r["name"]}" for r in risk_top])} - 强反弹后追高风险大')
    # 全部低分
    all_low = [r for r in results if max(r['chase'], r['rebound'], r['rng']) < 40]
    if all_low:
        lines.append(f'**观望** (三向均低): {", ".join([f"{r["name"]}" for r in all_low])}')
    # 关联新闻
    news_top = [r for r in results if r['news_count'] > 0]
    if news_top:
        lines.append(f'**今日有新闻** ({len(news_top)} 只): {", ".join([f"{r["name"]}({r["news_count"]}条)" for r in news_top])}')
    lines.append('')

    # 详细数据
    lines.append('## 📈 详细数据')
    lines.append('| 股票 | 行业 | 主力净流入 | 今日新闻 | 备注 |')
    lines.append('|------|------|------------|----------|------|')
    for r in results:
        main_str = f'{r["main_inflow"]:+.2f}亿' if r['main_inflow'] else 'N/A'
        lines.append(f'| {r["name"]} | {r["industry"]} | {main_str} | {r["news_count"]} | {r["desc"]} |')
    lines.append('')

    lines.append('---')
    lines.append('⚠️ 仅供参考，不构成投资建议')

    return '\n'.join(lines)


def main():
    if len(sys.argv) < 2:
        # 无参数：分析所有持仓
        print('=' * 50)
        print('未指定股票，分析所有持仓')
        print('=' * 50)
        print()
        report = analyze_holdings()
        print()
        print(report)
        return

    target = sys.argv[1]
    code = None
    name = None
    raw_code = target

    # 如果是 6 位数字，识别为代码
    if target.isdigit() and len(target) == 6:
        code = ('sh' if target.startswith(('6', '5')) else 'sz') + target
    else:
        # 名称搜索
        print(f'搜索股票: {target}...', flush=True)
        code = get_stock_by_name(target)
        if not code:
            print(f'❌ 未找到股票: {target}')
            sys.exit(1)

    # 获取名称（从实时行情拿）
    try:
        df = get_stocks_quote([code])
        if df is not None and len(df) > 0:
            name = df.iloc[0]['名称']
    except Exception:
        name = None

    if not name:
        name = target

    print(f'分析: {name} ({code})')
    print('=' * 50)
    print()
    report = analyze_stock(code, name)
    print()
    print(report)


if __name__ == '__main__':
    main()
