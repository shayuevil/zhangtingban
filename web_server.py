"""FastAPI Web服务器 - 提供API和WebSocket"""
import asyncio
import logging
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from storage import ZtPoolStorage, SectorStorage, YesterdayZtPerformance, ZtPredictor, ExtendedZtPredictor, init_database
from scheduler import start_scheduler
from data_fetcher import DataFetcher

logger = logging.getLogger(__name__)

# FastAPI应用
app = FastAPI(title="A股涨停板池系统", version="1.0.0")

# WebSocket连接管理器
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()

# 全局调度器实例
_scheduler = None


@app.get("/", response_class=HTMLResponse)
async def get_index():
    """返回主页"""
    html_path = Path(__file__).parent / "web_ui" / "index.html"
    return FileResponse(html_path)


@app.get("/api/zt_pool/today")
async def get_today_zt_pool():
    """获取今日涨停池"""
    stocks = ZtPoolStorage.get_today_zt_pool()
    return {"code": 0, "data": stocks, "count": len(stocks)}


@app.get("/api/zt_pool/history")
async def get_history_zt_pool(date: str = None, stock_code: str = None):
    """查询历史涨停池"""
    # 简化实现，后续可扩展
    stocks = ZtPoolStorage.get_today_zt_pool()
    return {"code": 0, "data": stocks}


@app.get("/api/sector/ranking")
async def get_sector_ranking(limit: int = 10):
    """获取板块排名"""
    sectors = SectorStorage.get_top_sectors(limit)
    return {"code": 0, "data": sectors}


@app.get("/api/stats/dashboard")
async def get_dashboard_stats():
    """获取Dashboard统计数据"""
    from data_fetcher import DataFetcher
    from storage import YesterdayZtPerformance

    today_zt = ZtPoolStorage.get_today_zt_pool()

    # 计算统计指标
    total_zt = len(today_zt)
    explosion_count = sum(1 for s in today_zt if s.get("explosion_count", 0) > 0)
    explosion_rate = round(explosion_count / total_zt * 100, 1) if total_zt > 0 else 0

    # 连板股统计
    continuous_stocks = [s for s in today_zt if s.get("continuous_days", 1) > 1]

    # 热门板块
    top_sectors = SectorStorage.get_top_sectors(3)

    # 昨日涨停今日表现
    yesterday_performance = {"momentum_score": "中性", "today_up_count": 0, "today_down_count": 0}
    try:
        fetcher = DataFetcher()
        yesterday_stocks = YesterdayZtPerformance.get_yesterday_zt_codes()

        if yesterday_stocks:
            codes = [s['stock_code'] for s in yesterday_stocks]
            # 获取实时行情
            quotes = fetcher.refresh_realtime_quotes(codes)

            # 构建 (当前价, 昨收价) 字典
            current_prices = {}
            for code in codes:
                if code in quotes:
                    current_prices[code] = (
                        quotes[code].get('price', 0),
                        quotes[code].get('prev_close', quotes[code].get('price', 0))
                    )

            yesterday_performance = YesterdayZtPerformance.calculate_performance(codes, current_prices)
    except Exception as e:
        logger.warning(f"获取昨日涨停表现失败: {e}")

    return {
        "code": 0,
        "data": {
            "total_zt": total_zt,
            "explosion_count": explosion_count,
            "explosion_rate": explosion_rate,
            "continuous_count": len(continuous_stocks),
            "top_sectors": top_sectors,
            "update_time": datetime.now().strftime("%H:%M:%S"),
            # 昨日涨停今日表现
            "yesterday_performance": yesterday_performance
        }
    }


@app.get("/api/zt_pool/yesterday_detail")
async def get_yesterday_zt_detail():
    """
    获取昨日涨停股的详细列表（按今日涨跌分组）

    返回:
    {
        "up_stocks": [{code, name, yesterday_close, today_price, today_change}...],
        "down_stocks": [...],
        "flat_stocks": [...],
        "no_data_stocks": [...]  # 无法获取行情的股票
    }
    """
    from data_fetcher import DataFetcher

    try:
        fetcher = DataFetcher()
        yesterday_stocks = YesterdayZtPerformance.get_yesterday_zt_codes()

        if not yesterday_stocks:
            return {"code": 0, "data": {
                "up_stocks": [],
                "down_stocks": [],
                "flat_stocks": [],
                "no_data_stocks": []
            }}

        codes = [s['stock_code'] for s in yesterday_stocks]
        quotes = fetcher.refresh_realtime_quotes(codes)

        up_stocks = []
        down_stocks = []
        flat_stocks = []
        no_data_stocks = []

        for stock in yesterday_stocks:
            code = stock['stock_code']
            name = stock['stock_name']
            yesterday_close = stock.get('yesterday_change', 0)

            if code in quotes:
                q = quotes[code]
                today_price = q.get('price', 0)
                prev_close = q.get('prev_close', today_price)

                if prev_close > 0:
                    today_change = (today_price - prev_close) / prev_close * 100
                else:
                    today_change = 0

                item = {
                    "code": code,
                    "name": name,
                    "yesterday_close": prev_close,
                    "today_price": today_price,
                    "today_change": round(today_change, 2),
                    "sector": stock.get('sector', '')
                }

                if today_change > 0.1:
                    up_stocks.append(item)
                elif today_change < -0.1:
                    down_stocks.append(item)
                else:
                    flat_stocks.append(item)
            else:
                no_data_stocks.append({
                    "code": code,
                    "name": name
                })

        # 按涨跌幅排序
        up_stocks.sort(key=lambda x: x['today_change'], reverse=True)
        down_stocks.sort(key=lambda x: x['today_change'])
        flat_stocks.sort(key=lambda x: x['today_change'], reverse=True)

        return {"code": 0, "data": {
            "up_stocks": up_stocks,
            "down_stocks": down_stocks,
            "flat_stocks": flat_stocks,
            "no_data_stocks": no_data_stocks
        }}

    except Exception as e:
        logger.error(f"获取昨日涨停详情失败: {e}")
        return {"code": 1, "message": str(e)}


