#!/usr/bin/env python3
"""
搜狗搜索小工具（备用 web_search）
- 爬取搜狗搜索结果
- 用法: python3 web_search.py "关键词" [结果数]
"""
import sys
import re
import requests
from typing import List, Dict

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {
    "User-Agent": UA,
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def search_sogou(query: str, max_results: int = 10) -> List[Dict]:
    """搜狗搜索"""
    results = []
    try:
        r = requests.get(
            "https://www.sogou.com/web",
            params={"query": query, "num": max_results + 5},
            headers=HEADERS,
            timeout=12,
        )
        if r.status_code != 200:
            return [{"error": f"搜狗返回 {r.status_code}"}]
        html = r.text
        # 搜狗结果在 h3 里，但需结合相邻的 a 标签拿 URL
        # 用更宽松的策略：匹配 h3 内的纯文本
        h3_pattern = re.compile(r'<h3[^>]*>(.*?)</h3>', re.DOTALL)
        # 提取每个 h3 后面最近的 <a href> URL
        for m in h3_pattern.finditer(html):
            inner = m.group(1)
            # 清理 HTML 标签得标题
            title = re.sub(r'<[^>]+>', '', inner).strip()
            title = re.sub(r'\s+', ' ', title)
            if not title or len(title) < 6 or '搜狗百科' in title:
                continue
            # 在 h3 范围内找链接
            url_match = re.search(r'href="([^"]+)"', inner)
            url = url_match.group(1) if url_match else ""
            results.append({"title": title, "url": url, "snippet": ""})
            if len(results) >= max_results:
                break
        return results
    except Exception as e:
        return [{"error": str(e)}]


def search_baidu(query: str, max_results: int = 5) -> List[Dict]:
    """百度搜索（兜底）"""
    results = []
    try:
        r = requests.get(
            "https://www.baidu.com/s",
            params={"wd": query, "rn": max_results + 5},
            headers=HEADERS,
            timeout=10,
        )
        if r.status_code != 200:
            return [{"error": f"百度返回 {r.status_code}"}]
        # 百度结果在 <h3 class="...">  里
        for m in re.finditer(r'<h3[^>]*>(.*?)</h3>', r.text, re.DOTALL):
            inner = m.group(1)
            title = re.sub(r'<[^>]+>', '', inner).strip()
            title = re.sub(r'\s+', ' ', title)
            if not title or len(title) < 6:
                continue
            url_match = re.search(r'href="([^"]+)"', inner)
            url = url_match.group(1) if url_match else ""
            results.append({"title": title, "url": url})
            if len(results) >= max_results:
                break
        return results
    except Exception as e:
        return [{"error": str(e)}]


def search(query: str, max_results: int = 8) -> List[Dict]:
    """多源搜索：先搜狗，失败用百度"""
    results = search_sogou(query, max_results)
    if not results or "error" in results[0]:
        results = search_baidu(query, max_results)
    return results


def format_results(results: List[Dict], query: str) -> str:
    if not results:
        return f"❌ 未找到结果"
    if "error" in results[0]:
        return f"❌ 搜索失败: {results[0]['error']}"
    out = [f"🔍 搜索: {query}\n"]
    for i, r in enumerate(results, 1):
        out.append(f"{i}. {r['title']}")
        if r.get("url"):
            out.append(f"   {r['url'][:100]}")
    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 web_search.py <关键词> [结果数]")
        sys.exit(1)
    query = sys.argv[1]
    max_n = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    results = search(query, max_n)
    print(format_results(results, query))
