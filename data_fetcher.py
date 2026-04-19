"""
A股资金流向监控系统 - 数据获取模块
策略：双数据源自动切换（东方财富实时 > 新浪延迟）
实时行情优先通过东方财富push2 API秒级刷新，新浪作为降级备选
"""
import os
import re
import time
from datetime import datetime

# 禁用代理，避免代理连接问题导致请求失败
os.environ['NO_PROXY'] = '*'
os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)
os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)
os.environ.pop('all_proxy', None)
os.environ.pop('ALL_PROXY', None)

import akshare as ak
import pandas as pd
import requests
from typing import List, Dict, Optional
from config import DATA_SOURCE, TUSHARE_TOKEN, DEFAULT_STOCK_COUNT, EXCLUDE_PREFIXES

# 强制 requests 不使用代理
requests.Session.trust_env = False

# ========== 数据源状态 ==========
# 自动检测东方财富源是否可用，启动时检测一次
_em_available: Optional[bool] = None


def _check_eastmoney_available() -> bool:
    """检测东方财富 push2 域名是否可达"""
    try:
        r = requests.get(
            'https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=1&fs=m:0+t:6&fields=f12',
            timeout=5
        )
        return r.status_code == 200 and len(r.text) > 100
    except Exception:
        return False


def get_data_source_status() -> str:
    """获取当前数据源状态描述"""
    global _em_available
    if _em_available is None:
        _em_available = _check_eastmoney_available()

    try:
        from em_websocket import get_best_quote_source
        best_source = get_best_quote_source()
    except Exception:
        best_source = "新浪(降级)"

    if _em_available:
        return f"东方财富(资金流) + {best_source}(实时行情)"
    else:
        return f"{best_source}(实时行情) + 新浪(降级)"


def _parse_amount(val) -> float:
    """
    解析金额字符串为浮点数（单位：元）
    如 '3.43亿' -> 343000000, '5262万' -> 52620000, '1234' -> 1234
    """
    if isinstance(val, (int, float)):
        return float(val)
    if not isinstance(val, str):
        return 0.0
    val = val.strip()
    try:
        if val.endswith('亿'):
            return float(val[:-1]) * 1e8
        elif val.endswith('万'):
            return float(val[:-1]) * 1e4
        else:
            return float(val)
    except (ValueError, TypeError):
        return 0.0


def _code_to_sina_prefix(code: str) -> str:
    """将纯数字股票代码转为新浪行情格式：sh600519 / sz000001"""
    code = str(code).strip()
    if code.startswith(('6', '9')):
        return f'sh{code}'
    else:
        return f'sz{code}'


