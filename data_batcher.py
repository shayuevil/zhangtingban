"""数据批量获取器 - 高效获取预测所需的所有数据"""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class BatchContext:
    """批量获取的数据上下文"""
    # 涨停池基础数据
    zt_pool: List[Dict] = field(default_factory=list)

    # 资金流向 (批量获取一次)
    money_flow: Dict[str, Dict] = field(default_factory=dict)

    # 市场整体数据
    market_zt_count: int = 0
    market_dt_count: int = 0
    index_change: float = 0.0

    # 各因子专用数据 (懒加载缓存)
    _technical_cache: Dict[str, Dict] = field(default_factory=dict)
    _kline_cache: Dict[str, Dict] = field(default_factory=dict)
    _order_book_cache: Dict[str, Dict] = field(default_factory=dict)
    _intraday_cache: Dict[str, Dict] = field(default_factory=dict)
    _northbound_cache: Dict[str, Dict] = field(default_factory=dict)
    _fund_flow_cache: Dict[str, Dict] = field(default_factory=dict)
    _sector_zt_count: Dict[str, int] = field(default_factory=dict)
    _sector_leaders: Dict[str, Dict] = field(default_factory=dict)
    _quotes_cache: Dict[str, Dict] = field(default_factory=dict)

    def get_money_flow(self, code: str) -> Dict:
        """获取单只股票资金流向"""
        return self.money_flow.get(code, {})


