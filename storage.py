"""SQLite存储层 - 涨停池数据持久化"""
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

DB_PATH = Path(__file__).parent / "database" / "zt_pool.db"


@contextmanager
def get_connection():
    """获取数据库连接的上下文管理器"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_database():
    """初始化数据库 - 执行schema"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    schema_path = Path(__file__).parent / "database" / "schema.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = f.read()
    with get_connection() as conn:
        conn.executescript(schema)


class ZtPoolStorage:
    """涨停池存储操作"""

    @staticmethod
    def save_zt_pool(stocks: list[dict], date: str) -> int:
        """保存涨停池数据，返回插入/更新数量"""
        with get_connection() as conn:
            cursor = conn.cursor()
            count = 0
            for stock in stocks:
                cursor.execute("""
                    INSERT INTO zt_pool_history
                    (stock_code, stock_name, date, close_price, change_pct,
                     seal_amount, seal_count, explosion_count, continuous_days,
                     sector, sector_change_pct, super_net_inflow, big_net_inflow, main_net_inflow)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(stock_code, date) DO UPDATE SET
                        stock_name = excluded.stock_name,
                        close_price = excluded.close_price,
                        change_pct = excluded.change_pct,
                        seal_amount = excluded.seal_amount,
                        seal_count = excluded.seal_count,
                        explosion_count = excluded.explosion_count,
                        continuous_days = excluded.continuous_days,
                        sector = excluded.sector,
                        sector_change_pct = excluded.sector_change_pct,
                        super_net_inflow = excluded.super_net_inflow,
                        big_net_inflow = excluded.big_net_inflow,
                        main_net_inflow = excluded.main_net_inflow,
                        created_at = datetime('now', 'localtime')
                """, (
                    stock["code"], stock["name"], date,
                    stock.get("close"), stock.get("change_pct"),
                    stock.get("seal_amount"), stock.get("seal_count"),
                    stock.get("explosion_count", 0), stock.get("continuous_days", 1),
                    stock.get("sector"), stock.get("sector_change_pct"),
                    stock.get("super_net_inflow"), stock.get("big_net_inflow"),
                    stock.get("main_net_inflow")
                ))
                count += 1
            conn.commit()
            return count

    @staticmethod
    def get_today_zt_pool() -> list[dict]:
        """获取今日涨停池"""
        today = datetime.now().strftime("%Y-%m-%d")
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM zt_pool_history
                WHERE date = ?
                ORDER BY continuous_days DESC, seal_amount DESC
            """, (today,))
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_yesterday_zt_pool() -> list[dict]:
        """获取昨日涨停池（用于计算昨涨停今日表现）"""
        today = datetime.now()
        yesterday = (today.replace(day=today.day - 1)).strftime("%Y-%m-%d")
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT stock_code, stock_name, date FROM zt_pool_history
                WHERE date = ?
            """, (yesterday,))
            return [dict(row) for row in cursor.fetchall()]


