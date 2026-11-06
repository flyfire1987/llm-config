#!/usr/bin/env python3
"""
afternoon_news_report.py - 财经午报（基于财经早报改造）
================================================================

【与早报的区别】
- 数据源：同早报
- 过滤：只看今天的新闻（基于 URL 日期 / 文本日期）
- 额外内容：
  * 大盘指数实时表现
  * 行业板块涨跌幅 TOP10
  * 主力资金净流入/流出 TOP5
  * 午后展望（基于热点+资金判断）
- 触发时间：工作日 14:35

【复用】所有评分/去重/股票关联函数从 morning_news_report 导入
"""

import sys
import os
import re
import time
import warnings
from datetime import datetime
from typing import List, Dict, Optional

warnings.filterwarnings('ignore')

sys.path.insert(0, '/root/.openclaw/workspace')
sys.path.insert(0, '/root/.openclaw/workspace/scripts')

# 复用早报模块
import morning_news_report as morning
from morning_news_report import (
    NEWS_TO_STOCKS, log, safe_get, extract_news_list,
    classify_news_type, detect_sentiment, match_sectors,
    score_news, dedup_news, match_stocks,
    get_stock_quote_safe, calc_7d_pct, get_main_fund_flow,
    format_stock_line,
)

# ==========================================
# 1. 今日新闻过滤
# ==========================================

def is_today_news(item: Dict) -> bool:
    """判断是否为今天的新闻（基于 URL 日期）

    午报逻辑：只看今天发布的新闻（URL含今天日期）。
    昨天/前天的隔夜新闻不计入午报热点。
    """
    today = datetime.now()
    today_str = today.strftime('%Y%m%d')  # 20260604
    url = item.get('url', '')

    # 优先看 URL：必须含今天日期
    if today_str in url:
        return True
    # URL 中明确包含昨天/前天的日期：排除
    for days_ago in range(1, 4):
        past = today.replace(day=today.day - days_ago) if today.day > days_ago else today
        if past.strftime('%Y%m%d') in url:
            return False
    # URL 中没有明确日期（部分站点 URL 不含日期）：看文本
    text = item.get('title', '') + item.get('raw', '')
    cn_date_patterns = [
        today.strftime('%m月%d日'),  # 06月04日
        today.strftime('%m-%d'),       # 06-04
        '今日', '今早', '盘中', '午后', '上午',
    ]
    for pat in cn_date_patterns:
        if pat in text:
            return True
    # 有明确昨日前缀：排除
    yesterday = today.replace(day=today.day - 1) if today.day > 1 else today
    if yesterday.strftime('%m月%d日') in text or '昨日' in text:
        return False
    # 兜底：没有明确日期信息、保留为"今日"
    return True

# ==========================================
# 2. 大盘指数
# ==========================================

def fetch_market_indices() -> List[Dict]:
    """获取主要大盘指数实时表现（腾讯批量接口）"""
    indices = [
        ('sh000001', '上证指数'),
        ('sz399001', '深证成指'),
        ('sz399006', '创业板指'),
        ('sh000688', '科创50'),
        ('sh000016', '上证50'),
        ('sz399905', '中证500'),
    ]
    codes = [c for c, _ in indices]
    name_map = {c: n for c, n in indices}
    results = []
    try:
        from stock_tencent import get_stocks_quote
        df = get_stocks_quote(codes)
        if df is not None and len(df) > 0:
            for _, row in df.iterrows():
                code = str(row['代码']).zfill(6)
                # 转换代码格式
                if code.startswith(('0', '3', '1')):
                    qcode = f'sz{code}'
                else:
                    qcode = f'sh{code}'
                name = name_map.get(qcode, row['名称'])
                results.append({
                    'name': name,
                    'code': qcode,
                    'price': float(row['当前价']),
                    'pct': float(row['涨跌幅'].rstrip('%')) if isinstance(row['涨跌幅'], str) else float(row['涨跌幅']),
                })
    except Exception as e:
        log(f'获取指数失败: {e}', 'WARN')
    return results

