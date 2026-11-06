#!/usr/bin/env python3
"""
morning_news_report.py - 财经早报数据采集与生成（独立脚本版）
================================================================

【数据源分层】
T1 权威源（必抓）:
  - 财联社电报  https://www.cls.cn/telegraph
  - 东方财富财经早餐 https://finance.eastmoney.com
  - 证监会/央行/财政部（待接入RSS）
T2 专业源（补充）:
  - 证券时报 / 中国证券报（通过web_fetch抓取）
  - 券商中国 / 21财经
T3 行情数据:
  - 腾讯财经 / Sina（已封装在data_source.py）
  - akshare（主力资金/板块）

【输出】stdout 一份结构化早报
【失败处理】每个数据源独立 try/except，整体不崩
"""

import sys
import os
import re
import json
import time
import random
import warnings
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

warnings.filterwarnings('ignore')

# 复用已有工具
sys.path.insert(0, '/root/.openclaw/workspace')
sys.path.insert(0, '/root/.openclaw/workspace/scripts')

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    os.system('pip install requests beautifulsoup4 -q')
    import requests
    from bs4 import BeautifulSoup

try:
    from data_source import get_realtime_price, get_kline
    HAS_DATA_SOURCE = True
except Exception:
    HAS_DATA_SOURCE = False

# ==========================================
# 1. 数据源配置（分层 + 优先级）
# ==========================================

NEWS_SOURCES = {
    'T1': [
        {
            'name': '财联社首页',
            'url': 'https://www.cls.cn/',
            'type': 'web_fetch',
            'weight': 1.0,  # 可信度权重
            'focus': ['A股', '政策', '业绩', '涨停'],
        },
        {
            'name': '东方财富财经首页',
            'url': 'https://finance.eastmoney.com',
            'type': 'web_fetch',
            'weight': 0.9,
            'focus': ['财经', '股票', '板块'],
        },
    ],
    'T2': [
        {
            'name': '证券时报',
            'url': 'https://www.stcn.com',
            'type': 'web_fetch',
            'weight': 0.85,
            'focus': ['财经', '监管'],
        },
        {
            'name': '21财经移动版',
            'url': 'https://m.21jingji.com',
            'type': 'web_fetch',
            'weight': 0.8,
            'focus': ['财经'],
        },
        {
            'name': '第一财经',
            'url': 'https://www.yicai.com',
            'type': 'web_fetch',
            'weight': 0.8,
            'focus': ['财经'],
        },
    ],
    'T3': [
        {
            'name': '新浪财经',
            'url': 'https://finance.sina.com.cn',
            'type': 'web_fetch',
            'weight': 0.6,
            'focus': ['财经'],
        },
    ],
}

# 板块-关键词-代表股映射（用于A 股关联分析）
SECTOR_KEYWORDS = {
    'AI算力/芯片': ['算力', 'GPU', 'AI芯片', '英伟达', '博通', '光模块', 'CPO'],
    '人形机器人': ['人形机器人', '宇树', 'Optimus', '帕西尼', '减速器', '丝杠'],
    '算力金属/有色': ['铜', '锡', '铟', '锗', '镓', '锂', '钴', '稀土', '算力金属'],
    '新能源汽车': ['比亚迪', '新能源车', '锂电', '固态电池', '充电桩'],
    '军工/航天': ['航天', '军工', '导弹', '卫星', 'SpaceX', '火箭'],
    '医药/创新药': ['创新药', 'GLP-1', '减肥药', 'ADC', 'CRO'],
    '光伏/储能': ['光伏', '储能', '钙钛矿', 'TOPCon', 'HJT'],
    '房地产': ['房地产', '楼市', '保交楼', '城中村'],
    '金融/银行': ['银行', '保险', '券商', '金融'],
    '黄金/贵金属': ['黄金', '白银', '赤金', '贵金属', '金价'],
}