class DataFetcher:
    """数据获取器（双数据源自动切换 + 实时行情秒级刷新）"""

    def __init__(self, source: str = DATA_SOURCE):
        self.source = source
        self._em_available: Optional[bool] = None
        self._init_source()

    def _init_source(self):
        """初始化数据源"""
        if self.source == 'tushare' and TUSHARE_TOKEN:
            import tushare as ts
            ts.set_token(TUSHARE_TOKEN)
            self.pro = ts.pro_api()

    @property
    def em_available(self) -> bool:
        """东方财富源是否可用（懒检测，只检测一次）"""
        if self._em_available is None:
            self._em_available = _check_eastmoney_available()
            if self._em_available:
                print("  [数据源] 东方财富push2实时源可用，优先使用")
            else:
                print("  [数据源] 东方财富不可用，使用新浪源 + 实时行情刷新(降级)")
        return self._em_available

    # ========== 股票列表 ==========

    def get_stock_list(self, count: int = DEFAULT_STOCK_COUNT) -> List[str]:
        """获取股票列表（按成交额排名）"""
        try:
            if self.em_available:
                return self._get_stock_list_em(count)
            else:
                return self._get_stock_list_sina(count)
        except Exception as e:
            print(f"获取股票列表失败: {e}")
            # 降级到新浪源
            if self._em_available:
                self._em_available = False
                try:
                    return self._get_stock_list_sina(count)
                except Exception:
                    pass
            return []

    def _get_stock_list_em(self, count: int) -> List[str]:
        """东方财富源获取股票列表"""
        df = ak.stock_zh_a_spot_em()
        df = df[~df['代码'].astype(str).str.startswith(tuple(EXCLUDE_PREFIXES))]
        df['成交额'] = pd.to_numeric(df['成交额'], errors='coerce').fillna(0)
        df = df.sort_values('成交额', ascending=False)
        return df['代码'].head(count).tolist()

    def _get_stock_list_sina(self, count: int) -> List[str]:
        """新浪源获取股票列表"""
        df = ak.stock_zh_a_spot()
        df = df[~df['代码'].astype(str).str.startswith('bj')]
        df['_pure_code'] = df['代码'].astype(str).str.replace(r'^(sh|sz)', '', regex=True)
        df = df[~df['_pure_code'].str.startswith(tuple(EXCLUDE_PREFIXES))]
        df['成交额'] = pd.to_numeric(df['成交额'], errors='coerce').fillna(0)
        df = df.sort_values('成交额', ascending=False)
        return df['_pure_code'].head(count).tolist()

    # ========== 资金流向（核心）==========

    def get_money_flow_batch(self, stock_codes: List[str] = None, count: int = DEFAULT_STOCK_COUNT) -> List[Dict]:
        """
        批量获取资金流向数据
        策略：东方财富实时 > 新浪批量
        """
        try:
            if self.em_available:
                result = self._get_money_flow_em(stock_codes, count)
                if result:
                    return result
                # 降级
                print("  [降级] 东方财富资金流获取失败，切换到新浪源")
                self._em_available = False

            return self._get_money_flow_sina(stock_codes, count)
        except Exception as e:
            print(f"批量获取资金流向失败: {e}")
            return []

    def _get_money_flow_em(self, stock_codes: List[str], count: int) -> List[Dict]:
        """东方财富源资金流向（实时，分档：超大单/大单/中单/小单）"""
        try:
            df = ak.stock_individual_fund_flow_rank(indicator="今日")
            if df is None or df.empty:
                return []

            df = df[~df['代码'].astype(str).str.startswith(tuple(EXCLUDE_PREFIXES))]

            if stock_codes:
                df = df[df['代码'].astype(str).isin(stock_codes)]

            results = []
            for _, row in df.iterrows():
                code = str(row.get('代码', ''))
                name = str(row.get('名称', ''))

                result = {
                    'code': code,
                    'name': name,
                    'close': float(pd.to_numeric(row.get('最新价', 0), errors='coerce') or 0),
                    'change_pct': float(pd.to_numeric(row.get('涨跌幅', 0), errors='coerce') or 0),
                    'turnover': float(pd.to_numeric(row.get('换手率', 0), errors='coerce') or 0),
                    'main_force_inflow': _parse_amount(row.get('主力净流入-净额', 0)),
                    'main_force_ratio': float(pd.to_numeric(row.get('主力净流入-净占比', 0), errors='coerce') or 0),
                    'super_large_order': _parse_amount(row.get('超大单净流入-净额', 0)),
                    'super_large_ratio': float(pd.to_numeric(row.get('超大单净流入-净占比', 0), errors='coerce') or 0),
                    'large_order': _parse_amount(row.get('大单净流入-净额', 0)),
                    'large_ratio': float(pd.to_numeric(row.get('大单净流入-净占比', 0), errors='coerce') or 0),
                    'medium_order': _parse_amount(row.get('中单净流入-净额', 0)),
                    'medium_ratio': float(pd.to_numeric(row.get('中单净流入-净占比', 0), errors='coerce') or 0),
                    'small_order': _parse_amount(row.get('小单净流入-净额', 0)),
                    'small_ratio': float(pd.to_numeric(row.get('小单净流入-净占比', 0), errors='coerce') or 0),
                    'inflow': _parse_amount(row.get('主力净流入-净额', 0)) + abs(_parse_amount(row.get('主力净流入-净额', 0))) / 2,
                    'outflow': abs(_parse_amount(row.get('主力净流入-净额', 0))) / 2,
                    'amount': _parse_amount(row.get('成交额', 0)),
                }
                # 修正流入流出计算
                net = _parse_amount(row.get('主力净流入-净额', 0))
                if net >= 0:
                    result['inflow'] = abs(net) * 2  # 近似
                    result['outflow'] = abs(net)
                else:
                    result['inflow'] = abs(net)
                    result['outflow'] = abs(net) * 2
                results.append(result)

            if not stock_codes:
                results.sort(key=lambda x: x.get('amount', 0), reverse=True)
                results = results[:count]

            return results
        except Exception:
            return []

    def _get_money_flow_sina(self, stock_codes: List[str], count: int) -> List[Dict]:
        """新浪源资金流向（批量，一次请求获取全部）"""
        df = ak.stock_fund_flow_individual()

        if df.empty:
            return []

        # 过滤排除的股票（代码已标准化为6位格式）
        df['_std_code'] = df['股票代码'].apply(
            lambda x: str(int(float(str(x)))).zfill(6) if str(x).replace('.','').isdigit() else str(x)
        )
        df = df[~df['_std_code'].str.startswith(tuple(EXCLUDE_PREFIXES))]

        results = []
        for _, row in df.iterrows():
            # 新浪资金流返回的代码是整数格式(如2475)，需补零为6位(002475)
            raw_code = str(row.get('股票代码', ''))
            try:
                code = str(int(float(raw_code))).zfill(6)
            except (ValueError, TypeError):
                code = raw_code
            name = str(row.get('股票简称', ''))

            if stock_codes and code not in stock_codes:
                continue

            net_amount = _parse_amount(row.get('净额', 0))
            inflow = _parse_amount(row.get('流入资金', 0))
            outflow = _parse_amount(row.get('流出资金', 0))
            # 换手率可能是 "14.43%" 格式，需要去掉%号
            turnover_val = row.get('换手率', 0)
            if isinstance(turnover_val, str):
                turnover_val = turnover_val.replace('%', '').strip()
            turnover = pd.to_numeric(turnover_val, errors='coerce')
            turnover = 0.0 if pd.isna(turnover) else float(turnover)
            close_price = pd.to_numeric(row.get('最新价', 0), errors='coerce')
            close_price = 0.0 if pd.isna(close_price) else float(close_price)
            # 涨跌幅可能是 "5.23%" 格式
            change_val = row.get('涨跌幅', 0)
            if isinstance(change_val, str):
                change_val = change_val.replace('%', '').strip()
            change_pct = pd.to_numeric(change_val, errors='coerce')
            change_pct = 0.0 if pd.isna(change_pct) else float(change_pct)
            amount = _parse_amount(row.get('成交额', 0))

            main_ratio = (net_amount / amount * 100) if amount > 0 else 0

            result = {
                'code': code,
                'name': name,
                'close': close_price,
                'change_pct': change_pct,
                'turnover': turnover,
                'main_force_inflow': net_amount,
                'main_force_ratio': main_ratio,
                'super_large_order': net_amount if net_amount >= 1e8 else 0,
                'super_large_ratio': main_ratio if net_amount >= 1e8 else 0,
                'large_order': net_amount,
                'large_ratio': main_ratio,
                'medium_order': 0,
                'medium_ratio': 0,
                'small_order': 0,
                'small_ratio': 0,
                'inflow': inflow,
                'outflow': outflow,
                'amount': amount,
            }
            results.append(result)

        if not stock_codes:
            results.sort(key=lambda x: x['amount'], reverse=True)
            results = results[:count]

        return results

    def get_money_flow(self, stock_code: str) -> Optional[Dict]:
        """获取个股资金流向数据"""
        results = self.get_money_flow_batch(stock_codes=[stock_code])
        return results[0] if results else None

    def get_batch_money_flow(self, stock_codes: List[str]) -> List[Dict]:
        """批量获取资金流向数据"""
        return self.get_money_flow_batch(stock_codes=stock_codes)

    # ========== 实时行情秒级刷新（关键！）==========

    def refresh_realtime_quotes(self, stock_codes: List[str]) -> Dict[str, Dict]:
        """
        秒级刷新实时行情（多源自动切换）

        返回 {code: {price, change_pct, volume, amount, turnover}} 实时数据

        数据源优先级：
        1. 腾讯行情 qt.gtimg.cn（实时，延迟<3秒）
        2. 东方财富push2 HTTP API（实时，部分网络不可用）
        3. 新浪hq.sinajs.cn（降级，延迟1-5秒）
        """
        if not stock_codes:
            return {}

        # 多源统一接口（腾讯>东财）
        try:
            from em_websocket import fetch_realtime_quotes
            results = fetch_realtime_quotes(stock_codes)
            if results:
                return results
        except Exception:
            pass

        # 最终降级：新浪行情接口
        return self._refresh_realtime_quotes_sina(stock_codes)

    def _refresh_realtime_quotes_sina(self, stock_codes: List[str]) -> Dict[str, Dict]:
        """新浪行情接口（降级方案）"""
        try:
            results = {}
            batch_size = 200

            for i in range(0, len(stock_codes), batch_size):
                batch = stock_codes[i:i+batch_size]
                codes_str = ','.join(_code_to_sina_prefix(c) for c in batch)

                url = f"https://hq.sinajs.cn/list={codes_str}"
                headers = {"Referer": "https://finance.sina.com.cn"}
                r = requests.get(url, headers=headers, timeout=10)

                if r.status_code != 200:
                    continue

                for line in r.text.strip().split('\n'):
                    if '=' not in line:
                        continue

                    match = re.match(r'var hq_str_(s[hz])(\d+)="(.+)"', line.strip())
                    if not match:
                        continue

                    prefix, code, data_str = match.groups()
                    fields = data_str.split(',')
                    if len(fields) < 32:
                        continue

                    try:
                        name = fields[0]
                        price = float(fields[3]) if fields[3] else 0
                        yesterday_close = float(fields[2]) if fields[2] else 0
                        volume = float(fields[8]) if fields[8] else 0
                        amount = float(fields[9]) if fields[9] else 0

                        if yesterday_close > 0:
                            change_pct = (price - yesterday_close) / yesterday_close * 100
                        else:
                            change_pct = 0

                        results[code] = {
                            'code': code,
                            'name': name,
                            'price': price,
                            'change_pct': round(change_pct, 2),
                            'volume': volume,
                            'amount': amount,
                            'source': 'sina_realtime',
                        }
                    except (ValueError, IndexError):
                        continue

                if i + batch_size < len(stock_codes):
                    time.sleep(0.2)

            return results

        except Exception as e:
            print(f"新浪实时行情刷新失败: {e}")
            return {}

    # ========== 大单明细 ==========

    def get_big_deals(self, minutes: int = 5, min_amount: float = 500000) -> List[Dict]:
        """获取大单交易明细（新浪源，逐笔记录）"""
        try:
            df = ak.stock_fund_flow_big_deal()

            if df.empty:
                return []

            from datetime import datetime, timedelta
            cutoff = datetime.now() - timedelta(minutes=minutes)

            df['成交时间'] = pd.to_datetime(df['成交时间'], errors='coerce')
            df = df[df['成交时间'] >= cutoff]

            if df.empty:
                return []

            results = []
            grouped = df.groupby(['股票代码', '股票简称', '大单性质'])

            stats = {}
            for (raw_code, name, nature), group in grouped:
                # 标准化代码格式
                try:
                    code = str(int(float(str(raw_code)))).zfill(6)
                except (ValueError, TypeError):
                    code = str(raw_code)
                if code not in stats:
                    stats[code] = {
                        'code': code,
                        'name': name,
                        'buy_count': 0,
                        'buy_amount': 0.0,
                        'sell_count': 0,
                        'sell_amount': 0.0,
                        'neutral_count': 0,
                        'neutral_amount': 0.0,
                    }
                total_amount = _parse_amount(group['成交额'].sum())
                count = len(group)

                if nature == '买盘':
                    stats[code]['buy_count'] += count
                    stats[code]['buy_amount'] += total_amount
                elif nature == '卖盘':
                    stats[code]['sell_count'] += count
                    stats[code]['sell_amount'] += total_amount
                else:
                    stats[code]['neutral_count'] += count
                    stats[code]['neutral_amount'] += total_amount

            for code, s in stats.items():
                s['net_amount'] = s['buy_amount'] - s['sell_amount']
                s['total_amount'] = s['buy_amount'] + s['sell_amount']
                if abs(s['net_amount']) >= min_amount or s['total_amount'] >= min_amount:
                    results.append(s)

            results.sort(key=lambda x: abs(x['net_amount']), reverse=True)
            return results

        except Exception as e:
            print(f"获取大单明细失败: {e}")
            return []

    # ========== 技术指标 ==========

    def get_stock_technical(self, stock_code: str) -> Optional[Dict]:
        """获取个股技术指标（均线、成交量比率等）"""
        try:
            df = ak.stock_zh_a_hist(symbol=stock_code, period='daily', adjust='qfq')

            if df is None or len(df) < 20:
                return None

            df = df.tail(20)
            close = pd.to_numeric(df['收盘'], errors='coerce')
            volume = pd.to_numeric(df['成交量'], errors='coerce')

            ma5 = close.rolling(5).mean().iloc[-1]
            ma10 = close.rolling(10).mean().iloc[-1]
            ma20 = close.rolling(20).mean().iloc[-1]

            vol_today = volume.iloc[-1]
            vol_ma5 = volume.rolling(5).mean().iloc[-1]
            volume_ratio = (vol_today / vol_ma5) if vol_ma5 > 0 else 1.0

            mav_bull = ma5 > ma10 > ma20

            return {
                'code': stock_code,
                'ma5': float(ma5) if not pd.isna(ma5) else 0,
                'ma10': float(ma10) if not pd.isna(ma10) else 0,
                'ma20': float(ma20) if not pd.isna(ma20) else 0,
                'volume_ratio': float(volume_ratio) if not pd.isna(volume_ratio) else 1.0,
                'mav_bull': bool(mav_bull),
            }
        except Exception:
            return None

    # ========== 板块资金流 ==========

    def get_sector_fund_flow(self) -> Dict[str, float]:
        """获取行业板块资金流向"""
        try:
            df = ak.stock_fund_flow_industry()
            if df.empty:
                return {}

            result = {}
            for _, row in df.iterrows():
                sector = str(row.get('行业', row.get('名称', '')))
                net = _parse_amount(row.get('今日净流入', row.get('净额', 0)))
                if net > 0:
                    result[sector] = net
            return result
        except Exception:
            return {}

    # ========== 实时行情（单只）==========

    def get_realtime_quote(self, stock_code: str) -> Optional[Dict]:
        """获取实时行情（多源自动切换）"""
        try:
            from em_websocket import fetch_realtime_quote_single
            result = fetch_realtime_quote_single(stock_code)
            if result:
                return result
        except Exception:
            pass
        # 降级新浪
        quotes = self._refresh_realtime_quotes_sina([stock_code])
        return quotes.get(stock_code)

    # ========== 涨停股池（212战法用）==========

    def get_zt_pool(self, date: str = None) -> List[Dict]:
        """
        获取指定日期涨停股池数据（东方财富）

        Args:
            date: 交易日期，格式"YYYYMMDD"，默认今天

        Returns: [{code, name, change_pct, close, amount, circulation_market_cap,
                   total_market_cap, turnover, seal_amount, first_seal_time,
                   last_seal_time, break_count, zt_stat, consecutive_days, industry}, ...]
        """
        if date is None:
            date = datetime.now().strftime('%Y%m%d')

        try:
            df = ak.stock_zt_pool_em(date=date)
            if df is None or df.empty:
                return []
        except Exception as e:
            print(f"  [错误] 获取涨停池数据失败(date={date}): {e}")
            return []

        df = df[~df['代码'].astype(str).str.startswith(tuple(EXCLUDE_PREFIXES))]

        results = []
        for _, row in df.iterrows():
            code = str(row.get('代码', ''))
            name = str(row.get('名称', ''))
            close = float(pd.to_numeric(row.get('最新价', 0), errors='coerce') or 0)
            change_pct = float(pd.to_numeric(row.get('涨跌幅', 0), errors='coerce') or 0)
            amount = float(pd.to_numeric(row.get('成交额', 0), errors='coerce') or 0)
            circulation_cap = float(pd.to_numeric(row.get('流通市值', 0), errors='coerce') or 0)
            total_cap = float(pd.to_numeric(row.get('总市值', 0), errors='coerce') or 0)
            turnover = float(pd.to_numeric(row.get('换手率', 0), errors='coerce') or 0)
            seal_amount = float(pd.to_numeric(row.get('封板资金', 0), errors='coerce') or 0)
            first_seal = str(row.get('首次封板时间', ''))
            last_seal = str(row.get('最后封板时间', ''))
            break_count = int(pd.to_numeric(row.get('炸板次数', 0), errors='coerce') or 0)
            zt_stat = str(row.get('涨停统计', ''))
            consecutive = int(pd.to_numeric(row.get('连板数', 0), errors='coerce') or 0)
            industry = str(row.get('所属行业', ''))

            results.append({
                'code': code,
                'name': name,
                'close': close,
                'change_pct': change_pct,
                'amount': amount,
                'circulation_market_cap': circulation_cap,
                'total_market_cap': total_cap,
                'turnover': turnover,
                'seal_amount': seal_amount,
                'first_seal_time': first_seal,
                'last_seal_time': last_seal,
                'break_count': break_count,
                'zt_stat': zt_stat,
                'consecutive_days': consecutive,
                'industry': industry,
                'zt_date': date,
            })

        return results

    # ========== 全市场A股列表（尾盘选股用）==========

    def get_all_a_stocks(self) -> List[Dict]:
        """
        获取全市场A股列表（含涨幅等）
        用于尾盘选股的涨停过滤等
        返回: [{code, name, close, change_pct, amount}, ...]
        """
        # 优先尝试东方财富源
        try:
            result = self._get_all_a_stocks_em()
            if result:
                return result
        except Exception as e:
            print(f"  [提示] 东方财富全市场列表获取失败: {e}")

        # 兜底：新浪源
        try:
            return self._get_all_a_stocks_sina()
        except Exception as e:
            print(f"  [错误] 新浪全市场列表获取失败: {e}")
            return []

    def _get_all_a_stocks_em(self) -> List[Dict]:
        """东方财富源：全市场A股列表（含总市值）"""
        df = ak.stock_zh_a_spot_em()
        if df is None or df.empty:
            return []

        df = df[~df['代码'].astype(str).str.startswith(tuple(EXCLUDE_PREFIXES))]

        # 确认总市值列存在
        cap_col = '总市值' if '总市值' in df.columns else None
        if cap_col is None:
            print("  [警告] 东方财富数据无'总市值'列，可用列: " + str(df.columns.tolist()))

        results = []
        for _, row in df.iterrows():
            code = str(row.get('代码', ''))
            name = str(row.get('名称', ''))
            close = float(pd.to_numeric(row.get('最新价', 0), errors='coerce') or 0)
            change_pct = float(pd.to_numeric(row.get('涨跌幅', 0), errors='coerce') or 0)
            total_market_cap = float(pd.to_numeric(row.get(cap_col, 0), errors='coerce') or 0) if cap_col else 0
            amount = float(pd.to_numeric(row.get('成交额', 0), errors='coerce') or 0)

            if close <= 0 or amount <= 0:
                continue

            results.append({
                'code': code,
                'name': name,
                'close': close,
                'change_pct': change_pct,
                'total_market_cap': total_market_cap,
                'amount': amount,
            })

        return results

    def _get_all_a_stocks_sina(self) -> List[Dict]:
        """新浪源：全市场A股列表（含总市值）"""
        df = ak.stock_zh_a_spot()
        df['_pure_code'] = df['代码'].astype(str).str.replace(r'^(sh|sz)', '', regex=True)
        df = df[~df['_pure_code'].str.startswith(tuple(EXCLUDE_PREFIXES))]

        results = []
        for _, row in df.iterrows():
            code = str(row.get('_pure_code', ''))
            name = str(row.get('名称', ''))
            close = float(pd.to_numeric(row.get('最新价', 0), errors='coerce') or 0)
            change_pct = float(pd.to_numeric(row.get('涨跌幅', 0), errors='coerce') or 0)
            total_market_cap = float(pd.to_numeric(row.get('总市值', row.get('流通市值', 0)), errors='coerce') or 0)
            amount = float(pd.to_numeric(row.get('成交额', 0), errors='coerce') or 0)

            if close <= 0 or amount <= 0:
                continue

            results.append({
                'code': code,
                'name': name,
                'close': close,
                'change_pct': change_pct,
                'total_market_cap': total_market_cap,
                'amount': amount,
            })

        return results

    # ========== 分时数据（VWAP + 尾盘量比）==========

    def get_intraday_data(self, code: str, max_retries: int = 3) -> Optional[Dict]:
        """
        获取个股当日分时数据，用于计算VWAP和尾盘抢筹动能

        Args:
            code: 股票代码（6位纯数字）
            max_retries: 最大重试次数（默认3次）

        Returns:
            {vwap, latest_price, total_volume, tail_volume,
             avg_half_hour_vol, tail_vol_ratio} 或 None
        """
        for attempt in range(1, max_retries + 1):
            try:
                df = ak.stock_intraday_em(symbol=code)
                if df is None or df.empty:
                    return None

                prices = pd.to_numeric(df['成交价'], errors='coerce').fillna(0)
                volumes = pd.to_numeric(df['手数'], errors='coerce').fillna(0)
                times = df['时间'].astype(str)

                # 全天 VWAP = sum(price * volume) / sum(volume)
                pv_sum = (prices * volumes).sum()
                vol_sum = volumes.sum()
                vwap = pv_sum / vol_sum if vol_sum > 0 else 0
                latest_price = float(prices.iloc[-1]) if len(prices) > 0 else 0

                # 全天平均每半小时成交量（交易时间4h=8个半小时）
                total_volume = float(vol_sum)
                avg_half_hour_vol = total_volume / 8 if total_volume > 0 else 0

                # 14:30-14:55 区间成交量
                tail_mask = times.apply(
                    lambda t: len(t) == 8 and '14:30:00' <= t < '14:55:00'
                )
                tail_volume = float(volumes[tail_mask].sum()) if tail_mask.any() else 0

                # 尾盘量比
                tail_vol_ratio = tail_volume / avg_half_hour_vol if avg_half_hour_vol > 0 else 0

                return {
                    'vwap': round(vwap, 3),
                    'latest_price': round(latest_price, 3),
                    'total_volume': total_volume,
                    'total_amount': float(pv_sum),
                    'tail_volume': tail_volume,
                    'avg_half_hour_vol': avg_half_hour_vol,
                    'tail_vol_ratio': round(tail_vol_ratio, 2),
                }
            except Exception as e:
                if attempt < max_retries:
                    wait = attempt * 2  # 递增等待: 2s, 4s
                    print(f"  [提示] 获取{code}分时数据失败(第{attempt}次): {e}，{wait}秒后重试...")
                    time.sleep(wait)
                else:
                    print(f"  [提示] 获取{code}分时数据失败(已重试{max_retries}次): {e}")
                    return None

    def get_stock_industry(self, code: str, max_retries: int = 3) -> str:
        """
        获取个股所属行业（东方财富个股信息）

        Args:
            code: 股票代码（6位纯数字）
            max_retries: 最大重试次数（默认3次）

        Returns:
            行业名称字符串，获取失败返回空字符串
        """
        for attempt in range(1, max_retries + 1):
            try:
                df = ak.stock_individual_info_em(symbol=code)
                if df is None or df.empty:
                    if attempt < max_retries:
                        time.sleep(attempt * 1)
                        continue
                    return ''
                industry_row = df[df['item'] == '行业']
                if not industry_row.empty:
                    return str(industry_row.iloc[0]['value']).strip()
                return ''
            except Exception:
                if attempt < max_retries:
                    time.sleep(attempt * 1)
                else:
                    return ''

    def get_sector_ranking(self, max_retries: int = 3) -> List[Dict]:
        """
        获取行业板块涨幅排名（新浪源）

        Args:
            max_retries: 最大重试次数（默认3次）

        Returns:
            [{sector, change_pct, rank}, ...] 按涨幅降序
        """
        for attempt in range(1, max_retries + 1):
            try:
                df = ak.stock_sector_spot()
                if df is None or df.empty:
                    if attempt < max_retries:
                        time.sleep(attempt * 2)
                        continue
                    return []

                results = []
                for _, row in df.iterrows():
                    sector = str(row.get('板块', ''))
                    change_pct = float(pd.to_numeric(row.get('涨跌幅', 0), errors='coerce') or 0)
                    results.append({
                        'sector': sector,
                        'change_pct': round(change_pct, 2),
                    })

                # 按涨幅降序排列
                results.sort(key=lambda x: x['change_pct'], reverse=True)
                for i, r in enumerate(results):
                    r['rank'] = i + 1

                return results
            except Exception as e:
                if attempt < max_retries:
                    wait = attempt * 2
                    print(f"  [提示] 获取板块排名失败(第{attempt}次): {e}，{wait}秒后重试...")
                    time.sleep(wait)
                else:
                    print(f"  [提示] 获取板块排名失败(已重试{max_retries}次): {e}")
                    return []

    # ========== 盘口数据（委比 + 内外盘）==========

    # 盘口数据缓存：{code: {committee_ratio, outer_volume, inner_volume, outin_ratio}}
    _order_book_cache: Dict[str, Dict] = {}
    _order_book_cache_time: float = 0
    _ORDER_BOOK_CACHE_TTL = 60  # 缓存有效期60秒

    def get_order_book_data(self, code: str, max_retries: int = 3) -> Optional[Dict]:
        """
        获取个股盘口数据（委比、内外盘）
        优化：批量获取全市场数据并缓存，避免逐只重复请求

        Args:
            code: 股票代码（6位纯数字）
            max_retries: 最大重试次数（默认3次）

        Returns:
            {committee_ratio, outer_volume, inner_volume, outin_ratio}
            委比(%)、外盘(手)、内盘(手)、外盘/内盘比
            获取失败返回 None
        """
        # 检查缓存
        now = time.time()
        if self._order_book_cache and (now - self._order_book_cache_time) < self._ORDER_BOOK_CACHE_TTL:
            cached = self._order_book_cache.get(code)
            if cached is not None:
                return cached
            # 缓存中无此代码，说明该股票数据不存在
            return None

        # 批量获取全市场数据并更新缓存
        for attempt in range(1, max_retries + 1):
            try:
                df = ak.stock_zh_a_spot_em()
                if df is None or df.empty:
                    if attempt < max_retries:
                        time.sleep(attempt * 2)
                        continue
                    return None

                # 批量解析所有股票的盘口数据
                new_cache = {}
                for _, row in df.iterrows():
                    try:
                        row_code = str(row.get('代码', ''))
                        committee_ratio = float(pd.to_numeric(row.get('委比', 0), errors='coerce') or 0)
                        outer_vol = float(pd.to_numeric(row.get('外盘', 0), errors='coerce') or 0)
                        inner_vol = float(pd.to_numeric(row.get('内盘', 0), errors='coerce') or 0)
                        outin_ratio = (outer_vol / inner_vol) if inner_vol > 0 else 999.0
                        new_cache[row_code] = {
                            'committee_ratio': round(committee_ratio, 2),
                            'outer_volume': outer_vol,
                            'inner_volume': inner_vol,
                            'outin_ratio': round(outin_ratio, 3),
                        }
                    except Exception:
                        continue

                # 更新缓存
                DataFetcher._order_book_cache = new_cache
                DataFetcher._order_book_cache_time = now

                return new_cache.get(code)

            except Exception as e:
                if attempt < max_retries:
                    wait = attempt * 2
                    print(f"  [提示] 批量获取盘口数据失败(第{attempt}次): {e}，{wait}秒后重试...")
                    time.sleep(wait)
                else:
                    print(f"  [提示] 批量获取盘口数据失败(已重试{max_retries}次): {e}")
                    return None

    # ========== 指数分时数据（抗跌强度用）==========

    def get_index_intraday(self, symbol: str = '000300', max_retries: int = 3) -> Optional[Dict]:
        """
        获取指数当日分时数据（用于抗跌相对强度计算）

        Args:
            symbol: 指数代码，默认沪深300（000300）
                    上证指数: 000001, 深证成指: 399001
            max_retries: 最大重试次数（默认3次）

        Returns:
            {times: [str], prices: [float], vwap: float}
            分时时间列表、价格列表、分时均价
            获取失败返回 None
        """
        for attempt in range(1, max_retries + 1):
            try:
                df = ak.stock_intraday_em(symbol=symbol)
                if df is None or df.empty:
                    if attempt < max_retries:
                        time.sleep(attempt * 2)
                        continue
                    return None

                prices = pd.to_numeric(df['成交价'], errors='coerce').fillna(0)
                volumes = pd.to_numeric(df['手数'], errors='coerce').fillna(0)
                times = df['时间'].astype(str).tolist()

                pv_sum = (prices * volumes).sum()
                vol_sum = volumes.sum()
                vwap = pv_sum / vol_sum if vol_sum > 0 else 0

                return {
                    'times': times,
                    'prices': prices.tolist(),
                    'vwap': round(float(vwap), 3),
                }
            except Exception as e:
                if attempt < max_retries:
                    wait = attempt * 2
                    print(f"  [提示] 获取指数{symbol}分时数据失败(第{attempt}次): {e}，{wait}秒后重试...")
                    time.sleep(wait)
                else:
                    print(f"  [提示] 获取指数{symbol}分时数据失败(已重试{max_retries}次): {e}")
                    return None

    # ========== 个股多日资金流趋势 ==========

    def get_stock_fund_flow_history(self, code: str, days: int = 5) -> Optional[Dict]:
        """
        获取个股近N日主力资金流趋势

        Args:
            code: 股票代码（6位纯数字）
            days: 回看天数（默认5日）

        Returns:
            {consecutive_inflow_days, total_net_inflow, daily_flows: [{date, net_inflow}, ...]}
            获取失败返回 None
        """
        for attempt in range(1, 4):
            try:
                df = ak.stock_individual_fund_flow(stock=code, market='sh' if code.startswith('6') else 'sz')
                if df is None or df.empty:
                    if attempt < 3:
                        time.sleep(attempt * 1)
                        continue
                    return None

                # 取最近days天数据
                df = df.tail(days)

                daily_flows = []
                consecutive_inflow = 0
                total_net = 0.0

                for _, row in df.iterrows():
                    date_str = str(row.get('日期', row.get('date', '')))
                    net_inflow = _parse_amount(row.get('主力净流入-净额', row.get('净流入', 0)))
                    daily_flows.append({
                        'date': date_str,
                        'net_inflow': net_inflow,
                    })
                    total_net += net_inflow

                # 从最新日往前数连续净流入天数
                for flow in reversed(daily_flows):
                    if flow['net_inflow'] > 0:
                        consecutive_inflow += 1
                    else:
                        break

                return {
                    'consecutive_inflow_days': consecutive_inflow,
                    'total_net_inflow': total_net,
                    'daily_flows': daily_flows,
                }
            except Exception as e:
                if attempt < 3:
                    time.sleep(attempt * 1)
                else:
                    print(f"  [提示] 获取{code}多日资金流失败: {e}")
                    return None

    # ========== 北向资金 ==========

    def get_northbound_flow(self, code: str, timeout: float = 10.0) -> Optional[Dict]:
        """
        获取个股北向资金数据

        Args:
            code: 股票代码（6位纯数字）
            timeout: 超时时间（秒），默认10秒

        Returns:
            {net_buy: float, is_buying: bool} 当日北向净买入额
            获取失败、超时或数据过期返回 None
        """
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

        def _fetch():
            df = ak.stock_hsgt_individual_em(symbol=code)
            return df

        for attempt in range(1, 3):  # 最多2次尝试
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(_fetch)
                    df = future.result(timeout=timeout)

                if df is None or df.empty:
                    continue

                # 检查数据是否过期（最新日期应在近7天内）
                latest_date_str = str(df.iloc[-1].get('持股日期', ''))
                try:
                    from datetime import datetime, timedelta
                    latest_date = datetime.strptime(latest_date_str, '%Y-%m-%d')
                    if datetime.now() - latest_date > timedelta(days=7):
                        return None  # 数据过期，不使用
                except (ValueError, TypeError):
                    pass

                # 取最新一条，字段名为'今日增持资金'
                row = df.iloc[-1]
                net_buy = float(pd.to_numeric(row.get('今日增持资金', 0), errors='coerce') or 0)

                return {
                    'net_buy': net_buy,
                    'is_buying': net_buy > 0,
                }
            except FuturesTimeout:
                print(f"  [提示] 获取{code}北向资金超时(>{timeout}秒)，跳过")
                return None
            except KeyboardInterrupt:
                raise
            except Exception as e:
                if attempt < 2:
                    time.sleep(attempt * 1)
                else:
                    print(f"  [提示] 获取{code}北向资金失败: {e}")
                    return None
        return None

    # ========== K线数据（缩量横盘检测用）==========

    def get_stock_kline(self, stock_code: str, days: int = 30) -> Optional[Dict]:
        """
        获取个股近N日K线数据（用于缩量横盘检测）
        优先使用新浪源（stock_zh_a_daily），东方财富源作为备选
        返回: {code, klines: [{date, open, close, high, low, volume}, ...]}
        """
        # 方案1: 新浪源（不受东方财富域名封锁影响）
        try:
            result = self._get_kline_sina(stock_code, days)
            if result:
                return result
        except Exception:
            pass

        # 方案2: 东方财富源
        try:
            df = ak.stock_zh_a_hist(symbol=stock_code, period='daily', adjust='qfq')
            if df is not None and len(df) >= days:
                df = df.tail(days)
                klines = []
                for _, row in df.iterrows():
                    klines.append({
                        'date': str(row.get('日期', '')),
                        'open': float(pd.to_numeric(row.get('开盘', 0), errors='coerce') or 0),
                        'close': float(pd.to_numeric(row.get('收盘', 0), errors='coerce') or 0),
                        'high': float(pd.to_numeric(row.get('最高', 0), errors='coerce') or 0),
                        'low': float(pd.to_numeric(row.get('最低', 0), errors='coerce') or 0),
                        'volume': float(pd.to_numeric(row.get('成交量', 0), errors='coerce') or 0),
                    })
                return {'code': stock_code, 'klines': klines}
        except Exception:
            pass

        return None

    def _get_kline_sina(self, stock_code: str, days: int = 30) -> Optional[Dict]:
        """新浪源K线数据（stock_zh_a_daily）"""
        # 新浪源代码格式：sz000001 / sh600519
        prefix = _code_to_sina_prefix(stock_code)
        df = ak.stock_zh_a_daily(symbol=prefix, adjust='qfq')
        if df is None or len(df) < days:
            return None

        df = df.tail(days)
        klines = []
        for _, row in df.iterrows():
            klines.append({
                'date': str(row.get('date', '')),
                'open': float(pd.to_numeric(row.get('open', 0), errors='coerce') or 0),
                'close': float(pd.to_numeric(row.get('close', 0), errors='coerce') or 0),
                'high': float(pd.to_numeric(row.get('high', 0), errors='coerce') or 0),
                'low': float(pd.to_numeric(row.get('low', 0), errors='coerce') or 0),
                'volume': float(pd.to_numeric(row.get('volume', 0), errors='coerce') or 0),
            })

        return {'code': stock_code, 'klines': klines}


# 全局数据获取器实例
fetcher = DataFetcher()


if __name__ == '__main__':
    # 测试数据获取
    print("测试数据源状态...")
    status = get_data_source_status()
    print(f"当前数据源: {status}")

    print("\n测试批量获取资金流向...")
    results = fetcher.get_money_flow_batch(count=10)
    print(f"获取到 {len(results)} 只股票")

    if results:
        item = results[0]
        print(f"\n股票: {item['name']} ({item['code']})")
        print(f"净额: {item['main_force_inflow']:,.0f} ({item['main_force_ratio']:.2f}%)")
        print(f"流入: {item['inflow']:,.0f}  流出: {item['outflow']:,.0f}")

    print("\n测试实时行情秒级刷新...")
    if results:
        codes = [r['code'] for r in results[:10]]
        t0 = time.time()
        quotes = fetcher.refresh_realtime_quotes(codes)
        elapsed = time.time() - t0
        print(f"刷新 {len(quotes)} 只股票，耗时 {elapsed:.2f}秒")
        for code, q in list(quotes.items())[:3]:
            print(f"  {q['name']}({code}): 价格={q['price']}, 涨幅={q['change_pct']}%")
