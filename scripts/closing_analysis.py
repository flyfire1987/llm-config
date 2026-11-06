#!/usr/bin/env python3
"""
收盘持仓分析脚本 v4 - 完整版
- 大盘指数、北向资金、融资余额、涨停家数
- 行业板块涨跌排名（持仓关联板块高亮）
- 关联商品（黄金/白银期货）
- 个股完整技术指标（实时K线计算 MA/RSI/MACD/BOLL）
- 浮盈亏汇总
- QQ原生表格格式（无markdown code block）
"""

import time, requests, json
from datetime import datetime

# ============ 配置 ============
HOLDINGS_FILE = "/root/.openclaw/workspace/data/holdings.txt"

def load_holdings():
    result = []
    with open(HOLDINGS_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(',')
            if len(parts) >= 3:
                result.append({'name': parts[0], 'code': parts[1], 'cost': float(parts[2])})
    return result

# ============ 网络请求 ============
def http_get(url, timeout=8):
    r = requests.get(url, timeout=timeout)
    return r.text

# ============ 大盘 ============
def get_market():
    import akshare as ak
    rows = []
    df = ak.stock_zh_index_spot_sina()
    targets = {
        'sh000001': '上证指数', 'sh000300': '沪深300',
        'sh000688': '科创50',   'sz399001': '深证成指',
        'sz399006': '创业板指', 'sh000016': '上证50',
    }
    for code, name in targets.items():
        row = df[df['代码'] == code]
        if not row.empty:
            r = row.iloc[0]
            rows.append({'name': name, 'price': round(float(r['最新价']), 2),
                         'change_pct': round(float(r['涨跌幅']), 2)})
    # 北向
    try:
        df_n = ak.stock_hsgt_fund_flow_summary_em()
        north = df_n[df_n['资金方向'] == '北向']['成交净买额'].sum()
    except:
        north = None
    # 融资
    try:
        sh = ak.macro_china_market_margin_sh()
        sz = ak.macro_china_market_margin_sz()
        margin_date = sh.iloc[-1]['日期']
        margin_total = round((float(sh.iloc[-1]['融资余额']) + float(sz.iloc[-1]['融资余额'])) / 1e8, 1)
    except:
        margin_date, margin_total = None, None
    # 涨停
    try:
        zt_count = len(ak.stock_zt_pool_strong_em())
    except:
        zt_count = 0
    return rows, north, margin_date, margin_total, zt_count

# ============ 行业板块 ============
def get_industry_board():
    import akshare as ak
    import pandas as pd
    df = ak.stock_board_industry_summary_ths()
    df_sorted = df.sort_values('涨跌幅', ascending=False).reset_index(drop=True)
    # 涨幅前10和跌幅前5
    top = df_sorted.head(10)
    bot = df_sorted.tail(5)
    combined = pd.concat([top, bot]).drop_duplicates(subset='板块').reset_index(drop=True)
    return combined, df_sorted

def get_sector_map():
    return {
        '600519': ('白酒消费', '贵金属', '饮料制造'),
        '600988': ('黄金有色', '贵金属'),
        '601611': ('核电基建', '建筑装饰'),
        '001314': ('消费电子', '电子化学品'),
        '001337': ('黄金有色', '贵金属'),
        '002716': ('白银有色', '贵金属'),
        '002929': ('通信设备', '通信设备'),
        '300139': ('半导体+黄金', '贵金属'),
        '688635': ('科创次新', '电子化学品'),
    }

# ============ 黄金白银期货 ============
def get_commodities():
    items = []
    try:
        text = http_get("https://qt.gtimg.cn/q=hf_AU2508,hf_AG2508,hf_CU2508")
        for seg in text.split('\n'):
            if '~' not in seg: continue
            name_map = {'hf_AU2508': '黄金期货', 'hf_AG2508': '白银期货', 'hf_CU2508': '沪铜期货'}
            code = seg.split('"')[0].replace('v_', '')
            name = name_map.get(code, code)
            fields = seg.split('"')[1].split('~')
            if len(fields) > 4:
                try:
                    change = float(fields[3])
                    items.append({'name': name, 'price': fields[1], 'change': change})
                except:
                    pass
    except:
        pass
    return items

# ============ 个股实时 ============
def get_realtime(code):
    qcode = f"sh{code}" if code[0] in '56' else f"sz{code}"
    text = http_get(f"https://qt.gtimg.cn/q={qcode}")
    if '"' not in text: return None
    parts = text.split('"')[1].split('~')
    if len(parts) < 38: return None
    prev = float(parts[4])
    return {
        'price': float(parts[3]),
        'open': float(parts[5]),
        'high': float(parts[33]),
        'low': float(parts[34]),
        'prev': prev,
        'change_pct': float(parts[32]),
        'volume': float(parts[36]),
        'amount': float(parts[37]),
        'turnover': float(parts[38]) if parts[38] else 0.0,
        'amplitude': (float(parts[33]) - float(parts[34])) / prev * 100 if prev else 0.0,
    }

# ============ 技术指标（实时K线） ============
def get_tech(code):
    """使用akshare实时获取K线计算技术指标"""
    import akshare as ak
    symbol_map = {'600519': 'sh600519', '600988': 'sh600988', '601611': 'sh601611',
                  '001314': 'sz001314', '001337': 'sz001337', '002716': 'sz002716',
                  '002929': 'sz002929', '300139': 'sz300139', '688635': 'sh688635'}
    sym = symbol_map.get(code, f"sh{code}" if code[0] in '56' else f"sz{code}")
    try:
        df = ak.stock_zh_a_daily(symbol=sym, adjust="qfq")
        if df is None or len(df) < 30:
            return None
        closes = df['close'].tolist()
        # MA
        ma5  = round(sum(closes[-5:]) / 5, 2) if len(closes) >= 5 else None
        ma10 = round(sum(closes[-10:]) / 10, 2) if len(closes) >= 10 else None
        ma20 = round(sum(closes[-20:]) / 20, 2) if len(closes) >= 20 else None
        # RSI
        gains, losses = [], []
        for i in range(1, len(closes)):
            d = closes[i] - closes[i-1]
            gains.append(d if d > 0 else 0.0)
            losses.append(abs(d) if d < 0 else 0.0)
        if len(gains) >= 14:
            ag = sum(gains[-14:]) / 14
            al = sum(losses[-14:]) / 14
            rsi = round(100 - 100 / (1 + ag / al), 1) if al > 0 else 100.0
        else:
            rsi = None
        # MACD
        def ema(data, n):
            k = 2 / (n + 1)
            e = data[0]
            for v in data[1:]:
                e = v * k + e * (1 - k)
            return e
        if len(closes) >= 35:
            ef = ema(closes, 12)
            es = ema(closes, 26)
            dif = round(ef - es, 3)
            # signal 9-day EMA of DIF (simplified)
            dif_series = []
            for i in range(26, len(closes)):
                ef_i = ema(closes[:i+1], 12)
                es_i = ema(closes[:i+1], 26)
                dif_series.append(round(ef_i - es_i, 3))
            if len(dif_series) >= 9:
                sig = round(sum(dif_series[-9:]) / 9, 3)
                macd_hist = round((dif - sig) * 2, 3)
            else:
                sig, macd_hist = None, None
        else:
            dif, sig, macd_hist = None, None, None
        # BOLL
        if len(closes) >= 20:
            recent = closes[-20:]
            m = sum(recent) / 20
            v = sum((x - m) ** 2 for x in recent) / 20
            std = v ** 0.5
            boll_upper = round(m + 2 * std, 2)
            boll_ma20   = round(m, 2)
            boll_lower  = round(m - 2 * std, 2)
        else:
            boll_upper = boll_ma20 = boll_lower = None
        return {
            'ma5': ma5, 'ma10': ma10, 'ma20': ma20,
            'rsi': rsi,
            'dif': dif, 'dea': sig, 'hist': macd_hist,
            'boll_upper': boll_upper, 'boll_ma20': boll_ma20, 'boll_lower': boll_lower,
        }
    except Exception as e:
        return None

# ============ 格式化 ============
def fp(v, digits=2):
    try:
        return f"{float(v):.{digits}f}"
    except:
        return "—"

def fpct(v):
    try:
        v = float(v)
        return f"+{v:.2f}%" if v >= 0 else f"{v:.2f}%"
    except:
        return "—"

def arrow(v):
    try:
        return "▲" if float(v) >= 0 else "▼"
    except:
        return " "

def rsi_signal(rsi):
    if rsi is None: return "─", "─"
    if rsi >= 80: return f"{rsi:.1f}", "⚠️超买"
    if rsi <= 20: return f"{rsi:.1f}", "⚠️超卖"
    return f"{rsi:.1f}", "─"

def ma_position(price, ma5, ma10):
    if ma5 is None: return "─"
    if price > ma5 and ma5 > ma10: return "强势"
    if price < ma5 and ma5 < ma10: return "弱势"
    return "震荡"

# ============ QQ原生表格格式化 ============
def qq_table(headers, rows, widths=None):
    """
    生成QQ原生格式的表格字符串（无markdown，纯文本）
    widths: 每列对齐方式，如 [('左',10), ('右',8)]
    """
    # 计算每列宽度
    col_count = len(headers)
    if widths is None:
        widths = [None] * col_count

    # 初始化列宽
    col_widths = [len(str(h)) for h in headers]

    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))

    # 表头行
    sep = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    header_line = "|" + "|".join(f" {str(headers[i]).ljust(col_widths[i])} " for i in range(col_count)) + "|"

    lines = [sep, header_line, sep.replace('-', '=')]
    for row in rows:
        line = "|" + "|".join(f" {str(row[i]).ljust(col_widths[i])} " for i in range(col_count)) + "|"
        lines.append(line)
    lines.append(sep)
    return "\n".join(lines)