# 新闻类型分类（用于标签化输出）
NEWS_TYPE_KEYWORDS = {
    '政策/监管': ['央行', '证监会', '银保监', '国常会', '政治局', '政策', '监管', '改革'],
    '业绩/财报': ['财报', '业绩', '净利', '营收', '扭亏', '预增', '预减'],
    '产业/技术': ['量产', '突破', '首发', '技术', '供应链', '量产'],
    '资本运作': ['IPO', '上市', '并购', '重组', '回购', '增持', '减持', '募资'],
    '市场异动': ['涨停', '跌停', '暴涨', '暴跌', '腰斩', '异动', '拉升', '砸盘'],
    '宏观/国际': ['美联储', '加息', '降息', 'CPI', 'GDP', '通胀', '欧央行', '褐皮书'],
}

# 利好/利空词
POSITIVE_KEYWORDS = ['上涨', '突破', '利好', '量产', '获批', '达成', '签署', '增加', '提高', '增持', '回购', '增长', '超预期', '新高']
NEGATIVE_KEYWORDS = ['下跌', '暴跌', '利空', '腰斩', '减持', '下调', '减产', '收缩', '走低', '退市', '退费', '超低', '失守']

# 关键词 → 关联 A 股（精选强关联）
NEWS_TO_STOCKS = {
    '博通': [('AVGO', '美股'), ('中芯国际', '688981'), ('兆易创新', '603986')],
    '英伟达': [('NVDA', '美股'), ('胜宏科技', '300476'), ('沪电股份', '002463')],
    '比亚迪': [('比亚迪', '002594')],
    '算力金属': [('紫金矿业', '601899'), ('云南铜业', '000878'), ('锡业股份', '000960')],
    '金属': [('紫金矿业', '601899'), ('云南铜业', '000878'), ('锡业股份', '000960')],
    '铜': [('紫金矿业', '601899'), ('云南铜业', '000878')],
    '锡': [('锡业股份', '000960'), ('兴业银锡', '000426')],
    '美联诸': [('黄金ETF', '518880')],
    '美联储': [('黄金ETF', '518880'), ('中国平安', '601318')],
    '算力': [('中科曙光', '603019'), ('润建股份', '002929')],
    '芯片': [('兆易创新', '603986'), ('中芯国际', '688981')],
    '夜盘': [('黄金ETF', '518880')],
    '暴跌': [('中信证券', '600030')],
    '長线': [('贵州茅台', '600519'), ('宁德时代', '300750')],
    '人形机器人': [('机器人', '300024'), ('绿的谐波', '688017'), ('汇川技术', '300124')],
    '宇树科技': [('机器人', '300024'), ('蓝思科技', '300433')],
    'SpaceX': [('航天电器', '002025'), ('中国核建', '601611')],
    '伊朗谈判': [('中国石油', '601857'), ('中曼石油', '603619')],
    '霍尔木兹': [('中国石油', '601857')],
    '黄金': [('赤峰黄金', '600988'), ('四川黄金', '001337'), ('山东黄金', '600547')],
    '白银': [('湖南白银', '002716'), ('兴业银锡', '000426')],
    '核建': [('中国核建', '601611')],
}

# ==========================================
# 2. 工具函数
# ==========================================

def log(msg: str, level: str = 'INFO'):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f'[{ts}] [{level}] {msg}', file=sys.stderr)

def safe_get(url: str, timeout: int = 8, headers: Optional[Dict] = None) -> Optional[str]:
    """带重试的 HTTP GET（短超时，避免拖垮早报）"""
    if headers is None:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
    for attempt in range(2):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            # 关键：自动探测真实编码
            if resp.status_code == 200 and resp.content:
                resp.encoding = resp.apparent_encoding or 'utf-8'
                if len(resp.text) > 200:
                    return resp.text
        except Exception as e:
            log(f'GET {url} 失败 (try {attempt+1}): {e}', 'WARN')
        time.sleep(random.uniform(0.3, 0.6))
    return None

