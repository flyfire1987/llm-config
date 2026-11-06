#!/usr/bin/env python3
"""通过 GitHub REST API 推送仓库（绕过 git smart-HTTP）。

背景：本机到 github.com:443 的 TLS 握手极不稳定（实测超时率 >90%），
但 api.github.com:443 稳定（10/10）。git push 走 smart-HTTP 必然挂住，
所以改用 REST API。

关键处理：
  1. 每次请求新建连接（不复用 keep-alive —— 长连接会僵死）
  2. socket 级看门狗：TLS 握手阶段不受 socket timeout 约束，
     必须用独立线程强制中断，否则永久卡死
  3. 一次性取回远端已有文件的 sha（避免逐文件 GET 成为瓶颈）

用法：python3 push_via_api.py <项目目录> <owner/repo>
"""
import base64
import http.client
import json
import os
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse

API_HOST = 'api.github.com'
API = f'https://{API_HOST}'


def _token():
    """从 gh 的 hosts.yml 直读 token。

    不用 `gh auth token` 子进程 —— 实测它会挂住（wait4 阻塞），
    而本脚本本身就是为绕过网络不稳定而写的。
    """
    import re
    path = os.path.expanduser('~/.config/gh/hosts.yml')
    try:
        with open(path, encoding='utf-8') as f:
            s = f.read()
        m = re.search(r'^\s*oauth_token:\s*(\S+)', s, re.M)
        if m:
            return m.group(1)
    except OSError:
        pass
    # 退路：子进程（加超时）
    r = subprocess.run(['gh', 'auth', 'token'], capture_output=True,
                       text=True, timeout=30)
    tok = r.stdout.strip()
    if not tok:
        sys.exit('❌ 取不到 gh token')
    return tok


TOKEN = _token()
HEADERS = {
    'Authorization': f'Bearer {TOKEN}',
    'Accept': 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'push-via-api',
}

CONNECT_TIMEOUT = 15
IO_TIMEOUT = 25
WATCHDOG_TIMEOUT = 35   # 看门狗总时限，必须大于 CONNECT + IO


class Timeout(Exception):
    pass


def _request_once(method, path, data):
    """单次请求。

    看门狗：TLS 握手阶段不受 socket timeout 约束（会无限挂住），
    所以用独立线程跑请求，主线程 join 超时后直接抛错并 abandon 该线程。
    """
    conn = http.client.HTTPSConnection(
        API_HOST, timeout=CONNECT_TIMEOUT, context=ssl.create_default_context())
    result = {}

    def do():
        try:
            conn.connect()
            conn.sock.settimeout(IO_TIMEOUT)
            conn.request(method, path, body=data, headers=HEADERS)
            resp = conn.getresponse()
            result['status'] = resp.status
            result['body'] = resp.read()
        except Exception as e:  # noqa: BLE001
            result['error'] = e
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    t = threading.Thread(target=do, daemon=True)
    t.start()
    t.join(WATCHDOG_TIMEOUT)
    if t.is_alive():
        # 强杀 socket，让线程尽快退出，避免线程泄漏堆积
        try:
            if conn.sock:
                conn.sock.shutdown(socket.SHUT_RDWR)
        except Exception:  # noqa: BLE001
            pass
        raise Timeout(f'请求超时（{WATCHDOG_TIMEOUT}s，看门狗触发）')
    if 'error' in result:
        raise result['error']
    return result['status'], result['body']


def api(method, path, body=None, retries=6, allow=()):
    data = json.dumps(body).encode() if body is not None else None
    last = ''
    for attempt in range(retries):
        try:
            status, raw = _request_once(method, path, data)
            if status in (200, 201):
                return json.loads(raw) if raw else {}
            body_s = raw.decode('utf-8', 'replace')[:300]
            if status in allow:
                return {'__code': status, '__body': body_s}
            last = f'HTTP {status}: {body_s}'
        except urllib.error.HTTPError as e:
            body_s = e.read().decode()[:300]
            if e.code in allow:
                return {'__code': e.code, '__body': body_s}
            last = f'HTTP {e.code}: {body_s}'
        except Exception as e:  # noqa: BLE001
            last = f'{type(e).__name__}: {str(e)[:150]}'
        wait = 2 * (attempt + 1)
        print(f'   ↻ 重试 {attempt+1}/{retries}: {last[:75]} — {wait}s', flush=True)
        time.sleep(wait)
    sys.exit(f'❌ API 失败: {method} {path}\n   {last}')


def collect(src):
    files = []
    for root, dirs, names in os.walk(src):
        dirs[:] = [d for d in dirs
                   if d not in ('.git', '__pycache__', 'node_modules', 'dist', 'build')]
        for n in names:
            full = os.path.join(root, n)
            rel = os.path.relpath(full, src)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            if size > 40 * 1024 * 1024:
                print(f'   ⚠️ 跳过超大文件: {rel} ({size/1048576:.1f}MB)')
                continue
            files.append((rel, full))
    files.sort()
    return files


def existing_shas(repo):
    """一次性取回远端已有文件的 sha（避免逐文件 GET）"""
    r = api('GET', f'/repos/{repo}/git/trees/main?recursive=1', allow=(409, 404))
    if 'tree' not in r:
        return {}
    return {e['path']: e['sha'] for e in r['tree'] if e.get('type') == 'blob'}


def main():
    src, repo = sys.argv[1], sys.argv[2]
    print(f'=== 推送 {src} → {repo} (via Contents API) ===', flush=True)

    files = collect(src)
    print(f'   {len(files)} 个文件', flush=True)

    r = api('PUT', f'/repos/{repo}/contents/.gitkeep',
            {'message': 'chore: init', 'content': ''}, allow=(422,))
    if r.get('__code') == 422:
        print('   （.gitkeep 已存在）', flush=True)

    shas = existing_shas(repo)
    print(f'   远端已有 {len(shas)} 个文件', flush=True)

    ok = fail = 0
    t0 = time.time()
    for i, (rel, full) in enumerate(files, 1):
        with open(full, 'rb') as f:
            content = f.read()
        payload = {
            'message': 'chore: 初始化仓库',
            'content': base64.b64encode(content).decode(),
        }
        if rel in shas:
            payload['sha'] = shas[rel]
        res = api('PUT', f'/repos/{repo}/contents/{urllib.parse.quote(rel)}', payload)
        if res.get('content'):
            ok += 1
        else:
            fail += 1
            print(f'   ❌ {rel}: {json.dumps(res)[:140]}', flush=True)
        if i % 25 == 0 or i == len(files):
            rate = i / max(time.time() - t0, 0.001)
            print(f'   {i}/{len(files)}  (成功 {ok}, 失败 {fail}, {rate:.1f} 文件/秒)', flush=True)

    print(f'\n✅ 完成: 成功 {ok} / 失败 {fail}', flush=True)

    br = api('GET', f'/repos/{repo}/git/refs/heads/main', allow=(409, 404))
    if br.get('object'):
        sha = br['object']['sha']
        subprocess.run(['git', '-C', src, 'update-ref', 'refs/remotes/origin/main', sha],
                       capture_output=True)
        print(f'   本地 remote 引用 → {sha[:8]}', flush=True)


if __name__ == '__main__':
    main()