@app.get("/api/predict/tomorrow")
async def get_tomorrow_prediction(limit: int = 10, extended: bool = True):
    """
    获取今日涨停股次日涨跌预测评分排行 (30+因子版)

    参数:
    - limit: 返回数量限制，默认10
    - extended: 是否使用30+因子扩展版，默认True

    返回:
    {
        "code": 0,
        "data": [
            {
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "continuous_days": 2,
                "sector": "白酒",
                "seal_amount": 52000,
                "main_net_inflow": 12000,
                "factors": {
                    "seal_time_score": 100,
                    "seal_pattern_score": 100,
                    ...
                },
                "prediction": {
                    "score": 85,
                    "up_probability": 0.72,
                    "down_probability": 0.15,
                    "flat_probability": 0.13,
                    "recommendation": "强烈推荐"
                }
            },
            ...
        ]
    }
    """
    try:
        # 暂时不使用fetcher以避免长时间等待
        # 核心因子来自ZT池和数据库已有数据
        if extended:
            predictions = ExtendedZtPredictor.get_top_predictions(limit)
        else:
            predictions = ZtPredictor.get_top_predictions(limit)
        return {"code": 0, "data": predictions}
    except Exception as e:
        logger.error(f"获取预测排行失败: {e}")
        import traceback
        traceback.print_exc()
        return {"code": 1, "message": str(e)}


@app.get("/api/analyze/stock/{stock_code}")
async def analyze_stock(stock_code: str, extended: bool = True):
    """
    分析单只股票的详细预测 (30+因子版)

    Args:
        stock_code: 股票代码
        extended: 是否使用30+因子扩展版

    Returns:
    {
        "code": 0,
        "data": {
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "today_zt": true,
            "factors": {...},
            "prediction": {...}
        }
    }
    """
    try:
        fetcher = DataFetcher()
        if extended:
            result = ExtendedZtPredictor.analyze_stock(stock_code, fetcher)
        else:
            result = ZtPredictor.analyze_stock(stock_code)
        if "error" in result:
            return {"code": 1, "message": result["error"]}
        return {"code": 0, "data": result}
    except Exception as e:
        logger.error(f"分析股票失败: {e}")
        import traceback
        traceback.print_exc()
        return {"code": 1, "message": str(e)}


@app.get("/api/predict/factors")
async def get_factor_definitions():
    """
    获取所有因子定义 (用于前端展示)

    返回:
    {
        "code": 0,
        "data": [
            {
                "name": "seal_time_score",
                "display_name": "涨停时间",
                "category": "seal_quality",
                "weight": 0.08,
                "description": "越早涨停越好..."
            },
            ...
        ]
    }
    """
    try:
        from factor_registry import get_factor_registry
        registry = get_factor_registry()
        factors = registry.get_all_factors()
        return {
            "code": 0,
            "data": [
                {
                    "name": f.name,
                    "display_name": f.display_name,
                    "category": f.category.value,
                    "weight": f.weight,
                    "description": f.description,
                    "higher_is_better": f.higher_is_better
                }
                for f in factors
            ]
        }
    except Exception as e:
        logger.error(f"获取因子定义失败: {e}")
        return {"code": 1, "message": str(e)}


@app.websocket("/ws/zt_pool")
async def websocket_zt_pool(websocket: WebSocket):
    """WebSocket - 实时推送涨停池更新"""
    await manager.connect(websocket)
    try:
        while True:
            # 保持连接，每60秒发送心跳
            await asyncio.sleep(60)
            await websocket.send_text("ping")
    except WebSocketDisconnect:
        manager.disconnect(websocket)


def create_app():
    """创建并配置应用"""
    global _scheduler

    # 初始化数据库
    init_database()

    # 挂载静态文件
    web_ui_path = Path(__file__).parent / "web_ui"
    app.mount("/web_ui", StaticFiles(directory=str(web_ui_path), html=True), name="web_ui")

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # 启动调度器
    from storage import ZtPoolStorage, SectorStorage
    fetcher = DataFetcher()

    # 创建组合存储对象
    class StorageWrapper:
        def save_zt_pool(self, stocks, date):
            return ZtPoolStorage.save_zt_pool(stocks, date)
        def save_sector_ranking(self, sectors, date):
            return SectorStorage.save_sector_ranking(sectors, date)

    storage = StorageWrapper()
    _scheduler = start_scheduler(fetcher, storage)
    logger.info("数据抓取调度器已启动")

    return app


if __name__ == "__main__":
    application = create_app()
    uvicorn.run(application, host="0.0.0.0", port=8000)