def extract_news_list(html: str, base_url: str = '') -> List[Dict]:
    """从 HTML 抽取新闻（标题+URL），针对财经站点优化"""
    items = []
    try:
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup(['script', 'style', 'noscript']):
            tag.decompose()

        # 找 a 标签：含完整URL的
        seen = set()
        for a in soup.find_all('a', href=True):
            text = a.get_text(strip=True)
            href = a['href']
            # 过滤：无文本/纯符号/重复
            if len(text) < 12 or len(text) > 120:
                continue
            if 'javascript' in href.lower() or href.startswith('#'):
                continue
            # 必须是文章URL（带 /a/ 或含日期）
            if not re.search(r'/(a|news|article)/\d+', href) and '2026' not in href and '2025' not in href:
                continue
            # 去重（同一URL）
            key = href[:80]
            if key in seen:
                continue
            seen.add(key)
            # 补全URL
            if href.startswith('/'):
                from urllib.parse import urljoin
                href = urljoin(base_url, href)
            items.append({'title': text, 'url': href})
    except Exception as e:
        log(f'HTML 解析失败: {e}', 'WARN')
    return items

def is_recent(text: str, hours: int = 18) -> bool:
    """粗略判断是否近期（基于文本中的日期/时间标识）"""
    now = datetime.now()
    today_strs = [now.strftime('%m月%d日'), now.strftime('%m-%d'), '今日', '今早', '刚刚']
    yesterday_strs = [(now - timedelta(days=1)).strftime('%m月%d日'), '昨日']
    for s in today_strs + yesterday_strs:
        if s in text:
            return True
    return True  # 默认保留（保守）

def classify_news_type(text: str) -> List[str]:
    """新闻类型分类（可能多标签）"""
    types = []
    for type_name, kws in NEWS_TYPE_KEYWORDS.items():
        if any(kw in text for kw in kws):
            types.append(type_name)
    return types if types else ['其他']

def detect_sentiment(text: str) -> str:
    """利好/利空/中性"""
    pos = sum(1 for kw in POSITIVE_KEYWORDS if kw in text)
    neg = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text)
    if pos > neg + 1:
        return '利好'
    elif neg > pos + 1:
        return '利空'
    return '中性'

def match_sectors(text: str) -> List[str]:
    """匹配板块"""
    sectors = []
    for sector, kws in SECTOR_KEYWORDS.items():
        if any(kw in text for kw in kws):
            sectors.append(sector)
    return sectors

def score_news(text: str) -> float:
    """新闻重要性评分（0-10）"""
    score = 0.0
    # 关键词权重
    high_kw = ['涨停', '跌停', '央行', '证监会', '国常会', '政治局', 'GDP', 'CPI', 'PMI', '美联储', '加息', '降息']
    mid_kw = ['财报', '业绩', '回购', '增持', '中标', '签约', '突破', '量产', '暴跌', '暴涨', '腰斩', 'IPO', '上市']
    low_kw = ['上涨', '下跌', '板块', '概念', '利好', '利空', '催化', '谈判']

    for kw in high_kw:
        if kw in text:
            score += 3.0
    for kw in mid_kw:
        if kw in text:
            score += 1.5
    for kw in low_kw:
        if kw in text:
            score += 0.5

    # 数字密度（带数字的新闻通常更具体）
    digits = len(re.findall(r'\d+', text))
    if digits >= 3:
        score += 1.0

    # 长度惩罚（太短不可信）
    if len(text) < 20:
        score -= 2.0

    # 关键公司名/事件加分（如果出现 NEWS_TO_STOCKS 里的关键词，自动基础分）
    for kw in NEWS_TO_STOCKS.keys():
        if kw in text:
            score += 2.0  # 强关联公司事件，基础分拉高
            break

    return min(max(score, 0), 10)

