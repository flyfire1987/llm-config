#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股板块复盘脚本 - 综合分析（含5分钟趋势）
用法: python3 sector_analysis.py
生成内容包括：大盘指数、5分钟趋势分析、行业板块、主力资金、次日预测
"""

import subprocess
import re
import json
import requests
from datetime import datetime

# ============================================
# 数据获取函数
# ============================================

def get_index_realtime(code="sh000001"):
    """获取指数实时行情（腾讯财经）"""
    try:
        url = f"https://qt.gtimg.cn/q={code}"
        result = subprocess.run(["curl", "-s", url], capture_output=True, timeout=10)
        try:
            data = result.stdout.decode('gbk', errors='ignore').strip()
        except:
            data = result.stdout.decode('utf-8', errors='ignore').strip()
        
        if not data or "v_" not in data:
            return None
        
        match = re.search(r'"([^"]+)"', data)
        if not match:
            return None
        
        fields = match.group(1).split("~")
        if len(fields) < 45:
            return None
        
        raw_33 = fields[33] if fields[33] else "0"
        if "/" in raw_33:
            parts_33 = raw_33.split("/")
            current_price_field = parts_33[0]
        else:
            current_price_field = raw_33

        current_price = float(current_price_field) if current_price_field not in ["", None, "0"] else 0
        open_val = float(fields[41]) if fields[41] and fields[41] not in ["", None] else current_price
        high_val = float(fields[41]) if fields[41] and fields[41] not in ["", None] else current_price
        low_val = float(fields[42]) if fields[42] and fields[42] not in ["", None] else current_price

        return {
            "name": fields[1],
            "code": fields[2],
            "price": current_price,
            "change": float(fields[31]) if fields[31] else 0,
            "change_percent": float(fields[32]) if fields[32] else 0,
            "volume": int(fields[6]) if fields[6] else 0,
            "amount": float(fields[37]) if len(fields) > 37 and fields[37] else 0,
            "open": open_val,
            "high": high_val,
            "low": low_val,
            "close_yesterday": float(fields[4]) if fields[4] else 0,
        }
    except Exception as e:
        return None


def get_multiple_index(codes):
    """获取多个指数"""
    result = {}
    for code in codes:
        data = get_index_realtime(code)
        if data:
            result[code] = data
    return result


def get_5min_data_akshare(code="sh000001"):
    """使用akshare获取今日5分钟K线数据"""
    try:
        import akshare as ak
        
        df = ak.stock_zh_a_minute(symbol=code, period='5')
        
        if df is None or len(df) < 10:
            return None
        
        today = datetime.now().strftime("%Y-%m-%d")
        today_df = df[df['day'].astype(str).str.startswith(today)]
        
        if len(today_df) < 10:
            if len(df) >= 10:
                today_df = df.tail(100)
        
        if len(today_df) < 10:
            return None
        
        klines = []
        for _, row in today_df.iterrows():
            klines.append({
                "day": str(row['day']),
                "open": float(row['open']),
                "close": float(row['close']),
                "high": float(row['high']),
                "low": float(row['low']),
                "volume": float(row['volume']),
            })
        
        return klines
    except Exception as e:
        return None


def get_industry_sector():
    """获取行业板块涨跌幅（新浪）"""
    try:
        url = 'https://vip.stock.finance.sina.com.cn/q/view/newFLJK.php?type=1&sort=涨跌幅&asc=0&page=1&num=50&m_id=&m_name=&classify=1'
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        match = re.search(r'var S_Finance_bankuai_ = (.+)', r.text)
        if not match:
            return [], []
        data = json.loads(match.group(1))
        items = []
        for k, v in data.items():
            parts = v.split(',')
            if len(parts) > 8:
                name = parts[1]
                pct = float(parts[4]) if parts[4] else 0
                amount = int(parts[6]) if parts[6] else 0
                leader = parts[8]
                items.append((pct, name, amount, leader))
        items.sort(key=lambda x: x[0], reverse=True)
        return items[:20], items[-20:][::-1]
    except Exception as e:
        return [], []


def get_sector_fund_flow_akshare():
    """使用akshare获取行业资金流向"""
    try:
        import akshare as ak
        
        df = ak.stock_fund_flow_industry()
        
        if df is None or len(df) == 0:
            return []
        
        columns = df.columns.tolist()
        flow_col = None
        for col in ['净额', '净流入', '资金净额']:
            if col in columns:
                flow_col = col
                break
        
        if flow_col is None:
            for col in ['流入资金', '流入']:
                if col in columns:
                    inflow_col = col
                    outflow_col = None
                    for col2 in ['流出资金', '流出']:
                        if col2 in columns:
                            outflow_col = col2
                            break
                    if outflow_col:
                        df['净额'] = df[inflow_col] - df.get(outflow_col, 0)
                        flow_col = '净额'
                        break
        
        sectors = []
        for _, row in df.head(20).iterrows():
            name = str(row.get('行业', ''))
            if not name or len(name) > 20:
                continue
            
            net_flow = 0
            if flow_col and flow_col in df.columns:
                val = row.get(flow_col, 0)
                if isinstance(val, (int, float)):
                    net_flow = val
            
            sectors.append({
                'name': name,
                'main_flow': net_flow * 10000 if abs(net_flow) < 100 else net_flow,
                'main_percent': row.get('行业-涨跌幅', 0),
            })
        
        return sectors
    except Exception as e:
        return []


# ============================================
# 趋势分析核心
# ============================================

def analyze_5min_trend(klines, open_price=None, yesterday_close=None):
    """分析5分钟趋势"""
    if not klines or len(klines) < 10:
        return None
    
    first_5 = klines[:5]
    last_5 = klines[-5:]
    
    open_5min = sum(k["open"] for k in first_5) / len(first_5)
    close_5min = sum(k["close"] for k in last_5) / len(last_5)
    high = max(k["high"] for k in klines)
    low = min(k["low"] for k in klines)
    
    if open_5min > 0:
        change_pct = (close_5min - open_5min) / open_5min * 100
    else:
        change_pct = 0
    
    if high != low:
        position_ratio = (close_5min - low) / (high - low)
    else:
        position_ratio = 0.5
    
    ref_price = yesterday_close if yesterday_close else open_price
    gap_open = open_5min - ref_price if ref_price else 0
    gap_ratio = gap_open / ref_price * 100 if ref_price else 0
    
    trend_type = "未知"
    trend_score = 50
    trend_desc = ""
    
    last_trend = 0
    for i in range(1, min(5, len(last_5))):
        last_trend += last_5[i]["close"] - last_5[i-1]["close"]
    
    if gap_ratio < -0.5:
        if change_pct < -0.3:
            trend_type = "低开低走"
            trend_score = 20
            trend_desc = "做空动能较强"
        elif change_pct > 0.5:
            trend_type = "低开高走"
            trend_score = 70
            trend_desc = "资金逢低买入意愿强"
        else:
            trend_type = "低开震荡"
            trend_score = 45
            trend_desc = "多空平衡"
    elif gap_ratio > 0.5:
        if change_pct > 0.5:
            trend_type = "高开高走"
            trend_score = 80
            trend_desc = "做多情绪高涨"
        elif change_pct < -0.3:
            trend_type = "高开低走"
            trend_score = 30
            trend_desc = "注意高位风险"
        else:
            trend_type = "高开震荡"
            trend_score = 55
            trend_desc = "观望情绪较浓"
    else:
        if position_ratio > 0.7:
            if last_trend > 0:
                trend_type = "尾盘拉升"
                trend_score = 75
                trend_desc = "强势拉升"
            else:
                trend_type = "高位震荡"
                trend_score = 60
                trend_desc = "多方略占优"
        elif position_ratio < 0.3:
            if last_trend < 0:
                trend_type = "尾盘砸盘"
                trend_score = 25
                trend_desc = "尾盘再度杀跌"
            else:
                trend_type = "低位震荡"
                trend_score = 40
                trend_desc = "空方压力仍在"
        else:
            trend_type = "横盘整理"
            trend_score = 50
            trend_desc = "等待突破"
    
    tail_action = ""
    if last_trend > 0.1:
        tail_action = "📈 尾盘做多"
        trend_score = min(100, trend_score + 10)
    elif last_trend < -0.1:
        tail_action = "📉 尾盘做空"
        trend_score = max(0, trend_score - 10)
    else:
        tail_action = "➡️ 尾盘平稳"
    
    vol_first_10 = sum(k.get("volume", 0) for k in klines[:10])
    vol_last_10 = sum(k.get("volume", 0) for k in klines[-10:])
    vol_ratio = vol_last_10 / vol_first_10 if vol_first_10 > 0 else 1
    
    if vol_ratio > 1.5:
        vol_analysis = "成交量放大"
    elif vol_ratio < 0.7:
        vol_analysis = "成交量萎缩"
    else:
        vol_analysis = "成交量持平"
    
    return {
        "trend_type": trend_type,
        "trend_score": trend_score,
        "trend_desc": trend_desc,
        "tail_action": tail_action,
        "position_ratio": position_ratio,
        "gap_ratio": gap_ratio,
        "change_pct": change_pct,
        "vol_analysis": vol_analysis,
        "open_5min": open_5min,
        "close_5min": close_5min,
        "high": high,
        "low": low,
    }


def analyze_from_realtime(realtime):
    """基于实时数据估算趋势"""
    if not realtime:
        return None
    
    price = realtime.get("price", 0)
    open_price = realtime.get("open", 0)
    high = realtime.get("high", 0)
    low = realtime.get("low", 0)
    yesterday_close = realtime.get("close_yesterday", 0)
    change_pct = realtime.get("change_percent", 0)
    
    if not all([price, open_price, high, low]):
        return None
    
    gap_ratio = (open_price - yesterday_close) / yesterday_close * 100 if yesterday_close else 0
    position_ratio = (price - low) / (high - low) if high != low else 0.5
    
    if gap_ratio < -0.5:
        if change_pct < -0.3:
            trend_type = "低开低走(估)"
        elif change_pct > 0.3:
            trend_type = "低开高走(估)"
        else:
            trend_type = "低开震荡(估)"
    elif gap_ratio > 0.5:
        if change_pct > 0.3:
            trend_type = "高开高走(估)"
        elif change_pct < -0.3:
            trend_type = "高开低走(估)"
        else:
            trend_type = "高开震荡(估)"
    else:
        if position_ratio > 0.7:
            trend_type = "高位运行(估)"
        elif position_ratio < 0.3:
            trend_type = "低位运行(估)"
        else:
            trend_type = "震荡整理(估)"
    
    return {
        "trend_type": trend_type,
        "trend_score": 50,
        "trend_desc": "⚠️ 基于有限数据估算",
        "tail_action": "➡️ 暂无尾盘数据",
        "position_ratio": position_ratio,
        "gap_ratio": gap_ratio,
        "change_pct": change_pct,
        "vol_analysis": "⚠️ 数据有限",
        "open_5min": open_price,
        "close_5min": price,
        "high": high,
        "low": low,
        "estimated": True,
    }


def combine_prediction(trend, sectors):
    """综合评分与次日预测"""
    if not trend:
        return None
    
    trend_score = trend["trend_score"]
    
    if sectors and len(sectors) > 0:
        inflow_count = sum(1 for s in sectors if s["main_flow"] > 0)
        total_count = len(sectors)
        fund_score = (inflow_count / total_count) * 100 if total_count > 0 else 50
    else:
        fund_score = 50
    
    if trend["change_pct"] > 0 and fund_score > 60:
        emotion_score = min(100, fund_score + 10)
    elif trend["change_pct"] < 0 and fund_score < 40:
        emotion_score = max(0, fund_score - 10)
    elif abs(trend["change_pct"]) < 0.3:
        emotion_score = 50
    else:
        emotion_score = max(0, min(100, 50 + trend["change_pct"] * 5))
    
    composite = trend_score * 0.4 + fund_score * 0.4 + emotion_score * 0.2
    
    if composite >= 75:
        prediction = "⬆️ 明日看多"
        prediction_desc = "走势强势，叠加资金净流入"
    elif composite >= 60:
        prediction = "↗️ 明日谨慎看多"
        prediction_desc = "表现尚可，需观察消息面"
    elif composite >= 45:
        prediction = "➡️ 明日震荡"
        prediction_desc = "多空均衡，维持震荡格局"
    elif composite >= 30:
        prediction = "↘️ 明日谨慎看空"
        prediction_desc = "走势偏弱，可能调整"
    else:
        prediction = "⬇️ 明日看空"
        prediction_desc = "走势极弱，继续回调"
    
    return {
        "trend_score": trend_score,
        "fund_score": fund_score,
        "emotion_score": emotion_score,
        "composite_score": composite,
        "prediction": prediction,
        "prediction_desc": prediction_desc,
    }


# ============================================
# 输出格式化
# ============================================

def format_report(index_data, trends, sectors, predictions):
    """格式化输出复盘报告"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    print(f"\n{'='*75}")
    print(f"📊 A股板块复盘报告 ({now})")
    print(f"{'='*75}")
    
    # 1. 大盘指数
    print(f"\n【一、大盘指数】")
    print(f"{'指数名称':<12}{'现价':>10}{'涨跌幅':>10}{'趋势类型':<14}{'趋势评分':>10}{'尾盘行为':<12}")
    print("-" * 75)
    
    INDEX_NAMES = {
        "sh000001": "上证指数",
        "sz399001": "深证成指",
        "sz399006": "创业板指",
        "sh000688": "科创50",
        "sh000300": "沪深300",
    }
    
    for code, data in index_data.items():
        name = INDEX_NAMES.get(code, data.get('name', code))
        pct = data.get('change_percent', 0)
        trend = trends.get(code, {})
        trend_type = trend.get('trend_type', 'N/A')
        trend_score = trend.get('trend_score', '-')
        tail = trend.get('tail_action', '-')
        print(f"{name:<12}{data['price']:>10.2f}{pct:>+9.2f}% {trend_type:<12}{str(trend_score):>8}{tail:<12}")
    
    # 2. 5分钟趋势详情
    print(f"\n【二、5分钟趋势分析】")
    for code, data in index_data.items():
        name = INDEX_NAMES.get(code, data.get('name', code))
        trend = trends.get(code, {})
        if not trend:
            continue
        
        estimated_tag = " [估算]" if trend.get("estimated") else ""
        print(f"\n  ▶ {name}{estimated_tag}")
        print(f"    走势类型: {trend['trend_type']} | 评分: {trend['trend_score']}/100")
        print(f"    日内涨跌: {trend['change_pct']:+.2f}% | 日内位置: {'高位' if trend['position_ratio'] > 0.7 else '低位' if trend['position_ratio'] < 0.3 else '中部'} ({trend['position_ratio']*100:.0f}%)")
        print(f"    尾盘行为: {trend['tail_action']} | 成交量: {trend['vol_analysis']}")
        if not trend.get("estimated"):
            print(f"    开盘价: {trend['open_5min']:.2f} | 收盘价: {trend['close_5min']:.2f} | 最高: {trend['high']:.2f} | 最低: {trend['low']:.2f}")
    
    # 3. 行业板块
    print(f"\n【三、行业板块涨跌幅】")
    if sectors and len(sectors) > 0:
        top_sectors = sorted([s for s in sectors if s["main_flow"] > 0], key=lambda x: x["main_percent"], reverse=True)[:5]
        bot_sectors = sorted([s for s in sectors if s["main_flow"] <= 0], key=lambda x: x["main_percent"])[:5]
        
        print(f"\n  📈 涨幅前5:")
        for i, s in enumerate(top_sectors, 1):
            print(f"     {i}. {s['name']}: {s['main_percent']:+.2f}%")
        
        print(f"\n  📉 跌幅前5:")
        for i, s in enumerate(bot_sectors, 1):
            print(f"     {i}. {s['name']}: {s['main_percent']:+.2f}%")
    else:
        print("  暂无数据")
    
    # 4. 主力资金
    print(f"\n【四、主力资金流向】")
    if sectors and len(sectors) > 0:
        inflow_sectors = [s for s in sectors if s["main_flow"] > 0]
        outflow_sectors = [s for s in sectors if s["main_flow"] <= 0]
        
        print(f"  流入行业: {len(inflow_sectors)}个 | 流出行业: {len(outflow_sectors)}个")
        
        if inflow_sectors[:3]:
            print(f"\n  📈 资金流入TOP3:")
            for s in sorted(inflow_sectors, key=lambda x: x["main_flow"], reverse=True)[:3]:
                flow_yi = s["main_flow"] / 1e8
                print(f"     {s['name']}: +{flow_yi:.2f}亿元")
        
        if outflow_sectors[:3]:
            print(f"\n  📉 资金流出TOP3:")
            for s in sorted(outflow_sectors, key=lambda x: x["main_flow"])[:3]:
                flow_yi = abs(s["main_flow"]) / 1e8
                print(f"     {s['name']}: -{flow_yi:.2f}亿元")
    else:
        print("  暂无数据")
    
    # 5. 综合预测
    main_index = index_data.get("sh000001", {})
    main_trend = trends.get("sh000001", {})
    main_pred = predictions.get("sh000001", {})
    
    if main_pred:
        print(f"\n【五、综合分析与次日预测】")
        print(f"  ┌{'─'*60}┐")
        print(f"  │ 上证指数综合评分: {main_pred['composite_score']:.0f}/100{' '*32}│")
        print(f"  │   - 趋势得分: {main_pred['trend_score']:.0f}/100{' '*42}│")
        print(f"  │   - 资金得分: {main_pred['fund_score']:.0f}/100{' '*42}│")
        print(f"  │   - 情绪得分: {main_pred['emotion_score']:.0f}/100{' '*42}│")
        print(f"  │{'─'*60}│")
        print(f"  │ 明日预测: {main_pred['prediction']} {' '*46}│")
        print(f"  │ 分析: {main_pred['prediction_desc']:<46}│")
        print(f"  └{'─'*60}┘")
        
        score = main_pred['composite_score']
        if score >= 70:
            print(f"\n  ✅ 操作建议：积极布局，适度加仓")
        elif score >= 55:
            print(f"\n  ⚠️ 操作建议：谨慎做多，控制仓位")
        elif score >= 45:
            print(f"\n  ⏸️ 操作建议：观望为主，不宜追涨")
        else:
            print(f"\n  ❌ 操作建议：控制风险，减少操作")
    else:
        print(f"\n【五、综合分析】数据不足")
    
    print(f"\n{'='*75}")
    print("⚠️ 风险提示: 以上分析仅供参考，不构成投资建议")
    print(f"{'='*75}\n")


