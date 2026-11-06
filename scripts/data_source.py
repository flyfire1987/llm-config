#!/usr/bin/env python3
"""
多源行情数据获取器
主源：腾讯 qt.gtimg.cn
备源：新浪 hq.sinajs.cn
板块数据：腾讯板块列表
"""
import requests
import time
import re
from typing import List, Dict, Optional

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Encoding": "identity",  # 强制不解压，避免 gzip 截断
}

# A股代码 -> 腾讯代码前缀映射
def to_tencent_code(code: str) -> str:
    """6位代码 -> sh/sz 前缀"""
    if code.startswith(("6", "5", "9")):
        return f"sh{code}"
    else:
        return f"sz{code}"

def to_sina_code(code: str) -> str:
    if code.startswith(("6", "5", "9")):
        return f"sh{code}"
    else:
        return f"sz{code}"


def parse_tencent_v(v_data: str) -> Optional[Dict]:
    """解析腾讯 v_xx=... 格式数据
    字段顺序: [1~名称~代码~当前价~昨收~今开~成交量~外盘~内盘...]
    """
    try:
        # v_sh600988="1~名称~代码~当前~昨收~今开~成交量~买一价~买一量~买二价..."
        # 取等号右边，去引号
        if "=" not in v_data:
            return None
        body = v_data.split("=", 1)[1].strip().strip('"')
        parts = body.split("~")
        if len(parts) < 30:
            return None
        return {
            "name": parts[1],
            "code": parts[2],
            "price": float(parts[3]),       # 当前价
            "prev_close": float(parts[4]),  # 昨收
            "open": float(parts[5]),        # 今开
            "volume": int(parts[6]),        # 成交量(手)
            "change": float(parts[31]),     # 涨跌额
            "change_pct": float(parts[32]), # 涨跌幅(%)
            "high": float(parts[33]),        # 最高
            "low": float(parts[34]),        # 最低
            "turnover": float(parts[37]) if parts[37] else 0,  # 成交额(万)
            "pe": float(parts[39]) if parts[39] else 0,       # 市盈率
        }
    except (ValueError, IndexError) as e:
        return None


def get_stocks_tencent(codes: List[str], retries: int = 2) -> Dict[str, Dict]:
    """从腾讯批量拉取股票行情（分批拉，每批最多 5 只）"""
    results = {}
    tencent_codes = [to_tencent_code(c) for c in codes]
    # 分批，每批 1 只（HTTP/2 下多 code 会返回 v_pv_none_match）
    batch_size = 1
    for i in range(0, len(tencent_codes), batch_size):
        batch = tencent_codes[i:i+batch_size]
        url = f"https://qt.gtimg.cn/q={'~'.join(batch)}"
        for attempt in range(retries):
            try:
                r = requests.get(url, headers=HEADERS, timeout=10)
                text = r.content.decode("gbk", errors="replace")
                for line in text.strip().split("\n"):
                    if "=" not in line:
                        continue
                    parsed = parse_tencent_v(line)
                    if parsed:
                        results[parsed["code"]] = parsed
                break
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(1)
                    continue
                print(f"腾讯源拉取 {batch} 失败: {e}")
    return results


def get_stocks_sina(codes: List[str], retries: int = 2) -> Dict[str, Dict]:
    """从新浪拉取股票行情（备源）"""
    results = {}
    sina_codes = [to_sina_code(c) for c in codes]
    url = f"https://hq.sinajs.cn/list={','.join(sina_codes)}"
    headers = {**HEADERS, "Referer": "https://finance.sina.com.cn"}
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=10)
            text = r.content.decode("gbk", errors="replace")
            for line in text.strip().split("\n"):
                if "=" not in line or '""' in line:
                    continue
                # var hq_str_sh600988="贵州茅台,600519,1272.86,...";
                body = line.split('"')[1] if '"' in line else ""
                parts = body.split(",")
                if len(parts) < 32:
                    continue
                code = parts[1] if parts[1] else parts[0][-6:]
                name = parts[0]
                open_p = float(parts[2] or 0)
                prev_close = float(parts[3] or 0)
                price = float(parts[4] or 0)
                high = float(parts[5] or 0)
                low = float(parts[6] or 0)
                change = price - prev_close
                change_pct = (change / prev_close * 100) if prev_close else 0
                results[code] = {
                    "name": name,
                    "code": code,
                    "price": price,
                    "prev_close": prev_close,
                    "open": open_p,
                    "high": high,
                    "low": low,
                    "change": round(change, 3),
                    "change_pct": round(change_pct, 2),
                }
            return results
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1)
                continue
            print(f"新浪源失败: {e}")
    return results


def get_stocks_multi_source(codes: List[str]) -> Dict[str, Dict]:
    """多源获取：先腾讯，失败新浪"""
    result = get_stocks_tencent(codes)
    if not result:
        print("切换到新浪源...")
        result = get_stocks_sina(codes)
    return result


# 主流贵金属股票代码
PRECIOUS_METAL_STOCKS = [
    "600988",  # 赤峰黄金
    "600547",  # 山东黄金
    "601899",  # 紫金矿业
    "600489",  # 中金黄金
    "001337",  # 四川黄金
    "002155",  # 湖南黄金
    "601069",  # 银泰黄金
    "002716",  # 湖南白银
    "000426",  # 兴业银锡
]


def get_precious_metals_overview() -> List[Dict]:
    """获取贵金属板块个股概览"""
    data = get_stocks_multi_source(PRECIOUS_METAL_STOCKS)
    # 按涨跌幅排序
    items = list(data.values())
    items.sort(key=lambda x: x.get("change_pct", 0), reverse=True)
    return items


if __name__ == "__main__":
    print("=" * 60)
    print("贵金属板块行情（多源）")
    print("=" * 60)
    items = get_precious_metals_overview()
    if items:
        print(f"{'名称':<8} {'代码':<8} {'现价':<8} {'涨跌幅':<8} {'成交额(亿)':<10}")
        print("-" * 50)
        for it in items:
            turnover = it.get("turnover", 0)
            turnover_yi = turnover / 1e4 if turnover else 0
            print(f"{it['name']:<10} {it['code']:<8} {it['price']:<8.2f} "
                  f"{it['change_pct']:+.2f}%   {turnover_yi:.2f}")
    else:
        print("❌ 所有源都不可用")