def ma_style(price, ma5, ma10, ma20):
    """均线多空排列"""
    if ma20 is None: return "─"
    if price > ma20 and ma20 > ma10 and ma10 > ma5: return "多头排列"
    if price < ma20 and ma20 < ma10 and ma10 < ma5: return "空头排列"
    return "均线缠绕"

# ============ 主程序 ============
def main():
    t0 = datetime.now()
    holdings = load_holdings()
    sector_map = get_sector_map()

    # ===== 1. 大盘 =====
    lines = []
    lines.append(f"📊 收盘持仓分析  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("═" * 50)

    try:
        indices, north, margin_date, margin_total, zt_count = get_market()
    except Exception as e:
        indices = []
        north, margin_date, margin_total, zt_count = None, None, None, 0

    lines.append("【大盘】")
    idx_data = []
    for idx in indices:
        cp = idx['change_pct']
        a = "▲" if cp >= 0 else "▼"
        s = "+" if cp >= 0 else ""
        idx_data.append([idx['name'], fp(idx['price']), f"{a}{s}{fpct(cp).lstrip('+')}".replace('+', '+')])

    # 对齐格式化
    idx_headers = ['指数', '最新价', '涨跌幅']
    col_w = [len(str(h)) for h in idx_headers]
    for row in idx_data:
        for j in range(3):
            col_w[j] = max(col_w[j], len(str(row[j])))

    idx_lines = ["  " + "  ".join(str(row[j]).ljust(col_w[j]) for j in range(3)) for row in idx_data]
    for l in idx_lines:
        lines.append(l)

    if north is not None:
        nf = "+" if north >= 0 else ""
        lines.append(f"  北向资金 {nf}{north:.2f}亿")
    if margin_total:
        lines.append(f"  融资余额 {margin_total:.1f}亿（{margin_date}）")
    lines.append(f"  涨停家数 {zt_count}")

    # ===== 2. 关联商品 ===== 
    try:
        commods = get_commodities()
        if commods:
            lines.append("")
            lines.append("【关联商品】")
            for c in commods:
                try:
                    chg = float(c['change'])
                    a = "▲" if chg >= 0 else "▼"
                    lines.append(f"  {c['name']} {c['price']} {a}{'+' if chg>=0 else ''}{chg:.2f}%")
                except:
                    pass
    except:
        pass

    # ===== 3. 板块排名 ===== 
    try:
        import pandas as pd
        df_board, df_all = get_industry_board()
        # 持仓关联板块
        holding_sectors = set()
        for h in holdings:
            secs = sector_map.get(h['code'], (None, None))
            holding_sectors.add(secs[0])  # 中文板块名
            if secs[1]: holding_sectors.add(secs[1])  # 英文板块名

        lines.append("")
        lines.append("【板块涨跌】")
        top5 = df_all.head(5)
        bot5 = df_all.tail(3)
        for _, r in pd.concat([top5, bot5]).iterrows():
            chg = r['涨跌幅']
            a = "▲" if chg >= 0 else "▼"
            sector_name = r['板块']
            tag = " ◀持仓" if sector_name in holding_sectors else ""
            net_in = r.get('净流入', 0)
            up = r.get('上涨家数', '-')
            dn = r.get('下跌家数', '-')
            lines.append(f"  {a} {sector_name:<8} {a}{'+' if chg>=0 else ''}{chg:.2f}%  净流入{net_in:.1f}亿  涨跌比{up}/{dn}{tag}")
    except Exception as e:
        lines.append(f"\n板块数据获取失败: {e}")

    lines.append("─" * 50)

    # ===== 4. 个股 ===== 
    lines.append("\n【持仓个股】")
    stock_header = ["名称", "现价", "涨跌", "振幅", "换手", "MA5", "MA10", "RSI", "MACD", "BOLL", "信号"]
    stock_rows = []

    for h in holdings:
        rt = get_realtime(h['code'])
        time.sleep(0.3)

        if rt is None:
            stock_rows.append([h['name'], "获取失败", "", "", "", "", "", "", "", "", ""])
            continue

        tech = get_tech(h['code'])
        time.sleep(0.5)  # 避免频率限制

        price = rt['price']
        cp = rt['change_pct']
        profit_pct = (price - h['cost']) / h['cost'] * 100

        a = "▲" if cp >= 0 else "▼"
        sp = "+" if cp >= 0 else ""

        ma5_v  = tech['ma5']  if tech else None
        ma10_v = tech['ma10'] if tech else None
        ma20_v = tech['ma20'] if tech else None
        rsi_v  = tech['rsi']  if tech else None
        dif_v  = tech['dif']  if tech else None

        # RSI信号
        rsi_str, rsi_tag = rsi_signal(rsi_v)

        # MACD
        if dif_v is not None:
            macd_str = f"({'+' if dif_v >= 0 else ''}{dif_v:.3f})"
        else:
            macd_str = "─"

        # BOLL
        if tech and tech.get('boll_upper'):
            boll_str = f"({tech['boll_lower']}/{tech['boll_ma20']}/{tech['boll_upper']})"
        else:
            boll_str = "─/─/─"

        # 均线信号
        ma_sig = ma_style(price, ma5_v, ma10_v, ma20_v)

        # 浮盈亏
        profit_emoji = "✅" if profit_pct >= 0 else "🔴"
        profit_tag = f"{profit_emoji}{'+' if profit_pct>=0 else ''}{profit_pct:.1f}%"

        row = [
            h['name'],
            fp(price),
            f"{a}{sp}{fpct(cp).lstrip('+')}",
            f"{rt['amplitude']:.2f}%",
            f"{rt['turnover']:.2f}%",
            fp(ma5_v) if ma5_v else "─",
            fp(ma10_v) if ma10_v else "─",
            rsi_str,
            macd_str,
            boll_str,
            f"{ma_sig} {rsi_tag}",
        ]
        stock_rows.append(row)

    # 打印个股表格（格式化）
    col_widths_s = [len(str(h)) for h in stock_header]
    for row in stock_rows:
        for j, cell in enumerate(row):
            col_widths_s[j] = max(col_widths_s[j], len(str(cell)))

    sep = "+" + "+".join("-" * (col_widths_s[j] + 2) for j in range(len(stock_header))) + "+"
    header_s = "|" + "|".join(f" {str(stock_header[j]).ljust(col_widths_s[j])} " for j in range(len(stock_header))) + "|"
    lines.append(sep)
    lines.append(header_s)
    lines.append(sep.replace('-', '='))
    for row in stock_rows:
        line = "|" + "|".join(f" {str(row[j]).ljust(col_widths_s[j])} " for j in range(len(stock_header))) + "|"
        lines.append(line)
    lines.append(sep)

    # ===== 5. 浮盈亏汇总 ===== 
    lines.append("\n【浮盈亏汇总】")
    profit_header = ["名称", "成本", "现价", "浮盈亏额", "浮盈亏率"]
    profit_rows = []

    total_cost = 0.0
    total_value = 0.0

    for h in holdings:
        rt = get_realtime(h['code'])
        time.sleep(0.3)
        if rt:
            p = rt['price']
            pa = p - h['cost']
            pp = pa / h['cost'] * 100
            total_cost += h['cost']
            total_value += p
            sa = "+" if pa >= 0 else ""
            sp = "+" if pp >= 0 else ""
            profit_rows.append([
                h['name'], fp(h['cost']), fp(p),
                f"{sa}{pa:.2f}", f"{sp}{pp:.2f}%"
            ])

    col_widths_p = [len(str(h)) for h in profit_header]
    for row in profit_rows:
        for j, cell in enumerate(row):
            col_widths_p[j] = max(col_widths_p[j], len(str(cell)))
    sep_p = "+" + "+".join("-" * (col_widths_p[j] + 2) for j in range(len(profit_header))) + "+"
    header_p = "|" + "|".join(f" {str(profit_header[j]).ljust(col_widths_p[j])} " for j in range(len(profit_header))) + "|"
    lines.append(sep_p)
    lines.append(header_p)
    lines.append(sep_p.replace('-', '='))
    for row in profit_rows:
        line = "|" + "|".join(f" {str(row[j]).ljust(col_widths_p[j])} " for j in range(len(profit_header))) + "|"
        lines.append(line)
    lines.append(sep_p)

    # 合计行
    total_pa = total_value - total_cost
    total_pp = total_pa / total_cost * 100 if total_cost else 0
    sa_t = "+" if total_pa >= 0 else ""
    sp_t = "+" if total_pp >= 0 else ""
    total_row = ["合计", fp(total_cost), fp(total_value), f"{sa_t}{total_pa:.2f}", f"{sp_t}{total_pp:.2f}%"]
    line_t = "|" + "|".join(f" {str(total_row[j]).ljust(col_widths_p[j])} " for j in range(len(profit_header))) + "|"
    lines.append(line_t)
    lines.append(sep_p)

    lines.append("\n⚠️ 仅供参考，不构成投资建议")
    lines.append(f"耗时 {round((datetime.now() - t0).total_seconds(), 1)}s")

    report = "\n".join(lines)
    print(report)
    return report

if __name__ == "__main__":
    main()