# ==========================================
# 3. 行业板块涨跌幅
# ==========================================

def fetch_sector_performance() -> Dict:
    """获取行业板块涨跌幅 TOP10 涨/跌（akshare + 东方财富HTML备选）"""
    gainers = []
    losers = []
    # 试 akshare
    try:
        import akshare as ak
        df = None
        for fn_name, args in [
            ('stock_board_industry_spot_em', {'symbol': '行业板块'}),
            ('stock_board_industry_name_em', {}),
        ]:
            if hasattr(ak, fn_name):
                try:
                    df = getattr(ak, fn_name)(**args)
                    if df is not None and len(df) > 0:
                        break
                except Exception as e:
                    log(f'akshare {fn_name} 失败: {e}', 'WARN')
        if df is not None and len(df) > 0:
            df_sorted = df.sort_values('涨跌幅', ascending=False)
            for _, row in df_sorted.head(10).iterrows():
                gainers.append({
                    'name': row.get('板块名称', row.get('名称', '')),
                    'code': row.get('板块代码', ''),
                    'pct': float(row.get('涨跌幅', 0)),
                })
            for _, row in df_sorted.tail(10).iterrows():
                losers.append({
                    'name': row.get('板块名称', row.get('名称', '')),
                    'code': row.get('板块代码', ''),
                    'pct': float(row.get('涨跌幅', 0)),
                })
    except Exception as e:
        log(f'akshare板块获取失败: {e}', 'WARN')

    # 备选：东方财富HTML
    if not gainers:
        try:
            import requests
            import re
            r = requests.get(
                'https://data.eastmoney.com/bkzj/hy.html',
                headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.eastmoney.com/'},
                timeout=8
            )
            r.encoding = r.apparent_encoding or 'utf-8'
            # 尝试从嵌入数据中提取
            pattern = r'\"f14\":\"([^\"]+)\",\"f3\":(-?[\d.]+)'
            matches = re.findall(pattern, r.text)
            sectors = [(name, float(pct)) for name, pct in matches[:50]]
            sectors_sorted = sorted(sectors, key=lambda x: x[1], reverse=True)
            for name, pct in sectors_sorted[:10]:
                gainers.append({'name': name, 'code': '', 'pct': pct})
            for name, pct in sectors_sorted[-10:]:
                losers.append({'name': name, 'code': '', 'pct': pct})
        except Exception as e:
            log(f'HTML备选板块也失败: {e}', 'WARN')

    return {'gainers': gainers, 'losers': losers}

# ==========================================
# 4. 主力资金流（板块级）
# ==========================================

def fetch_sector_fund_flow() -> Dict:
    """板块主力资金净流入/流出 TOP5（akshare + 东方财富重试）"""
    inflow = []
    outflow = []
    # 试 akshare
    try:
        import akshare as ak
        for fn_name, args in [
            ('stock_fund_flow_industry', {'symbol': '今日'}),
            ('stock_sector_fund_flow_rank', {'indicator': '今日', 'sector_type': '行业板块'}),
        ]:
            if hasattr(ak, fn_name):
                df = getattr(ak, fn_name)(**args)
                if df is not None and len(df) > 0:
                    for _, row in df.iterrows():
                        try:
                            main_inflow = float(str(row.get('主力净流入-净额', row.get('净额', 0))).replace(',', ''))
                        except (ValueError, TypeError):
                            main_inflow = 0
                        main_inflow_yi = main_inflow / 1e8
                        sector = {
                            'name': row.get('名称', row.get('板块名称', '')),
                            'code': row.get('代码', ''),
                            'main_inflow': main_inflow_yi,
                        }
                        inflow.append(sector)
                    break
    except Exception as e:
        log(f'akshare资金流失败: {e}', 'WARN')

    # 备选：东方财富HTML（简单解析）
    if not inflow:
        try:
            import requests
            r = requests.get(
                'https://data.eastmoney.com/bkzj/hy.html',
                headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.eastmoney.com/'},
                timeout=8
            )
            r.encoding = r.apparent_encoding or 'utf-8'
            import re
            # 尝试从嵌入的JSON提取（不同页面格式不同）
            pattern = r'\"f14\":\"([^\"]+)\",\"f3\":\"(-?[\d.]+)\",\"f62\":\"(-?[\d.]+)\"'
            matches = re.findall(pattern, r.text)
            for name, pct, inflow_val in matches[:30]:
                inflow.append({
                    'name': name,
                    'code': '',
                    'main_inflow': float(inflow_val) / 1e8,
                })
        except Exception as e:
            log(f'HTML备选资金流也失败: {e}', 'WARN')

    if inflow:
        outflow = sorted(inflow, key=lambda x: x['main_inflow'])[:5]
        inflow = sorted(inflow, key=lambda x: x['main_inflow'], reverse=True)[:5]

    return {'inflow': inflow, 'outflow': outflow}