def _extract_keywords(text: str) -> set:
    """从标题提取关键词集合（2字以上中文/英文/数字）"""
    # 去除标点
    clean = re.sub(r'[【】\s\d\W_]+', ' ', text)
    words = set()
    # 2 字以上中文词
    for m in re.finditer(r'[\u4e00-\u9fff]{2,}', clean):
        words.add(m.group())
    # 3 字以上英文词（专有名词、缩写）
    for m in re.finditer(r'[A-Za-z]{3,}', clean):
        words.add(m.group().lower())
    # 4 位以上数字（日期、代码）
    for m in re.finditer(r'\d{4,}', text):
        words.add(m.group())
    # 数字+单位
    for m in re.finditer(r'\d+[%亿万元美股个只多家条]', text):
        words.add(m.group())
    return words

def dedup_news(news_list: List[Dict]) -> List[Dict]:
    """合并重复新闻（同一事件不同报道）"""
    if not news_list:
        return news_list
    groups: List[List[Dict]] = []
    for n in news_list:
        kws = _extract_keywords(n['title'])
        if not kws:
            continue
        merged = False
        for group in groups:
            ref_kws = _extract_keywords(group[0]['title'])
            if not ref_kws:
                continue
            common = kws & ref_kws
            union = kws | ref_kws
            # 两个条件满足一个即合并：交集>=2 或 Jaccard>=0.25
            jaccard = len(common) / len(union) if union else 0
            if len(common) >= 2 or jaccard >= 0.25:
                group.append(n)
                merged = True
                break
        if not merged:
            groups.append([n])

    deduped = []
    for group in groups:
        if len(group) == 1:
            deduped.append(group[0])
        else:
            best = max(group, key=lambda x: x.get('score', 0))
            best['score'] = min(best.get('score', 0) + 0.5, 10)
            best['source'] = '+'.join(sorted(set(n['source'] for n in group)))
            best['multi_source'] = True
            deduped.append(best)
    return deduped

def match_stocks(text: str) -> List[Tuple[str, str]]:
    """根据文本匹配关联 A 股（去重，最多3个）"""
    matched = []
    seen_codes = set()
    for kw, stocks in NEWS_TO_STOCKS.items():
        if kw in text:
            for name, code in stocks:
                if code not in seen_codes and not code.isalpha() or (len(code) == 6 and code not in seen_codes):
                    matched.append((name, code))
                    seen_codes.add(code)
                    if len(matched) >= 3:
                        return matched
    return matched

def get_stock_quote_safe(code: str) -> Optional[Dict]:
    """获取行情（带异常保护）"""
    if not HAS_DATA_SOURCE:
        return None
    try:
        if code.isalpha():  # 美股代码
            return None
        return get_realtime_price(code)
    except Exception:
        return None

def calc_7d_pct(code: str) -> Optional[float]:
    """计算近7日涨幅（基于K线）"""
    if not HAS_DATA_SOURCE:
        return None
    try:
        df = get_kline(code, count=10)
        if df is None or len(df) < 2:
            return None
        # 取最近 7 个交易日
        df = df.tail(7)
        first_close = float(df.iloc[0]['close'])
        last_close = float(df.iloc[-1]['close'])
        if first_close == 0:
            return None
        return (last_close - first_close) / first_close * 100
    except Exception as e:
        log(f'计算 {code} 7日涨幅失败: {e}', 'WARN')
        return None

def get_main_fund_flow(code: str) -> Optional[float]:
    """获取主力资金净流入（近7日累计，单位：万元）"""
    try:
        import akshare as ak
        # 东方财富接口
        df = ak.stock_individual_fund_flow(stock=code, market='sh' if code.startswith(('6','5')) else 'sz')
        if df is None or df.empty:
            # 备选接口
            df = ak.stock_individual_fund_flow_rank(indicator='今日')
            return None
        # 累计近7日主力净流入
        if '主力净流入-净额' in df.columns:
            return float(df['主力净流入-净额'].tail(7).sum()) / 10000  # 元 → 万元
    except Exception as e:
        log(f'获取 {code} 资金流失败: {e}', 'WARN')
        return None

