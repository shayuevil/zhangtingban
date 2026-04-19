"""
实时行情多源客户端
数据源优先级：腾讯行情(qt.gtimg.cn) > 东方财富push2 > 新浪(hq.sinajs.cn)
支持WebSocket推送模式（东方财富WS，需安装websockets）
"""
import os
import re
import json
import time
import struct
import zlib
import threading
from typing import Dict, List, Optional, Callable
from datetime import datetime

# 禁用代理
os.environ['NO_PROXY'] = '*'
for key in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']:
    os.environ.pop(key, None)

import requests
requests.Session.trust_env = False

from config import REALTIME_QUOTE_INTERVAL


# ========== 数据源：腾讯行情 (qt.gtimg.cn) — 第一优先级 ==========

def _code_to_tencent_prefix(code: str) -> str:
    """将股票代码转为腾讯行情格式：sh600519 / sz000001"""
    code = str(code).strip()
    if code.startswith(('6', '9')):
        return f'sh{code}'
    else:
        return f'sz{code}'


def fetch_realtime_quotes_tencent(stock_codes: List[str]) -> Dict[str, Dict]:
    """
    通过腾讯行情API批量获取实时行情（第一优先级）
    延迟<3秒，一次最多约800只

    返回: {code: {code, name, price, change_pct, volume, amount, turnover, source}}
    """
    if not stock_codes:
        return {}

    try:
        results = {}
        batch_size = 200

        for i in range(0, len(stock_codes), batch_size):
            batch = stock_codes[i:i + batch_size]
            codes_str = ','.join(_code_to_tencent_prefix(c) for c in batch)

            url = f"http://qt.gtimg.cn/q={codes_str}"
            r = requests.get(url, timeout=10)

            if r.status_code != 200:
                continue

            for line in r.text.strip().split(';'):
                line = line.strip()
                if not line or '="' not in line:
                    continue

                try:
                    # 格式: v_sh600519="1~贵州茅台~600519~1460.49~1465.02~..."
                    var_part, data_str = line.split('="', 1)
                    data_str = data_str.rstrip('"')
                    if not data_str:
                        continue

                    fields = data_str.split('~')
                    if len(fields) < 40:
                        continue

                    # 腾讯行情字段说明：
                    # 1=名称, 2=代码, 3=当前价, 4=昨收, 5=今开,
                    # 6=成交量(手), 7=外盘, 8=内盘, 9=买一价,
                    # 30=涨跌额, 31=涨跌幅, 32=换手率, 37=成交额(万)
                    name = fields[1]
                    code = fields[2]
                    price = float(fields[3]) if fields[3] else 0
                    yesterday_close = float(fields[4]) if fields[4] else 0
                    volume = float(fields[6]) if fields[6] else 0       # 手
                    change_pct = float(fields[32]) if fields[32] else 0  # 涨跌幅%
                    turnover = float(fields[38]) if len(fields) > 38 and fields[38] else 0  # 换手率%
                    # 成交额：fields[37]是万元
                    amount_wan = float(fields[37]) if len(fields) > 37 and fields[37] else 0
                    amount = amount_wan * 1e4  # 万 -> 元

                    if price <= 0:
                        continue

                    # 如果涨跌幅为0但有昨收价，自行计算
                    if change_pct == 0 and yesterday_close > 0:
                        change_pct = round((price - yesterday_close) / yesterday_close * 100, 2)

                    results[code] = {
                        'code': code,
                        'name': name,
                        'price': price,
                        'change_pct': round(change_pct, 2),
                        'volume': volume,
                        'amount': amount,
                        'turnover': turnover,
                        'high': float(fields[33]) if len(fields) > 33 and fields[33] else 0,
                        'low': float(fields[34]) if len(fields) > 34 and fields[34] else 0,
                        'open': float(fields[5]) if fields[5] else 0,
                        'prev_close': yesterday_close,
                        'source': 'tencent',
                    }
                except (ValueError, IndexError):
                    continue

            if i + batch_size < len(stock_codes):
                time.sleep(0.1)

        return results

    except Exception as e:
        print(f"  [腾讯行情] 获取失败: {e}")
        return {}


