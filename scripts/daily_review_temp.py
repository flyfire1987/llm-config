import requests
import json

# 腾讯财经指数实时行情
indices = {
    '上证指数': 'sh000001',
    '深证成指': 'sz399001',
    '创业板指': 'sz399006',
    '科创50': 'sh000688'
}

print('=== 大盘指数 ===')
for name, code in indices.items():
    try:
        url = f'https://qt.gtimg.cn/q={code}'
        r = requests.get(url, timeout=5)
        # 格式: v_sz399001="49~name~price~change~change%~..."
        data = r.text.strip().split('~')
        if len(data) > 10:
            price = data[3]
            change = data[4]
            change_pct = data[32] if len(data) > 32 else data[31]
            print(f"{name}: {price} {change} ({change_pct}%)")
    except Exception as e:
        print(f"{name} error: {e}")

print('\n=== 行业板块 ===')
try:
    url = 'https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=20&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:90+t:2&fields=f2,f3,f4,f5,f6,f12,f14'
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://quote.eastmoney.com/'}
    r = requests.get(url, headers=headers, timeout=10)
    result = json.loads(r.text)
    if 'data' in result and result['data']:
        for item in result['data']['diff'][:15]:
            name = item.get('f14', '')
            change = item.get('f3', 0)
            amount = item.get('f6', 0) / 100000000  # 亿
            print(f"{name}: {change}% 成交额:{amount:.1f}亿")
except Exception as e:
    print(f'行业板块 error: {e}')

print('\n=== 持仓个股行情 ===')
# 持仓: 601611 中国核建, 001270 ST铖昌, 588000 科创50ETF
stocks = {
    '中国核建': 'sh601611',
    'ST铖昌': 'sz001270', 
    '科创50ETF华夏': 'sh588000'
}
for name, code in stocks.items():
    try:
        url = f'https://qt.gtimg.cn/q={code}'
        r = requests.get(url, timeout=5)
        data = r.text.strip().split('~')
        if len(data) > 10:
            price = data[3]
            change = data[4]
            change_pct = data[32] if len(data) > 32 else data[31]
            volume = float(data[6]) if data[6] else 0
            vol_str = f"{volume/10000:.0f}万" if volume < 100000000 else f"{volume/100000000:.1f}亿"
            print(f"{name}: {price} {change}({change_pct}%) 成交:{vol_str}")
    except Exception as e:
        print(f"{name} error: {e}")