# ==========================================
# 3. 数据采集
# ==========================================

def fetch_cls_telegraph() -> List[Dict]:
    """财联社首页（电报页是JS动态加载，改抓首页）"""
    for url in ['https://www.cls.cn/', 'https://www.cls.cn/telegraph']:
        html = safe_get(url, headers={'Referer': 'https://www.cls.cn/'})
        if not html:
            continue
        items = extract_news_list(html, 'https://www.cls.cn')
        if items:
            return [{
                'title': it['title'],
                'url': it['url'],
                'source': '财联社',
                'raw': it['title'],
                'tier': 'T1',
            } for it in items[:30]]
    return []

def fetch_eastmoney_home() -> List[Dict]:
    """东方财富首页要闻"""
    html = safe_get('https://finance.eastmoney.com', headers={'Referer': 'https://www.eastmoney.com/'})
    if not html:
        # 备用
        html = safe_get('https://www.eastmoney.com')
    if not html:
        return []
    items = extract_news_list(html, 'https://finance.eastmoney.com')
    return [{
        'title': it['title'],
        'url': it['url'],
        'source': '东方财富',
        'raw': it['title'],
        'tier': 'T1',
    } for it in items[:30]]

def fetch_stcn() -> List[Dict]:
    """证券时报"""
    html = safe_get('https://www.stcn.com')
    if not html:
        return []
    items = extract_news_list(html, 'https://www.stcn.com')
    return [{
        'title': it['title'],
        'url': it['url'],
        'source': '证券时报',
        'raw': it['title'],
        'tier': 'T2',
    } for it in items[:15]]

def fetch_21jingji() -> List[Dict]:
    """21财经（补充）"""
    for url in ['https://m.21jingji.com', 'https://www.21jingji.com']:
        html = safe_get(url)
        if html:
            items = extract_news_list(html, url)
            if items:
                return [{
                    'title': it['title'],
                    'url': it['url'],
                    'source': '21财经',
                    'raw': it['title'],
                    'tier': 'T2',
                } for it in items[:15]]
    return []

def fetch_yicai() -> List[Dict]:
    """第一财经"""
    html = safe_get('https://www.yicai.com')
    if not html:
        return []
    items = extract_news_list(html, 'https://www.yicai.com')
    return [{
        'title': it['title'],
        'url': it['url'],
        'source': '第一财经',
        'raw': it['title'],
        'tier': 'T2',
    } for it in items[:10]]

def fetch_sina() -> List[Dict]:
    """新浪财经（保底）"""
    html = safe_get('https://finance.sina.com.cn')
    if not html:
        return []
    items = extract_news_list(html, 'https://finance.sina.com.cn')
    return [{
        'title': it['title'],
        'url': it['url'],
        'source': '新浪财经',
        'raw': it['title'],
        'tier': 'T3',
    } for it in items[:10]]