class SectorStorage:
    """板块信息存储操作"""

    @staticmethod
    def save_sector_ranking(sectors: list[dict], date: str) -> int:
        """保存板块排名数据"""
        with get_connection() as conn:
            cursor = conn.cursor()
            count = 0
            for sector in sectors:
                cursor.execute("""
                    INSERT INTO sector_info (sector_name, date, change_pct, zt_count)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(sector_name, date) DO UPDATE SET
                        change_pct = excluded.change_pct,
                        zt_count = excluded.zt_count,
                        updated_at = datetime('now', 'localtime')
                """, (sector["name"], date, sector.get("change_pct"), sector.get("zt_count", 0)))
                count += 1
            conn.commit()
            return count

    @staticmethod
    def get_top_sectors(limit: int = 5) -> list[dict]:
        """获取涨幅前N的板块"""
        today = datetime.now().strftime("%Y-%m-%d")
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM sector_info
                WHERE date = ?
                ORDER BY change_pct DESC
                LIMIT ?
            """, (today, limit))
            return [dict(row) for row in cursor.fetchall()]


class YesterdayZtPerformance:
    """昨日涨停今日表现分析"""

    @staticmethod
    def get_yesterday_zt_codes() -> list[dict]:
        """获取最近一个有涨停数据的日期的涨停股"""
        with get_connection() as conn:
            cursor = conn.cursor()
            # 查找最近一个有涨停数据的交易日
            cursor.execute("""
                SELECT DISTINCT date FROM zt_pool_history
                WHERE date < date('now', 'localtime')
                ORDER BY date DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            if not row:
                return []

            latest_date = row['date']
            cursor.execute("""
                SELECT stock_code, stock_name, change_pct as yesterday_change
                FROM zt_pool_history
                WHERE date = ?
            """, (latest_date,))
            return [dict(r) for r in cursor.fetchall()]

    @staticmethod
    def calculate_performance(stock_codes: list[str], current_prices: dict[str, float]) -> dict:
        """
        计算昨日涨停股今日表现

        Args:
            stock_codes: 昨日涨停股代码列表
            current_prices: {code: (current_price, prev_close_price)}

        Returns:
            {
                "yesterday_zt_count": int,     # 昨日涨停股总数
                "today_up_count": int,         # 今日上涨数
                "today_down_count": int,       # 今日下跌数
                "today_flat_count": int,      # 今日平盘数
                "today_change_avg": float,     # 今日平均涨幅
                "momentum_score": str,       # 情绪评分: "极好"/"较好"/"中性"/"较差"/"极差"
            }
        """
        if not stock_codes:
            return {
                "yesterday_zt_count": 0,
                "today_up_count": 0,
                "today_down_count": 0,
                "today_flat_count": 0,
                "today_change_avg": 0,
                "momentum_score": "中性"
            }

        up_count = 0
        down_count = 0
        flat_count = 0
        total_change = 0
        valid_count = 0

        for code in stock_codes:
            if code in current_prices:
                current, prev_close = current_prices[code]
                if prev_close > 0:
                    change_pct = (current - prev_close) / prev_close * 100
                    total_change += change_pct
                    valid_count += 1

                    if change_pct > 0.1:
                        up_count += 1
                    elif change_pct < -0.1:
                        down_count += 1
                    else:
                        flat_count += 1

        avg_change = total_change / valid_count if valid_count > 0 else 0

        # 情绪评分
        if valid_count == 0:
            momentum_score = "中性"
        elif valid_count >= 5:
            up_rate = up_count / valid_count
            if up_rate >= 0.7 and avg_change >= 2:
                momentum_score = "极好"
            elif up_rate >= 0.5 and avg_change >= 1:
                momentum_score = "较好"
            elif up_rate >= 0.4:
                momentum_score = "中性"
            elif up_rate >= 0.3 and avg_change >= -1:
                momentum_score = "较差"
            else:
                momentum_score = "极差"
        else:
            momentum_score = "中性"

        return {
            "yesterday_zt_count": len(stock_codes),
            "today_up_count": up_count,
            "today_down_count": down_count,
            "today_flat_count": flat_count,
            "today_change_avg": round(avg_change, 2),
            "momentum_score": momentum_score
        }


# 保留原始的8因子预测器用于兼容
class ZtPredictor:
    """次日涨跌预测分析器 - 基于8因子评分模型 (兼容旧版本)"""

    FEATURE_WEIGHTS = {
        "main_inflow": 0.20, "yesterday_performance": 0.20, "seal_amount": 0.15,
        "continuous_days": 0.12, "sector_change": 0.10, "explosion_count": 0.10,
        "turnover": 0.08, "market_cap": 0.05
    }

    PERFORMANCE_SCORES = {"极好": 100, "较好": 80, "中性": 60, "较差": 40, "极差": 20}

    @classmethod
    def calculate_prediction(cls, stock: dict, context: dict) -> dict:
        features = cls._extract_features(stock, context)
        score = cls._calculate_score(features)
        up_prob, down_prob = cls._calculate_probability(score, features)
        recommendation = cls._get_recommendation(score, up_prob)
        return {"factors": {"main_inflow": features["main_inflow"]}, "prediction": {"score": score, "up_probability": round(up_prob, 2), "down_probability": round(down_prob, 2), "recommendation": recommendation}}

    @classmethod
    def _extract_features(cls, stock: dict, context: dict) -> dict:
        main_inflow = stock.get("main_net_inflow", 0) or 0
        seal_amount = stock.get("seal_amount", 0) or 0
        continuous_days = stock.get("continuous_days", 1) or 1
        explosion_count = stock.get("explosion_count", 0) or 0
        perf_key = context.get("momentum_score", "中性")
        return {"main_inflow": main_inflow, "seal_amount": seal_amount, "continuous_days": continuous_days, "explosion_count": explosion_count, "yesterday_performance": perf_key}

    @classmethod
    def _calculate_score(cls, features: dict) -> int:
        scores = {"main_inflow_score": min(features["main_inflow"] / 100, 100), "seal_score": min(features["seal_amount"] / 500, 100), "continuous_score": min(features["continuous_days"] * 25, 100), "explosion_score": max(100 - features["explosion_count"] * 30, 0), "perf_score": cls.PERFORMANCE_SCORES.get(features["yesterday_performance"], 60)}
        total = sum(scores.get(k.replace("_score", ""), 50) * v for k, v in cls.FEATURE_WEIGHTS.items() if k != "yesterday_performance")
        return min(int(total + scores["perf_score"] * 0.20), 100)

    @classmethod
    def _calculate_probability(cls, score: int, features: dict) -> tuple:
        up_base = score / 100 * 0.85
        down_base = (100 - score) / 100 * 0.75
        flat_prob = max(1 - up_base - down_base, 0.05)
        total = up_base + down_base + flat_prob
        return up_base / total, down_base / total

    @classmethod
    def _get_recommendation(cls, score: int, up_prob: float) -> str:
        if up_prob >= 0.70 and score >= 80: return "强烈推荐"
        elif up_prob >= 0.55 and score >= 60: return "推荐"
        elif up_prob >= 0.45: return "观察"
        return "谨慎"

    @classmethod
    def get_top_predictions(cls, limit: int = 10) -> list:
        today_zt = ZtPoolStorage.get_today_zt_pool()
        if not today_zt: return []
        top_sectors = SectorStorage.get_top_sectors(5)
        context = {"sectors": top_sectors, "momentum_score": "中性"}
        predictions = [{"stock_code": s.get("code") or s.get("stock_code", ""), "stock_name": s.get("name") or s.get("stock_name", ""), "continuous_days": s.get("continuous_days", 1) or 1, "sector": s.get("sector", ""), **cls.calculate_prediction(s, context)} for s in today_zt]
        predictions.sort(key=lambda x: x["prediction"]["score"], reverse=True)
        return predictions[:limit]

    @classmethod
    def analyze_stock(cls, stock_code: str) -> dict:
        today_zt = ZtPoolStorage.get_today_zt_pool()
        stock = next((s for s in today_zt if (s.get("code") or s.get("stock_code", "")) == stock_code), None)
        if not stock:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM zt_pool_history WHERE stock_code = ? ORDER BY date DESC LIMIT 1", (stock_code,))
                row = cursor.fetchone()
                if row: stock = dict(row)
        if not stock: return {"error": "股票未找到"}
        result = cls.calculate_prediction(stock, {"sectors": [], "momentum_score": "中性"})
        return {"stock_code": stock.get("code") or stock.get("stock_code", ""), "stock_name": stock.get("name") or stock.get("stock_name", ""), "today_zt": True, **result}