# ==========================================
# 5. 抓取今日新闻（基于早报的数据源）
# ==========================================

def fetch_today_news() -> List[Dict]:
    """抓取所有新闻并过滤为今天（先算分后过滤）"""
    log('开始抓取今日新闻...')
    all_news = morning.fetch_all_news()
    log(f'原始 {len(all_news)} 条，开始计算评分+过滤...')
    # 先 rank_news（计算 score / 关联股票 / 类型 / 情绪）
    ranked = morning.rank_news(all_news)
    # 过滤为今日
    today_news = [n for n in ranked if is_today_news(n)]
    log(f'今日新闻: {len(today_news)} 条')
    return today_news

# ==========================================
# 6. 午后展望（基于数据和关键词）
# ==========================================

def generate_outlook(today_news: List[Dict], sectors: Dict, fund_flow: Dict) -> str:
    """生成午后展望"""
    lines = []

    # 资金面判断
    if fund_flow.get('inflow') and fund_flow['inflow']:
        top_inflow = fund_flow['inflow'][0]['name']
    else:
        top_inflow = '未知'
    if fund_flow.get('outflow') and fund_flow['outflow']:
        top_outflow = fund_flow['outflow'][0]['name']
    else:
        top_outflow = '未知'

    # 板块面判断
    if sectors.get('gainers') and sectors['gainers']:
        top_sector = sectors['gainers'][0]
        sector_msg = f'强势板块：{top_sector["name"]}({top_sector["pct"]:+.2f}%)'
    else:
        sector_msg = '板块数据待获取'

    # 新闻情绪统计
    sentiments = {'利好': 0, '利空': 0, '中性': 0}
    for n in today_news:
        s = n.get('sentiment', '中性')
        sentiments[s] = sentiments.get(s, 0) + 1

    pos = sentiments.get('利好', 0)
    neg = sentiments.get('利空', 0)
    if pos > neg:
        bias = '偏多'
        emoji = '🟢'
    elif neg > pos:
        bias = '偏空'
        emoji = '🔴'
    else:
        bias = '中性'
        emoji = '⚪'

    lines.append(f'• {sector_msg}')
    lines.append(f'• 资金主线：{top_inflow} 流入 / {top_outflow} 流出')
    lines.append(f'• 消息面情绪：{emoji}{bias}（利好{pos} / 利空{neg}）')
    lines.append('')

    # 操作建议
    if bias == '偏多':
        lines.append('• 午后策略：可关注资金流入板块龙头，注意高位股风险')
    elif bias == '偏空':
        lines.append('• 午后策略：谨慎追高，关注防御性板块（黄金/公用事业）')
    else:
        lines.append('• 午后策略：控制仓位，等待方向明确')

    return '\n'.join(lines)

# ==========================================
# 7. 报告生成
# ==========================================