def fetch_all_news() -> List[Dict]:
    """聚合所有数据源（并行抓取加速）"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    tasks = {
        '财联社': fetch_cls_telegraph,
        '东方财富': fetch_eastmoney_home,
        '证券时报': fetch_stcn,
        '21财经': fetch_21jingji,
        '第一财经': fetch_yicai,
        '新浪财经': fetch_sina,
    }
    all_news = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(fn): name for name, fn in tasks.items()}
        for fut in as_completed(futures, timeout=30):
            name = futures[fut]
            try:
                result = fut.result(timeout=15)
                log(f'{name}: 抓到 {len(result)} 条')
                all_news.extend(result)
            except Exception as e:
                log(f'{name}: 抓取失败 - {e}', 'WARN')

    # 去重（按标题前 30 字）
    seen = set()
    unique = []
    for n in all_news:
        key = n['title'][:30]
        if key not in seen and key.strip():
            seen.add(key)
            unique.append(n)
    return unique

# ==========================================
# 4. 评分 & 筛选
# ==========================================

def rank_news(news_list: List[Dict]) -> List[Dict]:
    """按重要性评分排序，含增强字段"""
    for n in news_list:
        text = n['raw'] + n['title']
        n['score'] = score_news(text)
        n['stocks'] = match_stocks(text)
        n['types'] = classify_news_type(text)
        n['sentiment'] = detect_sentiment(text)
        n['sectors'] = match_sectors(text)
        # 必须能匹配到 A 股，否则降权
        if not n['stocks']:
            n['score'] *= 0.3

    # 去重合并
    news_list = dedup_news(news_list)
    # 按分数倒序
    return sorted(news_list, key=lambda x: x['score'], reverse=True)

# ==========================================
# 5. 报告生成
# ==========================================

def format_stock_line(name: str, code: str) -> str:
    """格式化单只股票行情行"""
    quote = get_stock_quote_safe(code)
    pct_7d = calc_7d_pct(code)
    fund_flow = get_main_fund_flow(code)
    parts = [f'{name}({code})']
    if pct_7d is not None:
        sign = '+' if pct_7d >= 0 else ''
        parts.append(f'7日:{sign}{pct_7d:.2f}%')
    if quote:
        sign = '+' if quote['pct'] >= 0 else ''
        parts.append(f'今:{sign}{quote["pct"]:.2f}%')
    if fund_flow is not None:
        sign = '+' if fund_flow >= 0 else '-'
        # 负数用红色标注（QQ消息中用 emoji 标示）
        marker = '🔴' if fund_flow < 0 else '🟢'
        if abs(fund_flow) >= 10000:  # 超过1亿，用亿单位
            parts.append(f'资金:{marker}{sign}{abs(fund_flow)/10000:.2f}亿')
        else:
            parts.append(f'资金:{marker}{sign}{abs(fund_flow):.0f}万')
    return ' | '.join(parts)

def generate_report(news_list: List[Dict]) -> str:
    """生成结构化早报"""
    today = datetime.now().strftime('%Y-%m-%d %A')
    lines = []
    lines.append(f'📈 财经早报 · {today}')
    lines.append(f'（数据源: 财联社 + 东方财富 + 证券时报 + 21财经 + 第一财经 + 新浪财经 | 最多10条）')
    lines.append('')

    top_news = [n for n in news_list if n['score'] >= 1.5 and n['stocks']][:10]

    if not top_news:
        lines.append('⚠️ 暂未抓到符合条件的热点新闻，请关注盘中动态。')
        return '\n'.join(lines)

    lines.append('【国内热点】')
    for i, n in enumerate(top_news, 1):
        lines.append(f'{i}. {n["title"]}')
        lines.append(f'   要点：{n["raw"][:120]}...' if len(n['raw']) > 120 else f'   要点：{n["raw"]}')
        # 标签：类型、情绪、板块
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
        # 关联股票
        stock_lines = [format_stock_line(name, code) for name, code in n['stocks']]
        if stock_lines:
            lines.append(f'   关联A股：{" / ".join(stock_lines)}')
        lines.append('')

    lines.append('---')
    lines.append('⚠️ 仅供参考，不构成投资建议')

    return '\n'.join(lines)

# ==========================================
# 6. 主流程
# ==========================================

def main():
    start = time.time()
    log('====== 财经早报数据采集开始 ======')

    # Step 1: 抓取
    news_list = fetch_all_news()
    log(f'共抓取 {len(news_list)} 条原始新闻')

    if not news_list:
        print('⚠️ 所有数据源均失败，请检查网络。')
        return

    # Step 2: 排序
    news_list = rank_news(news_list)

    # Step 3: 生成报告
    report = generate_report(news_list)

    # 输出（stdout）
    print(report)

    log(f'====== 早报生成完毕，耗时 {time.time()-start:.1f}s ======')

if __name__ == '__main__':
    main()