class ExtendedZtPredictor:
    """
    次日涨跌预测分析器 - 基于30+因子评分模型

    因子类别:
    1. 涨停质量因子 (4个) - 涨停时间、形态、封单强度、尾盘标识
    2. 资金行为因子 (4个) - 超大单占比、连续净买入、散户占比、主力占比
    3. 市场环境因子 (4个) - 涨跌停比、板块梯队、龙头联动、相对强弱
    4. 技术形态因子 (6个) - 量价齐升、均线多头、RSI、突破前高、布林带、MACD
    5. 历史规律因子 (3个) - 历史涨停次数、次溢价率、股性评分
    6. 盘口数据因子 (3个) - 委比、内外盘比、尾盘动量
    7. 北向资金因子 (3个) - 北向净买入、北向持续天数、持仓变化
    """

    # 昨涨停表现分数映射
    PERFORMANCE_SCORES = {
        "极好": 100, "较好": 80, "中性": 60, "较差": 40, "极差": 20
    }

    @classmethod
    def calculate_prediction(cls, stock: dict, context: 'BatchContext', data_fetcher=None) -> dict:
        """
        计算单只股票的次日涨跌预测 (扩展版30+因子)

        Args:
            stock: 股票数据
            context: BatchContext 批量上下文
            data_fetcher: 数据获取器实例

        Returns:
            预测结果字典 (包含所有因子分数)
        """
        scores = {}

        # ========== 1. 涨停质量因子 (4个) ==========
        scores.update(cls._calc_seal_quality(stock, context))

        # ========== 2. 资金行为因子 (4个) ==========
        scores.update(cls._calc_capital_behavior(stock, context))

        # ========== 3. 市场环境因子 (4个) ==========
        scores.update(cls._calc_market_environment(stock, context, data_fetcher))

        # ========== 4. 技术形态因子 (6个) ==========
        scores.update(cls._calc_technical(stock, context, data_fetcher))

        # ========== 5. 历史规律因子 (3个) ==========
        scores.update(cls._calc_historical(stock))

        # ========== 6. 盘口数据因子 (3个) ==========
        scores.update(cls._calc_order_book(stock, context, data_fetcher))

        # ========== 7. 北向资金因子 (3个) ==========
        scores.update(cls._calc_northbound(stock, context, data_fetcher))

        # ========== 计算综合评分 ==========
        total_score = cls._calculate_weighted_score(scores)
        up_prob, down_prob = cls._calculate_probability(total_score, scores)
        recommendation = cls._get_recommendation(total_score, up_prob)

        return {
            "factors": scores,
            "prediction": {
                "score": total_score,
                "up_probability": round(up_prob, 2),
                "down_probability": round(down_prob, 2),
                "flat_probability": round(1 - up_prob - down_prob, 2),
                "recommendation": recommendation
            }
        }

    # ========== 涨停质量因子 ==========

    @classmethod
    def _calc_seal_quality(cls, stock: dict, context: 'BatchContext') -> dict:
        """计算涨停质量因子"""
        return {
            "seal_time_score": cls._normalize_seal_time(stock.get("first_seal_time")),
            "seal_pattern_score": cls._normalize_seal_pattern(stock),
            "seal_strength_score": cls._normalize_seal_strength(
                stock.get("seal_amount"), stock.get("circulation_market_cap")
            ),
            "late_seal_score": cls._normalize_late_seal(stock.get("last_seal_time"))
        }

    @classmethod
    def _normalize_seal_time(cls, first_seal_time: str) -> float:
        """归一化涨停时间: 开盘~9:30=100, 9:30~10:00=80, 10:00~13:00=60, >13:00=40"""
        if not first_seal_time:
            return 50.0
        try:
            parts = first_seal_time.split(':')
            hour = int(parts[0])
            minute = int(parts[1])
            total_minutes = hour * 60 + minute
            if total_minutes <= 9 * 60 + 30:
                return 100.0
            elif total_minutes <= 10 * 60:
                return 80.0
            elif total_minutes <= 13 * 60:
                return 60.0
            else:
                return 40.0
        except:
            return 50.0

    @classmethod
    def _normalize_seal_pattern(cls, stock: dict) -> float:
        """归一化涨停形态: 一字板=100, T字板=80, 实体板=60"""
        try:
            open_price = stock.get("open", 0) or 0
            high = stock.get("high", 0) or 0
            low = stock.get("low", 0) or 0
            close = stock.get("close", 0) or stock.get("price", 0) or 0

            if not all([open_price, high, low, close]):
                return 50.0

            # 一字板: 开盘=最高=最低
            if abs(open_price - high) < 0.01 and abs(open_price - low) < 0.01:
                return 100.0

            # T字板: 开板后回封 (最低<开盘, 收盘=最高)
            if abs(close - high) < 0.01 and low < open_price:
                return 80.0

            # 实体板
            return 60.0
        except:
            return 50.0

    @classmethod
    def _normalize_seal_strength(cls, seal_amount: float, circulation_cap: float) -> float:
        """归一化封单强度比: >5%=100, 3~5%=80, 1~3%=60, <1%=40"""
        try:
            if not seal_amount or not circulation_cap or circulation_cap == 0:
                return 50.0
            ratio = seal_amount / circulation_cap * 100
            if ratio >= 5:
                return 100.0
            elif ratio >= 3:
                return 80.0
            elif ratio >= 1:
                return 60.0
            else:
                return 40.0
        except:
            return 50.0

    @classmethod
    def _normalize_late_seal(cls, last_seal_time: str) -> float:
        """归一化尾盘封板: 10:00前=100, 14:00前=70, 14:30前=50, >14:30=20"""
        if not last_seal_time:
            return 50.0
        try:
            parts = last_seal_time.split(':')
            hour = int(parts[0])
            minute = int(parts[1])
            total_minutes = hour * 60 + minute
            if total_minutes <= 10 * 60:
                return 100.0
            elif total_minutes <= 14 * 60:
                return 70.0
            elif total_minutes <= 14 * 60 + 30:
                return 50.0
            else:
                return 20.0
        except:
            return 50.0

    # ========== 资金行为因子 ==========

    @classmethod
    def _calc_capital_behavior(cls, stock: dict, context: 'BatchContext') -> dict:
        """计算资金行为因子"""
        code = stock.get("code") or stock.get("stock_code", "")
        money_flow = context.get_money_flow(code)
        fund_history = context._fund_flow_cache.get(code, {}) if hasattr(context, '_fund_flow_cache') else {}

        return {
            "super_large_ratio_score": cls._normalize_super_large_ratio(
                money_flow.get("super_large_ratio", 0)
            ),
            "consecutive_inflow_score": cls._normalize_consecutive_inflow(
                fund_history.get("consecutive_inflow_days", 0)
            ),
            "small_ratio_score": cls._normalize_small_ratio(
                money_flow.get("small_ratio", 0)
            ),
            "main_force_ratio_score": cls._normalize_main_force_ratio(
                money_flow.get("main_force_ratio", money_flow.get("main_force_inflow", 0))
            )
        }

    @classmethod
    def _normalize_super_large_ratio(cls, ratio: float) -> float:
        """归一化超大单净占比: >15%=100, 10~15%=80, 5~10%=60, <5%=40"""
        if ratio >= 15:
            return 100.0
        elif ratio >= 10:
            return 80.0
        elif ratio >= 5:
            return 60.0
        else:
            return 40.0

    @classmethod
    def _normalize_consecutive_inflow(cls, days: int) -> float:
        """归一化连续净买入天数: >=5天=100, 3~4天=80, 2天=60, 1天=40, 0天=20"""
        if days >= 5:
            return 100.0
        elif days >= 3:
            return 80.0
        elif days == 2:
            return 60.0
        elif days == 1:
            return 40.0
        else:
            return 20.0

    @classmethod
    def _normalize_small_ratio(cls, ratio: float) -> float:
        """归一化散户资金占比 (反向指标): <10%=100, 10~20%=60, >20%=30"""
        if ratio < 10:
            return 100.0
        elif ratio < 20:
            return 60.0
        else:
            return 30.0

    @classmethod
    def _normalize_main_force_ratio(cls, value: float) -> float:
        """归一化主力资金占比: >20%=100, 15~20%=80, 10~15%=60, <10%=40"""
        if isinstance(value, str):
            return 50.0
        if value >= 20:
            return 100.0
        elif value >= 15:
            return 80.0
        elif value >= 10:
            return 60.0
        else:
            return 40.0

    # ========== 市场环境因子 ==========

    @classmethod
    def _calc_market_environment(cls, stock: dict, context: 'BatchContext', fetcher=None) -> dict:
        """计算市场环境因子"""
        sector = stock.get("industry") or stock.get("sector") or ""
        sector_zt_count = context.get_sector_zt_count(sector) if hasattr(context, 'get_sector_zt_count') else 0

        # 计算市场涨跌停比
        zt_ratio = context.market_zt_count / max(context.market_dt_count, 1)

        # 相对强弱
        quote = context.get_realtime_quote(stock.get("code") or stock.get("stock_code", ""))
        stock_change = stock.get("change_pct", 0) or quote.get("change_pct", 0) if quote else 0
        relative_strength = stock_change - context.index_change

        return {
            "market_zt_ratio_score": cls._normalize_market_ratio(zt_ratio),
            "sector_team_score": cls._normalize_sector_team(sector_zt_count),
            "leader_link_score": cls._normalize_leader_link(sector, context),
            "relative_strength_score": cls._normalize_relative_strength(relative_strength)
        }

    @classmethod
    def _normalize_market_ratio(cls, ratio: float) -> float:
        """归一化市场涨跌停比: >5=100, 3~5=80, 1~3=60, <1=30"""
        if ratio >= 5:
            return 100.0
        elif ratio >= 3:
            return 80.0
        elif ratio >= 1:
            return 60.0
        else:
            return 30.0

    @classmethod
    def _normalize_sector_team(cls, count: int) -> float:
        """归一化板块梯队完整性: >=5只=100, 3~4只=80, 2只=60, 1只=40"""
        if count >= 5:
            return 100.0
        elif count >= 3:
            return 80.0
        elif count >= 2:
            return 60.0
        else:
            return 40.0

    @classmethod
    def _normalize_leader_link(cls, sector: str, context: 'BatchContext') -> float:
        """归一化龙头股联动: 龙头涨停=100, 板块平均=50, 龙头下跌=20"""
        if not sector:
            return 50.0
        # 简化处理: 如果同板块有多只涨停，认为有联动
        sector_count = context.get_sector_zt_count(sector) if hasattr(context, 'get_sector_zt_count') else 0
        if sector_count >= 3:
            return 100.0
        elif sector_count >= 2:
            return 70.0
        elif sector_count >= 1:
            return 50.0
        else:
            return 30.0

    @classmethod
    def _normalize_relative_strength(cls, diff: float) -> float:
        """归一化相对强弱: 跑赢>2%=100, 跑赢=80, 跟随=50, 跑输=30"""
        if diff > 2:
            return 100.0
        elif diff > 0:
            return 80.0
        elif diff > -2:
            return 50.0
        else:
            return 30.0

    # ========== 技术形态因子 ==========

    @classmethod
    def _calc_technical(cls, stock: dict, context: 'BatchContext', fetcher=None) -> dict:
        """计算技术形态因子"""
        code = stock.get("code") or stock.get("stock_code", "")

        # 获取技术指标
        if fetcher:
            try:
                tech = fetcher.get_stock_technical(code) or {}
            except:
                tech = {}
        else:
            tech = {}

        # 获取K线数据用于计算RSI/MACD
        if fetcher:
            try:
                kline = fetcher.get_stock_kline(code, 30) or {}
            except:
                kline = {}
        else:
            kline = {}

        # 量价齐升
        volume_ratio = tech.get("volume_ratio", 0) or 0
        price_up = stock.get("change_pct", 0) or 0
        volume_price_score = 100 if (volume_ratio > 1.5 and price_up > 0) else (60 if (volume_ratio > 1 or price_up > 0) else 40)

        return {
            "volume_price_momentum_score": volume_price_score,
            "ma_bull_score": 100 if tech.get("mav_bull") else 30,
            "rsi_score": cls._normalize_rsi(kline),
            "breakout_score": cls._normalize_breakout(stock, kline),
            "boll_position_score": cls._normalize_bollinger(kline),
            "macd_signal_score": cls._normalize_macd(kline)
        }

    @classmethod
    def _normalize_rsi(cls, kline: dict) -> float:
        """归一化RSI状态: 40~60=100, 30~40或60~70=70, 其他=50"""
        try:
            klines = kline.get("klines", [])
            if len(klines) < 7:
                return 50.0
            closes = [k.get("close", 0) for k in klines[-7:]]
            deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
            gains = [d if d > 0 else 0 for d in deltas]
            losses = [-d if d < 0 else 0 for d in deltas]
            avg_gain = sum(gains) / 6
            avg_loss = sum(losses) / 6
            if avg_loss == 0:
                return 100.0
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            if 40 <= rsi <= 60:
                return 100.0
            elif 30 <= rsi < 40 or 60 < rsi <= 70:
                return 70.0
            else:
                return 50.0
        except:
            return 50.0

    @classmethod
    def _normalize_breakout(cls, stock: dict, kline: dict) -> float:
        """归一化突破前高: 突破20日高点=100, 接近=70, 远离=40"""
        try:
            current_price = stock.get("close", 0) or stock.get("price", 0) or 0
            klines = kline.get("klines", [])
            if len(klines) < 20 or current_price == 0:
                return 50.0
            high_20 = max(k.get("high", 0) for k in klines[-20:])
            if current_price > high_20:
                return 100.0
            elif current_price >= high_20 * 0.95:
                return 70.0
            else:
                return 40.0
        except:
            return 50.0

    @classmethod
    def _normalize_bollinger(cls, kline: dict) -> float:
        """归一化布林带位置: 中轨上方=100, 上轨附近=80, 下轨=40"""
        try:
            klines = kline.get("klines", [])
            if len(klines) < 20:
                return 50.0
            closes = [k.get("close", 0) for k in klines[-20:]]
            ma20 = sum(closes) / 20
            std = (sum((c - ma20) ** 2 for c in closes) / 20) ** 0.5
            upper = ma20 + 2 * std
            lower = ma20 - 2 * std
            current = closes[-1]
            if upper == lower:
                return 50.0
            position = (current - lower) / (upper - lower) * 100
            if position >= 50:
                return 100.0
            elif position >= 30:
                return 70.0
            else:
                return 40.0
        except:
            return 50.0

    @classmethod
    def _normalize_macd(cls, kline: dict) -> float:
        """归一化MACD信号: 金叉=100, 零轴上方=80, 零轴下方=60, 死叉=30"""
        try:
            klines = kline.get("klines", [])
            if len(klines) < 27:
                return 50.0
            closes = [k.get("close", 0) for k in klines]

            def ema(data, period):
                k = 2 / (period + 1)
                ema_val = data[0]
                for price in data[1:]:
                    ema_val = price * k + ema_val * (1 - k)
                return ema_val

            ema12 = ema(closes, 12)
            ema26 = ema(closes, 26)
            dif = ema12 - ema26

            if dif > 0:
                return 100.0
            elif dif > -0.5:
                return 70.0
            else:
                return 30.0
        except:
            return 50.0

    # ========== 历史规律因子 ==========

    @classmethod
    def _calc_historical(cls, stock: dict) -> dict:
        """计算历史规律因子"""
        code = stock.get("code") or stock.get("stock_code", "")

        # 从数据库获取历史统计
        stats = cls._get_stock_statistics(code)

        return {
            "hist_zt_count_score": cls._normalize_hist_zt_count(stats.get("total_zt_count", 0)),
            "hist_premium_score": cls._normalize_hist_premium(stats.get("avg_next_day_change", 0)),
            "volatility_score": cls._normalize_volatility(stats.get("volatility_score", 50))
        }

    @classmethod
    def _get_stock_statistics(cls, code: str) -> dict:
        """获取股票历史统计"""
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM stock_zt_statistics WHERE stock_code = ?", (code,))
                row = cursor.fetchone()
                if row:
                    return dict(row)
        except:
            pass
        return {}

    @classmethod
    def _normalize_hist_zt_count(cls, count: int) -> float:
        """归一化历史涨停次数: >=10次=100, 5~9次=80, 2~4次=60, 1次=40, 0次=20"""
        if count >= 10:
            return 100.0
        elif count >= 5:
            return 80.0
        elif count >= 2:
            return 60.0
        elif count >= 1:
            return 40.0
        else:
            return 20.0

    @classmethod
    def _normalize_hist_premium(cls, avg_change: float) -> float:
        """归一化历史次溢价率: >=5%=100, 3~5%=80, 0~3%=60, <0%=30"""
        if avg_change >= 5:
            return 100.0
        elif avg_change >= 3:
            return 80.0
        elif avg_change >= 0:
            return 60.0
        else:
            return 30.0

    @classmethod
    def _normalize_volatility(cls, score: float) -> float:
        """归一化股性评分: 适度波动=100, 低波动=60, 高波动=40"""
        if 40 <= score <= 70:
            return 100.0
        elif score < 40:
            return 60.0
        else:
            return 40.0

    # ========== 盘口数据因子 ==========

    @classmethod
    def _calc_order_book(cls, stock: dict, context: 'BatchContext', fetcher=None) -> dict:
        """计算盘口数据因子 - 使用缓存数据，避免额外API调用"""
        code = stock.get("code") or stock.get("stock_code", "")

        # 使用上下文中的缓存数据（由batch获取）
        order_book = context._order_book_cache.get(code, {}) if hasattr(context, '_order_book_cache') else {}

        committee_ratio = order_book.get("committee_ratio", 0) or 0
        outin_ratio = order_book.get("outin_ratio", 1) or 1

        # 分时数据从上下文缓存获取
        intraday = context._intraday_cache.get(code, {}) if hasattr(context, '_intraday_cache') else {}
        tail_ratio = intraday.get("tail_vol_ratio", 0) or 0

        # 如果缓存为空，使用默认值（不触发额外API调用）
        if committee_ratio == 0 and outin_ratio == 1:
            committee_ratio = 30.0  # 中等委比
            outin_ratio = 1.2  # 略偏多

        return {
            "committee_ratio_score": cls._normalize_committee_ratio(committee_ratio),
            "outin_ratio_score": cls._normalize_outin_ratio(outin_ratio),
            "tail_momentum_score": cls._normalize_tail_momentum(tail_ratio)
        }

    @classmethod
    def _normalize_committee_ratio(cls, ratio: float) -> float:
        """归一化委比: >50%=100, 20~50%=80, 0~20%=60, <0%=30"""
        if ratio > 50:
            return 100.0
        elif ratio > 20:
            return 80.0
        elif ratio > 0:
            return 60.0
        else:
            return 30.0

    @classmethod
    def _normalize_outin_ratio(cls, ratio: float) -> float:
        """归一化内外盘比: >2=100, 1.5~2=80, 1~1.5=60, <1=30"""
        if ratio > 2:
            return 100.0
        elif ratio > 1.5:
            return 80.0
        elif ratio > 1:
            return 60.0
        else:
            return 30.0

    @classmethod
    def _normalize_tail_momentum(cls, ratio: float) -> float:
        """归一化尾盘动量: >2=100, 1.5~2=80, 1~1.5=60, <1=30"""
        if ratio > 2:
            return 100.0
        elif ratio > 1.5:
            return 80.0
        elif ratio > 1:
            return 60.0
        else:
            return 30.0

    # ========== 北向资金因子 ==========

    @classmethod
    def _calc_northbound(cls, stock: dict, context: 'BatchContext', fetcher=None) -> dict:
        """计算北向资金因子 - 使用缓存数据，避免额外API调用"""
        code = stock.get("code") or stock.get("stock_code", "")

        # 使用上下文中的缓存数据
        nb_data = context._northbound_cache.get(code, {}) if hasattr(context, '_northbound_cache') else {}

        net_buy = nb_data.get("net_buy", 0) or 0
        consecutive_days = nb_data.get("consecutive_days", 0) or 0

        # 北向资金数据通常难以获取，使用默认值
        if net_buy == 0 and consecutive_days == 0:
            net_buy = 5000  # 假设中等净买入
            consecutive_days = 1

        return {
            "northbound_netbuy_score": cls._normalize_northbound_netbuy(net_buy),
            "northbound_consecutive_score": cls._normalize_northbound_consecutive(consecutive_days),
            "northbound_hold_change_score": 50.0  # 需要额外数据源，暂时默认值
        }

    @classmethod
    def _normalize_northbound_netbuy(cls, net_buy: float) -> float:
        """归一化北向净买入: >=1亿=100, 5000万~1亿=80, 1000万~5000万=60, <1000万=30"""
        if net_buy >= 10000:  # 万元
            return 100.0
        elif net_buy >= 5000:
            return 80.0
        elif net_buy >= 1000:
            return 60.0
        else:
            return 30.0

    @classmethod
    def _normalize_northbound_consecutive(cls, days: int) -> float:
        """归一化北向持续买入: >=5天=100, 3~4天=80, 2天=60, 1天=40, 0天=20"""
        if days >= 5:
            return 100.0
        elif days >= 3:
            return 80.0
        elif days == 2:
            return 60.0
        elif days == 1:
            return 40.0
        else:
            return 20.0

    # ========== 核心计算方法 ==========

    @classmethod
    def _calculate_weighted_score(cls, scores: dict) -> int:
        """计算加权综合评分"""
        # 因子权重
        weights = {
            # 涨停质量 (30%权重)
            "seal_time_score": 0.08,
            "seal_pattern_score": 0.05,
            "seal_strength_score": 0.10,
            "late_seal_score": 0.07,
            # 资金行为 (20%权重)
            "super_large_ratio_score": 0.10,
            "consecutive_inflow_score": 0.08,
            "small_ratio_score": 0.05,
            "main_force_ratio_score": 0.07,
            # 市场环境 (15%权重)
            "market_zt_ratio_score": 0.06,
            "sector_team_score": 0.07,
            "leader_link_score": 0.05,
            "relative_strength_score": 0.08,
            # 技术形态 (18%权重)
            "volume_price_momentum_score": 0.06,
            "ma_bull_score": 0.05,
            "rsi_score": 0.04,
            "breakout_score": 0.05,
            "boll_position_score": 0.04,
            "macd_signal_score": 0.05,
            # 历史规律 (10%权重)
            "hist_zt_count_score": 0.05,
            "hist_premium_score": 0.07,
            "volatility_score": 0.04,
            # 盘口数据 (10%权重)
            "committee_ratio_score": 0.04,
            "outin_ratio_score": 0.05,
            "tail_momentum_score": 0.06,
            # 北向资金 (7%权重)
            "northbound_netbuy_score": 0.06,
            "northbound_consecutive_score": 0.04,
            "northbound_hold_change_score": 0.03,
        }

        total_score = 0.0
        for factor_name, weight in weights.items():
            score = scores.get(factor_name, 50.0)
            total_score += score * weight

        return min(int(total_score), 100)

    @classmethod
    def _calculate_probability(cls, score: int, scores: dict) -> tuple:
        """计算涨跌概率"""
        up_base = score / 100 * 0.85
        down_base = (100 - score) / 100 * 0.75

        # 根据关键因子调整
        if scores.get("seal_time_score", 50) >= 80:
            up_base = min(up_base + 0.05, 0.95)
        if scores.get("seal_strength_score", 50) >= 80:
            up_base = min(up_base + 0.05, 0.95)
        if scores.get("small_ratio_score", 50) < 40:
            up_base = max(up_base - 0.05, 0.05)
        if scores.get("late_seal_score", 50) < 30:
            down_base = min(down_base + 0.05, 0.90)

        flat_prob = max(1 - up_base - down_base, 0.05)
        total = up_base + down_base + flat_prob

        return up_base / total, down_base / total

    @classmethod
    def _get_recommendation(cls, score: int, up_prob: float) -> str:
        """获取推荐等级"""
        if up_prob >= 0.70 and score >= 80:
            return "强烈推荐"
        elif up_prob >= 0.55 and score >= 60:
            return "推荐"
        elif up_prob >= 0.45:
            return "观察"
        else:
            return "谨慎"

    @classmethod
    def get_top_predictions(cls, limit: int = 10) -> list[dict]:
        """获取今日涨停股预测评分排行 (30+因子版)"""
        from data_batcher import DataBatcher

        today_zt = ZtPoolStorage.get_today_zt_pool()
        if not today_zt:
            return []

        # 准备批量上下文（不使用fetcher避免长时间等待）
        batcher = DataBatcher(None)
        context = batcher.prepare_batch(today_zt)

        predictions = []
        for stock in today_zt:
            try:
                result = cls.calculate_prediction(stock, context, None)
                predictions.append({
                    "stock_code": stock.get("code") or stock.get("stock_code", ""),
                    "stock_name": stock.get("name") or stock.get("stock_name", ""),
                    "continuous_days": stock.get("consecutive_days", 1) or 1,
                    "sector": stock.get("industry") or stock.get("sector", ""),
                    "seal_amount": stock.get("seal_amount", 0),
                    "main_net_inflow": stock.get("main_force_inflow", 0),
                    **result
                })
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"预测失败 {stock.get('code')}: {e}")

        predictions.sort(key=lambda x: x["prediction"]["score"], reverse=True)
        return predictions[:limit]

    @classmethod
    def analyze_stock(cls, stock_code: str, data_fetcher=None) -> dict:
        """分析单只股票的详细预测"""
        from data_batcher import DataBatcher

        today_zt = ZtPoolStorage.get_today_zt_pool()
        stock = None
        for s in today_zt:
            if (s.get("code") or s.get("stock_code", "")) == stock_code:
                stock = s
                break

        if not stock:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM zt_pool_history
                    WHERE stock_code = ?
                    ORDER BY date DESC LIMIT 1
                """, (stock_code,))
                row = cursor.fetchone()
                if row:
                    stock = dict(row)

        if not stock:
            return {"error": "股票未找到"}

        # 准备上下文
        batcher = DataBatcher(data_fetcher)
        context = batcher.prepare_batch([stock])

        result = cls.calculate_prediction(stock, context, data_fetcher)
        return {
            "stock_code": stock.get("code") or stock.get("stock_code", ""),
            "stock_name": stock.get("name") or stock.get("stock_name", ""),
            "today_zt": True,
            **result
        }