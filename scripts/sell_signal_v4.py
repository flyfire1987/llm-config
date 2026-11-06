#!/usr/bin/env python3
"""
卖出信号检测脚本 v4.2（ETF/个股双版本）
- ETF：紧跟指数走势，阈值宽松，缩量提示关闭
- 个股：保守风控，保留完整技术面信号
自动识别持仓类型切换逻辑
"""

import requests
import re
import akshare as ak
import pandas as pd
from datetime import datetime

HOLDINGS_FILE = "/root/.openclaw/workspace/data/holdings.txt"

# ETF 关键词列表（命中则走ETF逻辑）
ETF_KEYWORDS = ["ETF", "etf", "指数", "50", "300", "500", "1000", "2000", "创业板", "科创", "MSCI", "纳斯达克", "恒生", "标普"]

def is_etf(name):
    """判断是否为ETF"""
    for kw in ETF_KEYWORDS:
        if kw in name:
            return True
    return False

def load_holdings():
    """加载持仓数据"""
    holdings = []
    with open(HOLDINGS_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                parts = line.split(',')
                def to_float(val):
                    try:
                        return float(val) if val.strip() else None
                    except ValueError:
                        return None
                if len(parts) >= 3:
                    holdings.append({
                        'name': parts[0],
                        'code': parts[1],
                        'cost': float(parts[2]),
                        'stop_loss': to_float(parts[3]) if len(parts) > 3 else None,
                        'profit_target': to_float(parts[4]) if len(parts) > 4 else None,
                    })
    return holdings

def get_realtime_price(code):
    """获取实时价格"""
    try:
        if code.startswith('6') or code.startswith('5'):
            qcode = f"sh{code}"
        else:
            qcode = f"sz{code}"
        
        url = f"https://qt.gtimg.cn/q={qcode}"
        resp = requests.get(url, timeout=5)
        fields = resp.text.split('"')[1].split('~')
        price = float(fields[3])
        prev_close = float(fields[4])
        high_price = float(fields[33]) if fields[33] else price
        low_price = float(fields[34]) if fields[34] else price
        volume = float(fields[38]) if fields[38] and fields[38] != '-' else 0
        turnover = float(fields[39]) if fields[39] and fields[39] != '-' else 0
        pct = (price - prev_close) / prev_close * 100
        
        return {
            'price': price,
            'prev_close': prev_close,
            'open': float(fields[5]) if fields[5] else prev_close,
            'high': float(fields[33]) if fields[33] else price,
            'low': float(fields[34]) if fields[34] else price,
            'volume': volume,
            'turnover': turnover,
            'pct': pct
        }
    except:
        return None

def get_30min_trend(code):
    """获取近30分钟分时趋势
    返回：(趋势方向, 涨跌幅, 说明)
    趋势方向: 'up' / 'down' / 'neutral'
    """
    try:
        if code.startswith('6') or code.startswith('5'):
            market = "sh" + code
        else:
            market = "sz" + code
        
        # 获取今日分时数据（5分钟频率）
        df = ak.stock_zh_a_minute(symbol=market, period="5", adjust="")
        
        # 取最近6根5分钟K线（约30分钟）
        df = df.tail(6)
        
        if len(df) < 3:
            return None
        
        # 计算趋势：比较首尾价格
        start_price = df['close'].iloc[0]
        end_price = df['close'].iloc[-1]
        change_pct = (end_price - start_price) / start_price * 100
        
        # 同时看中间是否有明显下探后拉回（V型）
        min_price = df['low'].min()
        min_pos = df['low'].idxmin()
        min_idx = df.index.get_loc(min_pos)
        
        # 判断趋势
        if change_pct > 0.1:
            direction = 'up'
        elif change_pct < -0.1:
            direction = 'down'
        else:
            direction = 'neutral'
        
        # V型反转检测：创低后反弹超过0.3%
        if min_idx > 0 and min_idx < len(df) - 1:
            rebound = (end_price - min_price) / min_price * 100
            if rebound > 0.3 and change_pct > 0:
                return {
                    'direction': 'rebound',  # V型反弹
                    'change_pct': change_pct,
                    'min_drop': (min_price - start_price) / start_price * 100,
                    'rebound_pct': rebound,
                    'desc': f'V型反弹↑{rebound:.2f}%'
                }
        
        return {
            'direction': direction,
            'change_pct': change_pct,
            'desc': f'30分钟{"↑" if direction=="up" else "↓" if direction=="down" else "→"}{change_pct:+.2f}%'
        }
    except Exception as e:
        return None

def get_main_money_flow(code):
    """获取主力资金净流入
    返回：净流入额（元）及其状态
    """
    try:
        if code.startswith('6') or code.startswith('5'):
            market = "sh" + code
        else:
            market = "sz" + code
        
        # 使用akshare的资金流数据
        df = ak.stock_individual_fund_flow(stock=market, market="sh" if code.startswith('6') or code.startswith('5') else "sz")
        
        # 取最新一行
        latest = df.iloc[-1]
        
        # 主力净流入 = 超大单净流入 + 大单净流入
        try:
            # 列名可能是"主力净流入-净额"或类似
            cols = df.columns.tolist()
            net_col = [c for c in cols if '主力' in c and '净额' in c]
            if net_col:
                main_net = float(latest[net_col[0]])
            else:
                # 尝试计算
                super_col = [c for c in cols if '超大单' in c and '净额' in c]
                big_col = [c for c in cols if '大单' in c and '净额' in c]
                main_net = 0
                if super_col:
                    main_net += float(latest[super_col[0]])
                if big_col:
                    main_net += float(latest[big_col[0]])
        except:
            main_net = None
        
        if main_net is None:
            return None
        
        # 判断状态
        if main_net > 0:
            status = 'inflow'  # 主力净流入
            desc = f'主力净流入 {main_net/100000000:.2f}亿'
        else:
            status = 'outflow'  # 主力净流出
            desc = f'主力净流出 {abs(main_net)/100000000:.2f}亿'
        
        return {
            'net': main_net,
            'status': status,
            'desc': desc
        }
    except:
        return None

def get_market_index():
    """获取大盘指数实时数据"""
    indices = [
        ("sh000001", "上证指数"),
        ("sh399001", "深证成指"),
        ("sz399006", "创业板指"),
        ("sh000688", "科创50"),
    ]
    
    results = []
    for qcode, name in indices:
        try:
            url = f"https://qt.gtimg.cn/q={qcode}"
            resp = requests.get(url, timeout=5)
            fields = resp.text.split('"')[1].split('~')
            price = float(fields[3])
            prev_close = float(fields[4])
            pct = (price - prev_close) / prev_close * 100
            high = float(fields[33]) if fields[33] else price
            low = float(fields[34]) if fields[34] else price
            turnover = float(fields[39]) if fields[39] and fields[39] != '-' else 0
            
            results.append({
                'name': name,
                'code': qcode,
                'price': price,
                'prev_close': prev_close,
                'pct': pct,
                'high': high,
                'low': low,
                'turnover': turnover / 100000000 if turnover else 0,
            })
        except:
            pass
    return results

def get_index_technical(index_code):
    """获取指数技术指标（上证为主）"""
    try:
        df = ak.stock_zh_index_daily(symbol=index_code.replace("sh", "000001").replace("sz", "399001"))
        df = df.tail(60)
        
        closes = df['close']
        highs = df['high']
        lows = df['low']
        
        ma5 = closes.rolling(5).mean().iloc[-1]
        ma10 = closes.rolling(10).mean().iloc[-1]
        ma20 = closes.rolling(20).mean().iloc[-1]
        ma60 = closes.rolling(60).mean().iloc[-1] if len(closes) >= 60 else None
        
        ema12 = closes.ewm(span=12, adjust=False).mean()
        ema26 = closes.ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()
        macd_bar = 2 * (dif - dea)
        
        period = 9
        highest = highs.rolling(period).max()
        lowest = lows.rolling(period).min()
        rsv = (closes - lowest) / (highest - lowest) * 100
        k = rsv.ewm(com=2, adjust=False).mean()
        d = k.ewm(com=2, adjust=False).mean()
        j = 3 * k - 2 * d
        
        delta = closes.diff()
        gain = delta.where(delta > 0, 0)
        loss = (-delta).where(delta < 0, 0)
        avg_gain = gain.ewm(com=13, adjust=False).mean()
        avg_loss = loss.ewm(com=13, adjust=False).mean()
        rs = avg_gain / avg_loss
        rsi = (100 - (100 / (1 + rs))).iloc[-1]
        
        bbr_mid = closes.rolling(20).mean()
        bbr_std = closes.rolling(20).std()
        bbr_upper = (bbr_mid + 2 * bbr_std).iloc[-1]
        bbr_lower = (bbr_mid - 2 * bbr_std).iloc[-1]
        
        return {
            'ma5': ma5, 'ma10': ma10, 'ma20': ma20, 'ma60': ma60,
            'dif': dif.iloc[-1], 'dea': dea.iloc[-1], 'macd_bar': macd_bar.iloc[-1],
            'k': k.iloc[-1], 'd': d.iloc[-1], 'j': j.iloc[-1], 'rsi': rsi,
            'bbr_upper': bbr_upper, 'bbr_mid': bbr_mid.iloc[-1], 'bbr_lower': bbr_lower,
            'current': closes.iloc[-1],
        }
    except:
        return None

def get_technical(code):
    """获取个股技术指标"""
    try:
        if code.startswith('6') or code.startswith('5'):
            market = "sh" + code
        else:
            market = "sz" + code
        
        df = ak.stock_zh_a_daily(symbol=market, adjust="qfq")
        df = df.tail(60)
        
        closes = df['close']
        highs = df['high']
        lows = df['low']
        
        ma5 = closes.rolling(5).mean().iloc[-1]
        ma10 = closes.rolling(10).mean().iloc[-1]
        ma20 = closes.rolling(20).mean().iloc[-1]
        ma60 = closes.rolling(60).mean().iloc[-1] if len(closes) >= 60 else None
        
        ema12 = closes.ewm(span=12, adjust=False).mean()
        ema26 = closes.ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()
        macd_bar = 2 * (dif - dea)
        
        period = 9
        highest = highs.rolling(period).max()
        lowest = lows.rolling(period).min()
        rsv = (closes - lowest) / (highest - lowest) * 100
        k = rsv.ewm(com=2, adjust=False).mean()
        d = k.ewm(com=2, adjust=False).mean()
        j = 3 * k - 2 * d
        
        delta = closes.diff()
        gain = delta.where(delta > 0, 0)
        loss = (-delta).where(delta < 0, 0)
        avg_gain = gain.ewm(com=13, adjust=False).mean()
        avg_loss = loss.ewm(com=13, adjust=False).mean()
        rs = avg_gain / avg_loss
        rsi = (100 - (100 / (1 + rs))).iloc[-1]
        
        bbr_mid = closes.rolling(20).mean()
        bbr_std = closes.rolling(20).std()
        bbr_upper = (bbr_mid + 2 * bbr_std).iloc[-1]
        bbr_lower = (bbr_mid - 2 * bbr_std).iloc[-1]
        
        return {
            'ma5': ma5, 'ma10': ma10, 'ma20': ma20, 'ma60': ma60,
            'dif': dif.iloc[-1], 'dea': dea.iloc[-1], 'macd_bar': macd_bar.iloc[-1],
            'k': k.iloc[-1], 'd': d.iloc[-1], 'j': j.iloc[-1], 'rsi': rsi,
            'bbr_upper': bbr_upper, 'bbr_mid': bbr_mid.iloc[-1], 'bbr_lower': bbr_lower,
            'current': closes.iloc[-1],
        }
    except:
        return None

def get_market_overview():
    """获取市场整体概况"""
    try:
        df = ak.stock_spot_em()
        rise = len(df[df['涨跌幅'] > 0])
        fall = len(df[df['涨跌幅'] < 0])
        total = rise + fall
        ratio = round(rise / fall, 2) if fall > 0 else 0
        return {'rise': rise, 'fall': fall, 'ratio': ratio}
    except:
        return None

def get_trend_signal(tech):
    """均线趋势"""
    if not tech:
        return "数据不足"
    ma5, ma10, ma20 = tech['ma5'], tech['ma10'], tech['ma20']
    if ma5 > ma10 > ma20:
        return "📈 多头排列"
    elif ma5 < ma10 < ma20:
        return "📉 空头排列"
    else:
        return "📊 均线缠绕"

def get_bbr_position(price, upper, mid, lower):
    """布林带位置"""
    if price < lower:
        return "🔴 触及下轨"
    elif price > upper:
        return "🟢 触及上轨"
    elif price > mid:
        return "🟡 中上轨"
    else:
        return "🟡 中下轨"

def analyze_etf_signal(name, code, cost, stop_loss, profit_target, market_data, market_overview):
    """
    ETF 卖出信号分析（宽松版）
    核心逻辑：紧跟指数，以指数技术面为主要信号
    """
    rt = get_realtime_price(code)
    if rt is None:
        return None
    
    tech = get_technical(code)
    price = rt['price']
    pct = rt['pct']
    profit = (price - cost) / cost * 100
    
    # 找跟踪的指数
    target_index = None
    if "科创" in name or "588" in code:
        for idx in market_data:
            if "科创50" in idx['name']:
                target_index = idx
                break
    elif "50" in name or "300" in name or "500" in name:
        for idx in market_data:
            if "上证" in idx['name'] or "沪深" in idx['name']:
                target_index = idx
                break
    else:
        target_index = market_data[0] if market_data else None
    
    index_pct = target_index['pct'] if target_index else None
    relative = pct - index_pct if index_pct is not None else 0
    
    signals = []
    
    # 1. 止损（ETF宽松，仍保留）
    if stop_loss and price <= stop_loss:
        return {'name': name, 'code': code, 'price': price, 'pct': pct,
                'profit': profit, 'cost': cost, 'stop_loss': stop_loss,
                'profit_target': profit_target,
                'signal': '🔴', 'type': '止损', 'action': f'跌破{stop_loss}，清仓',
                'tech': tech, 'rt': rt, 'market_data': market_data, 'market_overview': market_overview,
                'is_etf': True, 'target_index': target_index, 'relative': relative, 'pattern': '止损'}
    
    # 2. 目标价
    if profit_target and price >= profit_target:
        signals.append(('🟠', '触及目标', f'盈利目标{profit_target}，部分止盈'))
    
    # 3. ETF核心：指数技术面信号（均线多头/空头排列）
    index_tech = None
    if target_index:
        idx_code = target_index['code']
        index_tech = get_index_technical(idx_code)
    
    if index_tech:
        trend = get_trend_signal(index_tech)
        if "空头" in trend:
            signals.append(('🔴', '指数空头排列', f'{target_index["name"]}{trend}，减仓'))
        elif "多头" in trend and profit > 8:
            signals.append(('🟡', '指数多头但盈利丰厚', f'指数{trend}，盈利{profit:.1f}%，可分批止盈'))
        
        # 指数MACD死叉
        if index_tech['dif'] < index_tech['dea'] and index_tech['macd_bar'] < 0:
            signals.append(('🟡', '指数MACD死叉', f'{target_index["name"]}趋势转弱，减1/3'))
        
        # 指数超买（ETF阈值放宽到95）
        if index_tech['j'] > 95:
            signals.append(('🟡', '指数KDJ极端超买', f'J={index_tech["j"]:.0f}，注意短线回调风险'))
        elif index_tech['rsi'] > 85:
            signals.append(('🟡', '指数RSI极端超买', f'RSI={index_tech["rsi"]:.0f}，高位减仓'))
    
    # 4. 大盘系统风险（保留，ETF对大盘更敏感）
    if index_pct is not None:
        if index_pct < -2:
            signals.insert(0, ('🔴', '指数大跌', f'{target_index["name"]}{index_pct:.2f}%，系统性风险，控制仓位'))
        elif index_pct < -1:
            signals.append(('🔴', '指数偏弱', f'{target_index["name"]}{index_pct:.2f}%，谨慎'))
    
    # 5. 市场整体赚钱效应
    if market_overview and market_overview.get('ratio', 1) < 0.5 and index_pct and index_pct < 0:
        signals.insert(0, ('🔴', '市场普跌', f'涨跌比{market_overview["ratio"]}，赚钱效应差'))
    
    # 6. 相对强弱（ETF跑赢/跑输指数）
    if abs(relative) > 1:
        if relative > 1:
            signals.append(('🟢', f'跑赢指数{relative:.1f}%', 'ETF强于基准'))
        else:
            signals.append(('🔴', f'跑输指数{relative:.1f}%', 'ETF弱于基准，关注'))
    
    # 7. ETF特有：缩量提示关闭，不做缩量判断
    
    # 8. 盈利丰厚 + 指数高位 = 部分止盈
    if profit > 15 and index_tech and index_tech['rsi'] > 70:
        signals.append(('🟠', '盈利丰厚+指数高位', f'盈利{profit:.1f}%+RSI{index_tech["rsi"]:.0f}，建议止盈一半'))
    
    # 选择最强信号
    if signals:
        priority_keywords = ['止损', '目标', '大跌', '普跌', '空头']
        for sig in signals:
            if any(kw in sig[1] for kw in priority_keywords):
                return {'name': name, 'code': code, 'price': price, 'pct': pct,
                        'profit': profit, 'cost': cost, 'stop_loss': stop_loss,
                        'profit_target': profit_target,
                        'signal': sig[0], 'type': sig[1], 'action': sig[2],
                        'tech': tech, 'rt': rt, 'market_data': market_data, 'market_overview': market_overview,
                        'is_etf': True, 'target_index': target_index, 'relative': relative,
                        'index_tech': index_tech, 'pattern': sig[1]}
        return {'name': name, 'code': code, 'price': price, 'pct': pct,
                'profit': profit, 'cost': cost, 'stop_loss': stop_loss,
                'profit_target': profit_target,
                'signal': signals[0][0], 'type': signals[0][1], 'action': signals[0][2],
                'tech': tech, 'rt': rt, 'market_data': market_data, 'market_overview': market_overview,
                'is_etf': True, 'target_index': target_index, 'relative': relative,
                'index_tech': index_tech, 'pattern': signals[0][1]}
    
    return {'name': name, 'code': code, 'price': price, 'pct': pct,
            'profit': profit, 'cost': cost, 'stop_loss': stop_loss,
            'profit_target': profit_target,
            'signal': '🟢', 'type': '持有', 'action': '正常波动',
            'tech': tech, 'rt': rt, 'market_data': market_data, 'market_overview': market_overview,
            'is_etf': True, 'target_index': target_index, 'relative': relative, 'pattern': '持有'}

def analyze_stock_signal(name, code, cost, stop_loss, profit_target, market_data, market_overview):
    """
    个股卖出信号分析（保守版）
    完整技术面 + 大盘/板块联动 + 短期趋势过滤
    
    短期趋势过滤逻辑：
    - MACD死叉/KDJ超买触发时，先看30分钟趋势和主力资金
    - 30分钟上升趋势 or 主力净流入 → 改为"继续持有观察"
    - 30分钟下降趋势 and 主力净流出 → 确认减仓信号
    """
    rt = get_realtime_price(code)
    if rt is None:
        return None
    
    tech = get_technical(code)
    price = rt['price']
    pct = rt['pct']
    profit = (price - cost) / cost * 100
    
    market_pct = None
    if market_data:
        for idx in market_data:
            if '上证' in idx['name']:
                market_pct = idx['pct']
                break
    
    # 获取短期趋势和主力资金（用于过滤技术信号）
    trend_30min = get_30min_trend(code)
    money_flow = get_main_money_flow(code)
    
    signals = []
    
    # 1. 止损
    if stop_loss and price <= stop_loss:
        return {'name': name, 'code': code, 'price': price, 'pct': pct,
                'profit': profit, 'cost': cost, 'stop_loss': stop_loss,
                'profit_target': profit_target,
                'signal': '🔴', 'type': '止损', 'action': f'立即清仓！跌破{stop_loss}',
                'tech': tech, 'rt': rt, 'market_data': market_data, 'market_overview': market_overview,
                'is_etf': False, 'pattern': '止损', 'trend_30min': trend_30min, 'money_flow': money_flow}
    
    # 2. 止盈
    if profit_target and price >= profit_target:
        signals.append(('🟠', '触及目标', f'触及目标{profit_target}，卖1/2-2/3'))
    
    # 3. 技术指标（带短期趋势过滤）
    if tech:
        # MACD死叉检查
        if tech['dif'] < tech['dea']:
            # 短期趋势过滤
            short_term_bullish = False
            filter_reason = []
            
            if trend_30min:
                if trend_30min['direction'] in ['up', 'rebound']:
                    short_term_bullish = True
                    filter_reason.append(trend_30min['desc'])
            
            if money_flow and money_flow['status'] == 'inflow':
                short_term_bullish = True
                filter_reason.append(money_flow['desc'])
            
            if short_term_bullish:
                signals.append(('🟢', 'MACD死叉但短期支撑', f'30分钟趋势向上/主力净流入，继续观察'))
            else:
                signals.append(('🟡', 'MACD死叉', '趋势转弱，减1/3'))
        
        # KDJ超买检查
        if tech['j'] > 80:
            short_term_bullish = False
            filter_reason = []
            
            if trend_30min:
                if trend_30min['direction'] in ['up', 'rebound']:
                    short_term_bullish = True
                    filter_reason.append(trend_30min['desc'])
            
            if money_flow and money_flow['status'] == 'inflow':
                short_term_bullish = True
                filter_reason.append(money_flow['desc'])
            
            if short_term_bullish:
                signals.append(('🟢', 'KDJ超买但短期不弱', f'30分钟趋势向上/主力净流入，耐心持有'))
            else:
                signals.append(('🟡', 'KDJ超买', '注意回调，减1/3'))
        
        # RSI超买
        if tech['rsi'] > 70:
            signals.append(('🟡', 'RSI超买', '超买区域，谨慎'))
        
        if profit > 10:
            signals.append(('🟡', '盈利超10%', '可考虑部分止盈'))
    
    # 4. 大盘风险
    if market_pct:
        if market_pct < -1.5:
            signals.insert(0, ('🔴', '大盘大跌', f'上证{market_pct:.2f}%，系统性风险，控制仓位'))
        elif market_pct < -0.5:
            signals.append(('🟡', '大盘偏弱', f'上证{market_pct:.2f}%，谨慎操作'))
    
    # 5. 日内走势
    day_range = rt.get('high', 0) - rt.get('low', 0)
    from_open = (price - rt.get('open', 0)) / rt.get('open', 1) * 100
    from_high = (price - rt.get('high', 0)) / rt.get('high', 1) * 100
    from_low = (price - rt.get('low', 0)) / rt.get('low', 1) * 100
    
    if from_open > 1 and from_high < -0.5:
        signals.append(('🔴', '早盘冲高回落', '主力可能出货'))
    if pct < -2:
        signals.append(('🔴', '跌幅扩大', '恐慌抛售'))
    if pct < -2 and day_range > abs(pct) * 1.5:
        signals.append(('🔴', '放量大跌', '主力出逃'))
    if from_low > 1:
        signals.append(('🟢', '创新低后反弹', '下档有支撑'))
    
    # 6. 相对强弱
    if market_pct is not None:
        relative = pct - market_pct
        if relative < -1:
            signals.append(('🔴', f'跑输大盘{relative:.1f}%', '弱于市场'))
    
    if signals:
        priority = ['止损', '目标', '大跌', '普跌', '放量', '冲高']
        for sig in signals:
            if any(kw in sig[1] for kw in priority):
                return {'name': name, 'code': code, 'price': price, 'pct': pct,
                        'profit': profit, 'cost': cost, 'stop_loss': stop_loss,
                        'profit_target': profit_target,
                        'signal': sig[0], 'type': sig[1], 'action': sig[2],
                        'tech': tech, 'rt': rt, 'market_data': market_data, 'market_overview': market_overview,
                        'is_etf': False, 'pattern': sig[1], 'trend_30min': trend_30min, 'money_flow': money_flow}
        return {'name': name, 'code': code, 'price': price, 'pct': pct,
                'profit': profit, 'cost': cost, 'stop_loss': stop_loss,
                'profit_target': profit_target,
                'signal': signals[0][0], 'type': signals[0][1], 'action': signals[0][2],
                'tech': tech, 'rt': rt, 'market_data': market_data, 'market_overview': market_overview,
                'is_etf': False, 'pattern': signals[0][1], 'trend_30min': trend_30min, 'money_flow': money_flow}
    
    return {'name': name, 'code': code, 'price': price, 'pct': pct,
            'profit': profit, 'cost': cost, 'stop_loss': stop_loss,
            'profit_target': profit_target,
            'signal': '🟢', 'type': '持有', 'action': '正常波动',
            'tech': tech, 'rt': rt, 'market_data': market_data, 'market_overview': market_overview,
            'is_etf': False, 'pattern': '持有', 'trend_30min': trend_30min, 'money_flow': money_flow}

def print_market_header(market_data, market_overview):
    """打印大盘信息头部"""
    print("=" * 80)
    print(f"📉 卖出信号检测 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 80)
    
    if market_data:
        print("\n【大盘指数】")
        for idx in market_data:
            sig = "🔴" if idx['pct'] < 0 else "🟢"
            print(f"  {idx['name']}: {idx['price']:.2f} ({sig}{idx['pct']:+.2f}%)")
    
    if market_overview:
        print(f"\n【市场概况】上涨 {market_overview['rise']} 家 | 下跌 {market_overview['fall']} 家 | 涨跌比 {market_overview['ratio']}")

def print_summary(results):
    """打印汇总表"""
    print("\n" + "=" * 80)
    print("【卖出信号汇总】")
    print("-" * 80)
    print(f"{'股票':<12s} {'类型':>4s} {'现价':>8s} {'涨跌':>7s} {'盈亏':>8s} {'走势':>10s} {'信号':>4s} {'操作建议'}")
    print("-" * 80)
    
    for r in results:
        tag = "ETF" if r['is_etf'] else "个股"
        print(f"{r['name']:<12s} {tag:>4s} {r['price']:>8.2f} {r['pct']:>+6.2f}% {r['profit']:>+7.2f}% {r['pattern']:>10s} {r['signal']:>4s} {r['action']}")

def print_detail(r):
    """打印单只持仓详细分析"""
    print(f"\n{'='*55}")
    label = "ETF" if r['is_etf'] else "个股"
    print(f"📊 {r['name']} ({r['code']}) [{label}]")
    print(f"{'='*55}")
    
    # 大盘对比
    if r.get('market_data'):
        for idx in r['market_data']:
            if '上证' in idx['name']:
                rel = r['pct'] - idx['pct']
                sig = "🟢" if rel > 0 else "🔴"
                print(f"\n【大盘】上证 {idx['pct']:+.2f}% → {sig}相对 {rel:+.2f}%")
                break
    
    # ETF特有：跟踪指数信息
    if r['is_etf'] and r.get('target_index'):
        ti = r['target_index']
        print(f"【跟踪指数】{ti['name']} {ti['pct']:+.2f}%")
        itech = r.get('index_tech')
        if itech:
            print(f"  均线: {get_trend_signal(itech)}")
            macd_s = "🟢金叉" if itech['dif'] > itech['dea'] else "🔴死叉"
            kdj_s = "超买(J={:.0f})".format(itech['j']) if itech['j'] > 80 else "超卖(J={:.0f})".format(itech['j']) if itech['j'] < 20 else "中性"
            print(f"  MACD: {macd_s} | KDJ: {kdj_s} | RSI: {itech['rsi']:.0f}")
    
    print(f"\n【价格】现价 {r['price']:.2f} ({r['pct']:+.2f}%) | 成本 {r['cost']:.2f} | 盈亏 {r['profit']:+.2f}%")
    
    sl = f"{r['stop_loss']:.2f}" if r['stop_loss'] else "未设"
    pt = f"{r['profit_target']:.2f}" if r['profit_target'] else "未设"
    print(f"【阈值】止损 {sl} | 目标 {pt}")
    
    rt = r.get('rt')
    if rt:
        print(f"\n【当日走势】开盘 {rt['open']:.2f} | 最高 {rt['high']:.2f} | 最低 {rt['low']:.2f}")
        day_r = rt['high'] - rt['low']
        print(f"  日内波动 {day_r:.2f} ({day_r/rt['prev_close']*100:+.2f}%)")
    
    # 个股新增：短期趋势
    if not r['is_etf']:
        trend = r.get('trend_30min')
        if trend:
            print(f"\n【短期趋势】{trend['desc']}")
        money = r.get('money_flow')
        if money:
            sig = "🟢" if money['status'] == 'inflow' else "🔴"
            print(f"【主力资金】{sig}{money['desc']}")
    
    tech = r.get('tech')
    if tech:
        print(f"\n【技术指标】")
        print(f"  MA5 {tech['ma5']:.2f} | MA10 {tech['ma10']:.2f} | MA20 {tech['ma20']:.2f}")
        if tech.get('ma60'):
            print(f"  MA60 {tech['ma60']:.2f}", end="")
        print(f"  → {get_trend_signal(tech)}")
        
        macd_s = "🟢金叉" if tech['dif'] > tech['dea'] else "🔴死叉"
        print(f"  MACD柱 {tech['macd_bar']:+.2f} ({macd_s}) | KDJ J={tech['j']:.0f} | RSI={tech['rsi']:.0f}")
        print(f"  布林带: {get_bbr_position(r['price'], tech['bbr_upper'], tech['bbr_mid'], tech['bbr_lower'])}")
    
    print(f"\n【信号】 {r['signal']} {r['type']}: {r['action']}")

def main():
    print("=" * 80)
    print(f"📉 卖出信号检测 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 80)

    print("\n⏳ 获取市场数据...")
    market_data = get_market_index()
    market_overview = get_market_overview()

    if market_data:
        print_market_header(market_data, market_overview)
    else:
        print("⚠️ 大盘数据获取失败，继续检测持仓...")

    holdings = load_holdings()
    print(f"\n检测 {len(holdings)} 只持仓（自动识别ETF/个股）...\n")

    results = []
    for h in holdings:
        if is_etf(h['name']):
            result = analyze_etf_signal(h['name'], h['code'], h['cost'],
                                        h['stop_loss'], h['profit_target'],
                                        market_data, market_overview)
        else:
            result = analyze_stock_signal(h['name'], h['code'], h['cost'],
                                           h['stop_loss'], h['profit_target'],
                                           market_data, market_overview)
        if result:
            results.append(result)

    print_summary(results)

    print("\n" + "=" * 80)
    print("【详细分析】")
    print("=" * 80)

    for r in results:
        print_detail(r)

    print("\n" + "=" * 80)
    print("⚠️ 仅供参考，投资需谨慎")
    print("=" * 80)

if __name__ == "__main__":
    main()