class DataBatcher:
    """数据批量获取管理器"""

    def __init__(self, data_fetcher=None):
        self.fetcher = data_fetcher
        self._context: Optional[BatchContext] = None

    def prepare_batch(self, zt_pool: List[Dict], fetcher=None) -> BatchContext:
        """
        批量准备所有需要的上下文数据 (优化版，避免长时间等待)

        Args:
            zt_pool: 今日涨停池数据
            fetcher: 数据获取器实例
        """
        if fetcher is None:
            fetcher = self.fetcher

        if fetcher is None:
            logger.warning("No data fetcher provided, using empty context")
            self._context = BatchContext(zt_pool=zt_pool)
            return self._context

        codes = [s.get("code") or s.get("stock_code") for s in zt_pool]

        # Step 1: 批量获取资金流向 (一次性获取所有股票)
        try:
            money_flow_list = fetcher.get_money_flow_batch(codes, len(codes))
            money_flow_map = {mf.get("code"): mf for mf in money_flow_list if mf.get("code")}
        except Exception as e:
            logger.warning(f"获取资金流向失败: {e}")
            money_flow_map = {}

        # Step 2: 获取市场整体数据 (涨停/跌停家数) - 快速获取
        market_stats = self._get_market_stats(fetcher)

        # Step 3: 获取板块涨停统计
        sector_stats = self._get_sector_zt_count(zt_pool)

        # Step 4: 大盘指数涨跌 - 跳过获取，使用默认值（避免超时）
        index_change = 0.0

        # Step 5: 构建上下文
        self._context = BatchContext(
            zt_pool=zt_pool,
            money_flow=money_flow_map,
            market_zt_count=market_stats.get("zt_count", len(zt_pool)),
            market_dt_count=market_stats.get("dt_count", 10),
            index_change=index_change
        )
        self._context._sector_zt_count = sector_stats

        # Step 6: 批量获取实时报价 (用于计算相对强弱) - 跳过，避免慢速API
        # 使用ZT池中的change_pct作为涨跌
        quotes = {}
        for stock in zt_pool:
            code = stock.get("code") or stock.get("stock_code", "")
            quotes[code] = {
                "change_pct": stock.get("change_pct", 0),
                "price": stock.get("close", 0)
            }
        self._context._quotes_cache = quotes

        # 跳过获取: 盘口数据、分时数据、北向资金、逐个K线
        # 这些数据在预测时会使用默认值

        return self._context

    def _get_market_stats(self, fetcher) -> Dict:
        """获取市场整体统计"""
        try:
            # 获取涨停池作为涨停家数
            zt_pool = fetcher.get_zt_pool()
            zt_count = len(zt_pool)

            # 跌停家数需要单独获取，这里做估算
            # 实际应该通过东方财富接口获取
            dt_count = max(5, zt_count // 10)  # 估算值

            return {
                "zt_count": zt_count,
                "dt_count": dt_count,
                "zt_dt_ratio": zt_count / max(dt_count, 1)
            }
        except Exception as e:
            logger.warning(f"获取市场统计失败: {e}")
            return {"zt_count": 50, "dt_count": 10, "zt_dt_ratio": 5.0}

    def _get_sector_zt_count(self, zt_pool: List[Dict]) -> Dict[str, int]:
        """统计每个板块的涨停股数量"""
        sector_count = {}
        for stock in zt_pool:
            sector = stock.get("industry") or stock.get("sector") or "未知"
            sector_count[sector] = sector_count.get(sector, 0) + 1
        return sector_count

    def get_technical(self, code: str) -> Optional[Dict]:
        """获取技术指标 (带缓存)"""
        if not self._context:
            return None
        if code not in self._context._technical_cache:
            if self.fetcher:
                try:
                    self._context._technical_cache[code] = self.fetcher.get_stock_technical(code) or {}
                except Exception as e:
                    logger.warning(f"获取技术指标失败 {code}: {e}")
                    self._context._technical_cache[code] = {}
            else:
                self._context._technical_cache[code] = {}
        return self._context._technical_cache[code]

    def get_kline(self, code: str, days: int = 30) -> Optional[Dict]:
        """获取K线数据 (带缓存)"""
        if not self._context:
            return None
        cache_key = f"{code}_{days}"
        if cache_key not in self._context._kline_cache:
            if self.fetcher:
                try:
                    self._context._kline_cache[cache_key] = self.fetcher.get_stock_kline(code, days) or {}
                except Exception as e:
                    logger.warning(f"获取K线失败 {code}: {e}")
                    self._context._kline_cache[cache_key] = {}
            else:
                self._context._kline_cache[cache_key] = {}
        return self._context._kline_cache[cache_key]

    def get_order_book(self, code: str) -> Optional[Dict]:
        """获取盘口数据 (带缓存)"""
        if not self._context:
            return None
        if code not in self._context._order_book_cache:
            if self.fetcher:
                try:
                    self._context._order_book_cache[code] = self.fetcher.get_order_book_data(code) or {}
                except Exception as e:
                    logger.warning(f"获取盘口数据失败 {code}: {e}")
                    self._context._order_book_cache[code] = {}
            else:
                self._context._order_book_cache[code] = {}
        return self._context._order_book_cache[code]

    def get_intraday(self, code: str) -> Optional[Dict]:
        """获取分时数据 (带缓存)"""
        if not self._context:
            return None
        if code not in self._context._intraday_cache:
            if self.fetcher:
                try:
                    self._context._intraday_cache[code] = self.fetcher.get_intraday_data(code) or {}
                except Exception as e:
                    logger.warning(f"获取分时数据失败 {code}: {e}")
                    self._context._intraday_cache[code] = {}
            else:
                self._context._intraday_cache[code] = {}
        return self._context._intraday_cache[code]

    def get_northbound(self, code: str) -> Optional[Dict]:
        """获取北向资金数据 (带缓存)"""
        if not self._context:
            return None
        if code not in self._context._northbound_cache:
            if self.fetcher:
                try:
                    self._context._northbound_cache[code] = self.fetcher.get_northbound_flow(code) or {}
                except Exception as e:
                    logger.warning(f"获取北向资金失败 {code}: {e}")
                    self._context._northbound_cache[code] = {}
            else:
                self._context._northbound_cache[code] = {}
        return self._context._northbound_cache[code]

    def get_fund_flow_history(self, code: str) -> Optional[Dict]:
        """获取资金流向历史 (带缓存)"""
        if not self._context:
            return None
        if code not in self._context._fund_flow_cache:
            if self.fetcher:
                try:
                    self._context._fund_flow_cache[code] = self.fetcher.get_stock_fund_flow_history(code, 5) or {}
                except Exception as e:
                    logger.warning(f"获取资金流向历史失败 {code}: {e}")
                    self._context._fund_flow_cache[code] = {}
            else:
                self._context._fund_flow_cache[code] = {}
        return self._context._fund_flow_cache[code]

    def get_realtime_quote(self, code: str) -> Optional[Dict]:
        """获取实时报价"""
        if not self._context:
            return None
        return self._context._quotes_cache.get(code)

    def get_sector_zt_count(self, sector: str) -> int:
        """获取板块涨停股数量"""
        if not self._context:
            return 0
        return self._context._sector_zt_count.get(sector, 0)

    def get_context(self) -> Optional[BatchContext]:
        """获取当前上下文"""
        return self._context


# 为 BatchContext 添加便捷方法
BatchContext.get_realtime_quote = lambda self, code: self._quotes_cache.get(code)
BatchContext.get_money_flow = lambda self, code: self.money_flow.get(code, {})
BatchContext.get_sector_zt_count = lambda self, sector: self._sector_zt_count.get(sector, 0)