# ============================================
# 主函数
# ============================================

def main():
    INDEX_CODES = ["sh000001", "sz399001", "sz399006", "sh000688", "sh000300"]
    
    print("🔍 正在获取A股复盘数据...")
    
    # 1. 获取大盘指数
    print("  📊 获取大盘指数...")
    index_data = get_multiple_index(INDEX_CODES)
    
    # 2. 获取5分钟趋势
    print("  📈 获取5分钟趋势数据...")
    trends = {}
    for code in INDEX_CODES:
        klines = get_5min_data_akshare(code)
        if klines and len(klines) >= 10:
            realtime = index_data.get(code, {})
            open_price = realtime.get("open", 0) if realtime else None
            yesterday_close = realtime.get("close_yesterday", 0) if realtime else None
            trends[code] = analyze_5min_trend(klines, open_price, yesterday_close)
        elif index_data.get(code):
            trends[code] = analyze_from_realtime(index_data[code])
    
    # 3. 获取行业板块
    print("  📋 获取行业板块数据...")
    top_sectors, bot_sectors = get_industry_sector()
    
    # 4. 获取主力资金
    print("  💰 获取主力资金流向...")
    sectors = get_sector_fund_flow_akshare()
    
    # 5. 综合预测
    predictions = {}
    for code in INDEX_CODES:
        trend = trends.get(code)
        predictions[code] = combine_prediction(trend, sectors)
    
    # 6. 输出报告
    format_report(index_data, trends, sectors, predictions)


if __name__ == "__main__":
    main()