def generate_afternoon_report() -> str:
    """生成完整午报"""
    today = datetime.now()
    weekday_cn = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][today.weekday()]
    date_str = today.strftime('%Y-%m-%d')

    lines = []
    lines.append(f'📊 财经午报 · {date_str} {weekday_cn}')
    lines.append(f'（数据源: 财联社 + 东方财富 + 证券时报 + 21财经 + 第一财经 + 新浪财经 | 最多10条）')
    lines.append('')

    # ====== 一、大盘指数 ======
    lines.append('【一、大盘指数】')
    indices = fetch_market_indices()
    if indices:
        lines.append('| 指数 | 点位 | 涨跌幅 |')
        lines.append('|------|------|--------|')
        for idx in indices:
            emoji = '🟢' if idx['pct'] >= 0 else '🔴'
            lines.append(f'| {idx["name"]} | {idx["price"]:.2f} | {emoji}{idx["pct"]:+.2f}% |')
    else:
        lines.append('⚠️ 指数数据获取失败')
    lines.append('')

    # ====== 二、今日热点新闻 ======
    lines.append('【二、今日热点】')
    today_news = fetch_today_news()
    # 排序 + 取 top 10
    ranked = sorted(today_news, key=lambda x: x.get('score', 0), reverse=True)
    top_news = [n for n in ranked if n.get('score', 0) >= 1.5 and n.get('stocks')][:10]

    if top_news:
        for i, n in enumerate(top_news, 1):
            lines.append(f'{i}. {n["title"]}')
            tags = []
            if n.get('types'):
                tags.append('🏷' + '/'.join(n['types'][:2]))
            if n.get('sentiment') and n['sentiment'] != '中性':
                emoji = '🟢' if n['sentiment'] == '利好' else '🔴'
                tags.append(emoji + n['sentiment'])
            if n.get('sectors'):
                tags.append('📊' + '/'.join(n['sectors'][:2]))
            if tags:
                lines.append('   ' + ' | '.join(tags))
            src_tag = n['source'] + ('(多源)' if n.get('multi_source') else '')
            lines.append(f'   来源：{src_tag} | 重要性: {n["score"]:.1f}/10')
            stock_lines = [format_stock_line(name, code) for name, code in n.get('stocks', [])]
            if stock_lines:
                lines.append(f'   关联A股：{" / ".join(stock_lines)}')
            lines.append('')
    else:
        lines.append('⚠️ 今日暂无符合条件的热点新闻')
        lines.append('')

    # ====== 三、板块表现 ======
    lines.append('【三、板块表现 TOP10】')
    sectors = fetch_sector_performance()
    if sectors.get('gainers'):
        lines.append('**涨幅前5**：')
        for s in sectors['gainers'][:5]:
            lines.append(f'  🟢 {s["name"]} {s["pct"]:+.2f}%')
        lines.append('')
        lines.append('**跌幅前5**：')
        for s in sectors.get('losers', [])[:5]:
            lines.append(f'  🔴 {s["name"]} {s["pct"]:+.2f}%')
    else:
        lines.append('⚠️ 板块数据获取失败')
    lines.append('')

    # ====== 四、资金流向 ======
    lines.append('【四、主力资金流向】')
    fund_flow = fetch_sector_fund_flow()
    if fund_flow.get('inflow'):
        lines.append('**净流入 TOP5**：')
        for s in fund_flow['inflow'][:5]:
            lines.append(f'  🟢 {s["name"]}：{s["main_inflow"]:+.2f}亿')
        lines.append('')
        lines.append('**净流出 TOP5**：')
        for s in fund_flow.get('outflow', [])[:5]:
            lines.append(f'  🔴 {s["name"]}：{s["main_inflow"]:+.2f}亿')
    else:
        lines.append('⚠️ 资金流数据获取失败')
    lines.append('')

    # ====== 五、午后展望 ======
    lines.append('【五、午后展望】')
    outlook = generate_outlook(today_news, sectors, fund_flow)
    lines.append(outlook)
    lines.append('')

    lines.append('---')
    lines.append('⚠️ 仅供参考，不构成投资建议')

    return '\n'.join(lines)

# ==========================================
# 8. 主流程
# ==========================================

def main():
    start = time.time()
    log('====== 财经午报开始生成 ======')
    report = generate_afternoon_report()
    print(report)
    log(f'====== 午报生成完毕，耗时 {time.time()-start:.1f}s ======')

if __name__ == '__main__':
    main()