# ========== 数据源：东方财富push2 HTTP API — 第二优先级 ==========

def _code_to_em_secid(code: str) -> str:
    """将股票代码转为东方财富secid格式: 0.000001 / 1.600519"""
    code = str(code).strip()
    if code.startswith(('6', '9')):
        return f'1.{code}'
    else:
        return f'0.{code}'


def fetch_realtime_quotes_em(stock_codes: List[str]) -> Dict[str, Dict]:
    """
    通过东方财富push2 HTTP API批量获取实时行情（第二优先级）
    一次请求最多约200只，数据延迟<3秒
    注意：push2.eastmoney.com 在某些网络环境下可能被拦截

    返回: {code: {code, name, price, change_pct, volume, amount, source}}
    """
    if not stock_codes:
        return {}

    try:
        results = {}
        batch_size = 200

        for i in range(0, len(stock_codes), batch_size):
            batch = stock_codes[i:i + batch_size]
            secids = ','.join(_code_to_em_secid(c) for c in batch)

            url = "https://push2.eastmoney.com/api/qt/clist/get"
            params = {
                'pn': '1',
                'pz': str(len(batch)),
                'np': '1',
                'fltt': '2',
                'invt': '2',
                'fid': 'f3',
                'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048',
                'fields': 'f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f14,f15,f16,f17,f18',
                'secids': secids,
            }

            r = requests.get(url, params=params, timeout=10,
                             headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://quote.eastmoney.com/'})

            if r.status_code != 200:
                continue

            data = r.json()
            diff = data.get('data', {}).get('diff', [])
            if not diff:
                continue

            for item in diff:
                code = str(item.get('f12', ''))
                if not code or code not in batch:
                    continue

                name = str(item.get('f14', ''))
                price = float(item.get('f2', 0) or 0)
                change_pct = float(item.get('f3', 0) or 0)
                volume = float(item.get('f5', 0) or 0)
                amount = float(item.get('f6', 0) or 0)
                turnover = float(item.get('f8', 0) or 0)
                high = float(item.get('f15', 0) or 0)
                low = float(item.get('f16', 0) or 0)
                open_price = float(item.get('f17', 0) or 0)
                prev_close = float(item.get('f18', 0) or 0)

                if price <= 0:
                    continue

                results[code] = {
                    'code': code,
                    'name': name,
                    'price': price,
                    'change_pct': round(change_pct, 2),
                    'volume': volume,
                    'amount': amount,
                    'turnover': turnover,
                    'high': high,
                    'low': low,
                    'open': open_price,
                    'prev_close': prev_close,
                    'source': 'em_http',
                }

            if i + batch_size < len(stock_codes):
                time.sleep(0.1)

        return results

    except Exception as e:
        print(f"  [东方财富HTTP行情] 获取失败: {e}")
        return {}


def fetch_realtime_quote_single(code: str) -> Optional[Dict]:
    """获取单只股票实时行情（多源尝试）"""
    # 1. 腾讯
    try:
        quotes = fetch_realtime_quotes_tencent([code])
        if quotes:
            return quotes[code]
    except Exception:
        pass
    # 2. 东方财富
    try:
        secid = _code_to_em_secid(code)
        url = "https://push2.eastmoney.com/api/qt/stock/get"
        params = {
            'secid': secid,
            'fields': 'f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f14,f15,f16,f17,f18',
            'np': '1', 'fltt': '2',
        }
        r = requests.get(url, params=params, timeout=10,
                         headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://quote.eastmoney.com/'})
        if r.status_code == 200:
            data = r.json().get('data', {})
            if data:
                price = float(data.get('f2', 0) or 0)
                if price > 0:
                    return {
                        'code': code, 'name': str(data.get('f14', '')),
                        'price': price, 'change_pct': round(float(data.get('f3', 0) or 0), 2),
                        'volume': float(data.get('f5', 0) or 0), 'amount': float(data.get('f6', 0) or 0),
                        'turnover': float(data.get('f8', 0) or 0),
                        'high': float(data.get('f15', 0) or 0), 'low': float(data.get('f16', 0) or 0),
                        'open': float(data.get('f17', 0) or 0), 'prev_close': float(data.get('f18', 0) or 0),
                        'source': 'em_http',
                    }
    except Exception:
        pass
    return None


# ========== 统一实时行情获取（多源自动切换）==========

def fetch_realtime_quotes(stock_codes: List[str]) -> Dict[str, Dict]:
    """
    多源实时行情获取（自动切换）
    优先级：腾讯行情 > 东方财富push2 > 新浪

    返回: {code: {code, name, price, change_pct, volume, amount, turnover, source}}
    """
    if not stock_codes:
        return {}

    # 1. 腾讯行情（第一优先级，当前网络可用）
    try:
        results = fetch_realtime_quotes_tencent(stock_codes)
        if results and len(results) >= len(stock_codes) * 0.5:
            return results
    except Exception:
        pass

    # 2. 东方财富push2（第二优先级，部分网络环境不可用）
    try:
        results = fetch_realtime_quotes_em(stock_codes)
        if results and len(results) >= len(stock_codes) * 0.5:
            return results
    except Exception:
        pass

    # 3. 新浪行情（最终降级，在data_fetcher中实现）
    return {}


# ========== 数据源可用性检测 ==========

def check_tencent_available() -> bool:
    """检测腾讯行情API是否可用"""
    try:
        r = requests.get('http://qt.gtimg.cn/q=sh600519', timeout=5)
        return r.status_code == 200 and '贵州茅台' in r.text
    except Exception:
        return False


def check_em_http_available() -> bool:
    """检测东方财富HTTP API是否可用"""
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {'pn': '1', 'pz': '1', 'fs': 'm:0+t:6', 'fields': 'f12'}
        r = requests.get(url, params=params, timeout=5,
                         headers={'User-Agent': 'Mozilla/5.0'})
        return r.status_code == 200 and len(r.text) > 50
    except Exception:
        return False


def get_best_quote_source() -> str:
    """获取当前最佳可用行情源"""
    if check_tencent_available():
        return "腾讯行情(实时)"
    elif check_em_http_available():
        return "东方财富push2(实时)"
    else:
        return "新浪(降级)"


# ========== 东方财富WebSocket实时行情 ==========

EM_WS_URL = "wss://push.eastmoney.com/websocket"
EM_QUOTE_FIELDS = 'f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f14,f15,f16,f17,f18'


def _build_subscribe_msg(stock_codes: List[str]) -> str:
    """构建东方财富WebSocket订阅消息"""
    sub_id = str(int(time.time() * 1000))[-8:]
    secid_list = [_code_to_em_secid(c) for c in stock_codes]
    msg = {"op": "subscribe", "seq": sub_id, "codes": secid_list, "fields": EM_QUOTE_FIELDS}
    return json.dumps(msg)


def _parse_ws_quote(data: dict) -> Optional[Dict]:
    """解析WebSocket推送的行情数据"""
    code = str(data.get('f12', ''))
    if not code:
        return None
    price = float(data.get('f2', 0) or 0)
    if price <= 0:
        return None
    return {
        'code': code, 'name': str(data.get('f14', '')),
        'price': price, 'change_pct': round(float(data.get('f3', 0) or 0), 2),
        'volume': float(data.get('f5', 0) or 0), 'amount': float(data.get('f6', 0) or 0),
        'turnover': float(data.get('f8', 0) or 0),
        'high': float(data.get('f15', 0) or 0), 'low': float(data.get('f16', 0) or 0),
        'open': float(data.get('f17', 0) or 0), 'prev_close': float(data.get('f18', 0) or 0),
        'source': 'em_ws', 'timestamp': time.time(),
    }


class EMWebSocketClient:
    """
    实时行情WebSocket客户端（多源降级）

    工作模式：
    1. 尝试连接东方财富WebSocket，成功则接收推送行情
    2. WS连接失败时，自动降级为HTTP轮询（腾讯/东方财富/新浪）
    3. 在后台线程运行，通过回调推送行情更新
    """

    def __init__(self, on_quote_update: Callable[[Dict], None] = None):
        self._on_quote_update = on_quote_update
        self._ws = None
        self._connected = False
        self._subscribed_codes: List[str] = []
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._use_ws = False
        self._latest_quotes: Dict[str, Dict] = {}
        self._lock = threading.Lock()
        self._ws_available: Optional[bool] = None

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def mode(self) -> str:
        if self._use_ws and self._connected:
            return "WebSocket推送(东方财富)"
        return f"HTTP轮询({get_best_quote_source()})"

    def get_latest_quotes(self) -> Dict[str, Dict]:
        with self._lock:
            return dict(self._latest_quotes)

    def subscribe(self, stock_codes: List[str]):
        self._subscribed_codes = list(set(stock_codes))
        self._running = True
        if self._thread and self._thread.is_alive():
            if self._use_ws and self._connected:
                self._ws_resubscribe()
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def unsubscribe(self):
        self._running = False
        self._connected = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None

    def update_codes(self, stock_codes: List[str]):
        self._subscribed_codes = list(set(stock_codes))
        if self._use_ws and self._connected:
            self._ws_resubscribe()

    # ========== 内部方法 ==========

    def _try_connect_ws(self) -> bool:
        try:
            import websockets
            import asyncio

            async def _connect():
                ws = await websockets.connect(EM_WS_URL, ping_interval=15, ping_timeout=5, close_timeout=3)
                return ws

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._ws = loop.run_until_complete(_connect())
            self._connected = True
            self._use_ws = True
            self._ws_available = True
            return True
        except ImportError:
            print("  [WebSocket] websockets库未安装，使用HTTP轮询模式")
            self._ws_available = False
            return False
        except Exception as e:
            print(f"  [WebSocket] 连接失败: {e}，降级为HTTP轮询")
            self._ws_available = False
            return False

    def _ws_resubscribe(self):
        if not self._ws or not self._connected:
            return
        try:
            import asyncio
            msg = _build_subscribe_msg(self._subscribed_codes)
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self._ws.send(msg))
        except Exception:
            self._connected = False

    def _run_loop(self):
        if self._ws_available is not False:
            if self._try_connect_ws():
                print("  [实时行情] 东方财富WebSocket已连接，推送模式")
                self._ws_loop()
                return
        source = get_best_quote_source()
        print(f"  [实时行情] 使用HTTP轮询模式({source})")
        self._http_poll_loop()

    def _ws_loop(self):
        import asyncio

        async def _recv():
            try:
                async for message in self._ws:
                    if not self._running:
                        break
                    self._handle_ws_message(message)
            except Exception as e:
                if self._running:
                    print(f"  [WebSocket] 连接断开: {e}")
                    self._connected = False

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            msg = _build_subscribe_msg(self._subscribed_codes)
            loop.run_until_complete(self._ws.send(msg))
            loop.run_until_complete(_recv())
        except Exception:
            self._connected = False

        if self._running:
            print("  [实时行情] WebSocket断开，降级为HTTP轮询")
            self._use_ws = False
            self._http_poll_loop()

    def _handle_ws_message(self, message):
        try:
            if isinstance(message, bytes):
                try:
                    data = zlib.decompress(message, -zlib.MAX_WBITS)
                    data = json.loads(data)
                except Exception:
                    data = json.loads(message)
            else:
                data = json.loads(message)

            if isinstance(data, dict):
                quote = _parse_ws_quote(data)
                if quote:
                    with self._lock:
                        self._latest_quotes[quote['code']] = quote
                    if self._on_quote_update:
                        self._on_quote_update({quote['code']: quote})
            elif isinstance(data, list):
                updates = {}
                for item in data:
                    quote = _parse_ws_quote(item)
                    if quote:
                        with self._lock:
                            self._latest_quotes[quote['code']] = quote
                        updates[quote['code']] = quote
                if updates and self._on_quote_update:
                    self._on_quote_update(updates)
        except Exception:
            pass

    def _http_poll_loop(self):
        self._connected = True
        interval = max(REALTIME_QUOTE_INTERVAL, 5)

        while self._running:
            try:
                if not self._subscribed_codes:
                    time.sleep(interval)
                    continue

                # 多源获取行情（直接调用各源函数，避免循环导入）
                quotes = {}
                # 1. 腾讯行情
                try:
                    quotes = fetch_realtime_quotes_tencent(self._subscribed_codes)
                except Exception:
                    pass
                # 2. 东方财富push2
                if not quotes:
                    try:
                        quotes = fetch_realtime_quotes_em(self._subscribed_codes)
                    except Exception:
                        pass
                # 3. 新浪（延迟导入避免循环）
                if not quotes:
                    try:
                        from data_fetcher import DataFetcher
                        fetcher = DataFetcher()
                        quotes = fetcher._refresh_realtime_quotes_sina(self._subscribed_codes)
                    except Exception:
                        pass

                if quotes:
                    with self._lock:
                        self._latest_quotes.update(quotes)
                    if self._on_quote_update:
                        self._on_quote_update(quotes)

                wait_time = interval
                while wait_time > 0 and self._running:
                    time.sleep(min(1, wait_time))
                    wait_time -= 1

            except Exception as e:
                print(f"  [HTTP轮询] 错误: {e}")
                time.sleep(interval)


if __name__ == '__main__':
    import sys, io
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    print("=" * 50)
    print("实时行情多源测试")
    print("=" * 50)

    test_codes = ['000001', '600519', '300750', '002594', '601318']

    # 1. 数据源可用性
    print("\n[1] 数据源可用性检测...")
    tencent_ok = check_tencent_available()
    em_ok = check_em_http_available()
    best = get_best_quote_source()
    print(f"  腾讯行情: {'可用' if tencent_ok else '不可用'}")
    print(f"  东方财富: {'可用' if em_ok else '不可用'}")
    print(f"  最佳源: {best}")

    # 2. 腾讯行情
    print("\n[2] 腾讯行情测试...")
    t0 = time.time()
    quotes = fetch_realtime_quotes_tencent(test_codes)
    elapsed = time.time() - t0
    print(f"  获取 {len(quotes)} 只，耗时 {elapsed:.2f}秒")
    for code, q in quotes.items():
        print(f"  {q['name']}({code}): 价格={q['price']}, 涨幅={q['change_pct']}%, 成交额={q['amount']/1e8:.2f}亿, 换手={q['turnover']:.2f}%")

    # 3. 多源统一接口
    print("\n[3] 多源统一接口测试...")
    t0 = time.time()
    quotes = fetch_realtime_quotes(test_codes)
    elapsed = time.time() - t0
    print(f"  获取 {len(quotes)} 只，耗时 {elapsed:.2f}秒")
    for code, q in quotes.items():
        print(f"  {q['name']}({code}): 价格={q['price']}, 涨幅={q['change_pct']}%, 来源={q['source']}")

    # 4. WS客户端测试
    print("\n[4] WebSocket客户端测试(10秒)...")
    latest = {}
    def on_update(qs):
        latest.update(qs)
    client = EMWebSocketClient(on_quote_update=on_update)
    client.subscribe(test_codes)
    print(f"  模式: {client.mode}")
    time.sleep(10)
    client.unsubscribe()
    print(f"  收到 {len(latest)} 只股票行情:")
    for code, q in latest.items():
        print(f"  {q['name']}({code}): 价格={q['price']}, 涨幅={q['change_pct']}%, 来源={q['source']}")
