"""FastAPI Web服务器 - 提供API和WebSocket"""
import asyncio
import logging
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from storage import ZtPoolStorage, SectorStorage, init_database

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
    today_zt = ZtPoolStorage.get_today_zt_pool()

    # 计算统计指标
    total_zt = len(today_zt)
    explosion_count = sum(1 for s in today_zt if s.get("explosion_count", 0) > 0)
    explosion_rate = round(explosion_count / total_zt * 100, 1) if total_zt > 0 else 0

    # 连板股统计
    continuous_stocks = [s for s in today_zt if s.get("continuous_days", 1) > 1]

    # 热门板块
    top_sectors = SectorStorage.get_top_sectors(3)

    return {
        "code": 0,
        "data": {
            "total_zt": total_zt,
            "explosion_count": explosion_count,
            "explosion_rate": explosion_rate,
            "continuous_count": len(continuous_stocks),
            "top_sectors": top_sectors,
            "update_time": datetime.now().strftime("%H:%M:%S")
        }
    }


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
    # 初始化数据库
    init_database()

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    return app


if __name__ == "__main__":
    application = create_app()
    uvicorn.run(application, host="0.0.0.0", port=8000)
