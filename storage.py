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