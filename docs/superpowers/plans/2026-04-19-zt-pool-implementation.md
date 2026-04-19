# A股涨停板池系统 - 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个Web版的A股涨停板池系统，支持每分钟刷新、Dashboard统计、表格筛选

**Architecture:** 定时任务抓取数据 → SQLite存储 → FastAPI提供API → WebSocket推送 → 前端展示

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy, APScheduler, SQLite, Vanilla JS

---

## 文件结构

```
gp-v2/
├── requirements.txt         # 依赖声明
├── data_fetcher.py          # 已有 - 数据获取封装
├── storage.py               # 新增 - SQLite存储层
├── scheduler.py            # 新增 - 定时任务调度
├── web_server.py           # 新增 - FastAPI服务
├── web_ui/
│   ├── index.html           # 主页
│   ├── styles.css           # 样式
│   └── app.js               # 前端逻辑
└── database/
    └── schema.sql           # 数据库Schema
```

---

## Task 1: 项目初始化

**Files:**
- Create: `requirements.txt`
- Create: `database/schema.sql`

- [ ] **Step 1: 创建 requirements.txt**

```txt
fastapi==0.109.0
uvicorn[standard]==0.27.0
sqlalchemy==2.0.25
apscheduler==3.10.4
aiohttp==3.9.3
python-multipart==0.0.6
websockets==12.0
```

- [ ] **Step 2: 创建数据库Schema**

```sql
-- 涨停池历史表
CREATE TABLE IF NOT EXISTS zt_pool_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT NOT NULL,
    stock_name TEXT NOT NULL,
    date TEXT NOT NULL,
    close_price REAL,
    change_pct REAL,
    seal_amount REAL,
    seal_count INTEGER,
    explosion_count INTEGER DEFAULT 0,
    continuous_days INTEGER DEFAULT 1,
    sector TEXT,
    sector_change_pct REAL,
    super_net_inflow REAL,
    big_net_inflow REAL,
    main_net_inflow REAL,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(stock_code, date)
);

-- 板块信息表
CREATE TABLE IF NOT EXISTS sector_info (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sector_name TEXT NOT NULL,
    date TEXT NOT NULL,
    change_pct REAL,
    zt_count INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(sector_name, date)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_zt_date ON zt_pool_history(date);
CREATE INDEX IF NOT EXISTS idx_zt_code ON zt_pool_history(stock_code);
CREATE INDEX IF NOT EXISTS idx_sector_date ON sector_info(date);
```

- [ ] **Step 3: 提交**

```bash
git add requirements.txt database/schema.sql
git commit -m "chore: project init - dependencies and database schema"
```

---

## Task 2: 存储层 (storage.py)

**Files:**
- Create: `storage.py`

- [ ] **Step 1: 编写 storage.py**

```python
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
```

- [ ] **Step 2: 验证 storage.py 可正常导入**

Run: `cd e:/gp/gp-v2 && python -c "from storage import init_database, ZtPoolStorage, SectorStorage; print('OK')"`
Expected: OK

- [ ] **Step 3: 提交**

```bash
git add storage.py
git commit -m "feat: add SQLite storage layer for ZT pool"
```

---

## Task 3: 定时任务调度 (scheduler.py)

**Files:**
- Create: `scheduler.py`

- [ ] **Step 1: 编写 scheduler.py**

```python
"""定时任务调度 - 每分钟刷新涨停池数据"""
import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

# 模拟 data_fetcher 模块的接口（实际项目中已存在）
# from data_fetcher import DataFetcher

logger = logging.getLogger(__name__)


def fetch_and_save_zt_pool(data_fetcher, storage):
    """抓取并保存涨停池数据"""
    today = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"开始抓取 {today} 涨停池数据...")

    try:
        # 1. 获取涨停池
        zt_data = data_fetcher.get_zt_pool(today)
        if not zt_data:
            logger.warning("涨停池数据为空")
            return

        # 2. 获取资金流向（批量）
        stock_codes = [s["code"] for s in zt_data]
        money_flow = data_fetcher.get_money_flow_batch(stock_codes, 1)

        # 3. 合并数据
        code_to_flow = {mf["code"]: mf for mf in money_flow}
        for stock in zt_data:
            flow = code_to_flow.get(stock["code"], {})
            stock["super_net_inflow"] = flow.get("super_net_inflow", 0)
            stock["big_net_inflow"] = flow.get("big_net_inflow", 0)
            stock["main_net_inflow"] = flow.get("main_net_inflow", 0)

            # 获取板块信息
            sector_data = data_fetcher.get_stock_industry(stock["code"])
            stock["sector"] = sector_data.get("industry", "")

        # 4. 保存到数据库
        count = storage.save_zt_pool(zt_data, today)
        logger.info(f"成功保存 {count} 条涨停数据")

    except Exception as e:
        logger.error(f"抓取涨停池失败: {e}")


def fetch_sector_ranking(data_fetcher, storage):
    """抓取并保存板块排名"""
    today = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"开始抓取 {today} 板块数据...")

    try:
        sector_data = data_fetcher.get_sector_ranking()
        if sector_data:
            count = storage.save_sector_ranking(sector_data, today)
            logger.info(f"成功保存 {count} 条板块数据")

    except Exception as e:
        logger.error(f"抓取板块数据失败: {e}")


def create_scheduler(data_fetcher, storage) -> BackgroundScheduler:
    """创建并配置调度器"""
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

    # 每分钟执行涨停池抓取
    scheduler.add_job(
        fetch_and_save_zt_pool,
        trigger=IntervalTrigger(minutes=1),
        args=[data_fetcher, storage],
        id="fetch_zt_pool",
        name="抓取涨停池数据",
        replace_existing=True
    )

    # 每5分钟执行板块数据抓取
    scheduler.add_job(
        fetch_sector_ranking,
        trigger=IntervalTrigger(minutes=5),
        args=[data_fetcher, storage],
        id="fetch_sector",
        name="抓取板块排名",
        replace_existing=True
    )

    # 启动时立即执行一次
    fetch_and_save_zt_pool(data_fetcher, storage)
    fetch_sector_ranking(data_fetcher, storage)

    return scheduler
```

- [ ] **Step 2: 提交**

```bash
git add scheduler.py
git commit -m "feat: add scheduler for periodic data fetching"
```

---

## Task 4: Web服务器 (web_server.py)

**Files:**
- Create: `web_server.py`

- [ ] **Step 1: 编写 web_server.py**

```python
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
```

- [ ] **Step 2: 提交**

```bash
git add web_server.py
git commit -m "feat: add FastAPI web server with REST API and WebSocket"
```

---

## Task 5: 前端页面 (web_ui/)

**Files:**
- Create: `web_ui/index.html`
- Create: `web_ui/styles.css`
- Create: `web_ui/app.js`

- [ ] **Step 1: 创建 index.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>A股涨停板池</title>
    <link rel="stylesheet" href="/web_ui/styles.css">
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header class="header">
            <h1>📊 今日涨停板池</h1>
            <div class="header-right">
                <span id="update-time" class="update-time">--:--:--</span>
                <button id="refresh-btn" class="btn-refresh">🔄 刷新</button>
            </div>
        </header>

        <!-- Dashboard Stats -->
        <div class="dashboard">
            <div class="stat-card">
                <div class="stat-label">涨停总数</div>
                <div id="stat-total" class="stat-value">--</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">炸板数</div>
                <div id="stat-explosion" class="stat-value">--</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">炸板率</div>
                <div id="stat-rate" class="stat-value">--</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">连板股</div>
                <div id="stat-continuous" class="stat-value">--</div>
            </div>
        </div>

        <!-- Filters -->
        <div class="filters">
            <label>
                连板≥
                <select id="filter-continuous">
                    <option value="1">全部</option>
                    <option value="2">2连板+</option>
                    <option value="3">3连板+</option>
                    <option value="4">4连板+</option>
                </select>
            </label>
            <label>
                封板资金≥
                <select id="filter-seal">
                    <option value="0">全部</option>
                    <option value="1000">1000万</option>
                    <option value="5000">5000万</option>
                    <option value="10000">1亿</option>
                </select>
            </label>
            <label>
                板块
                <select id="filter-sector">
                    <option value="">全部</option>
                </select>
            </label>
            <input type="text" id="search-stock" placeholder="搜索股票代码/名称">
        </div>

        <!-- Data Table -->
        <div class="table-container">
            <table id="zt-table">
                <thead>
                    <tr>
                        <th data-sort="stock_code">股票代码</th>
                        <th data-sort="stock_name">股票名称</th>
                        <th data-sort="continuous_days">连板</th>
                        <th data-sort="seal_amount">封板资金</th>
                        <th data-sort="explosion_count">炸板</th>
                        <th data-sort="super_net_inflow">超大单</th>
                        <th data-sort="big_net_inflow">大单</th>
                        <th data-sort="sector">板块</th>
                    </tr>
                </thead>
                <tbody id="zt-tbody">
                    <tr><td colspan="8" class="loading">加载中...</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <script src="/web_ui/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: 创建 styles.css**

```css
:root {
    --primary: #2563eb;
    --success: #10b981;
    --danger: #ef4444;
    --warning: #f59e0b;
    --bg: #f8fafc;
    --card-bg: #ffffff;
    --text: #1e293b;
    --text-muted: #64748b;
    --border: #e2e8f0;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.5;
}

.container { max-width: 1400px; margin: 0 auto; padding: 20px; }

/* Header */
.header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
}
.header h1 { font-size: 24px; }
.update-time { color: var(--text-muted); margin-right: 12px; }
.btn-refresh {
    padding: 8px 16px;
    background: var(--primary);
    color: white;
    border: none;
    border-radius: 6px;
    cursor: pointer;
}
.btn-refresh:hover { background: #1d4ed8; }

/* Dashboard */
.dashboard {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 20px;
}
.stat-card {
    background: var(--card-bg);
    padding: 20px;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}
.stat-label { color: var(--text-muted); font-size: 14px; margin-bottom: 4px; }
.stat-value { font-size: 32px; font-weight: bold; color: var(--primary); }

/* Filters */
.filters {
    display: flex;
    gap: 16px;
    margin-bottom: 16px;
    padding: 16px;
    background: var(--card-bg);
    border-radius: 8px;
}
.filters label { display: flex; align-items: center; gap: 8px; }
.filters select, .filters input {
    padding: 8px 12px;
    border: 1px solid var(--border);
    border-radius: 6px;
}
.filters input { min-width: 150px; }

/* Table */
.table-container { background: var(--card-bg); border-radius: 8px; overflow: hidden; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 12px 16px; text-align: left; border-bottom: 1px solid var(--border); }
th { background: var(--bg); font-weight: 600; cursor: pointer; }
th:hover { background: #e2e8f0; }
.loading { text-align: center; color: var(--text-muted); }

/* Stock name color */
.stock-up { color: var(--danger); font-weight: 600; }
.stock-explosion { color: var(--warning); }

/* Net inflow colors */
.positive { color: var(--danger); }
.negative { color: var(--success); }

/* Responsive */
@media (max-width: 768px) {
    .dashboard { grid-template-columns: repeat(2, 1fr); }
    .filters { flex-wrap: wrap; }
}
```

- [ ] **Step 3: 创建 app.js**

```javascript
/** A股涨停板池 - 前端逻辑 */
class ZtPoolApp {
    constructor() {
        this.data = [];
        this.sortColumn = 'continuous_days';
        this.sortOrder = 'desc';
        this.filters = { continuous: 1, seal: 0, sector: '', search: '' };

        this.initElements();
        this.bindEvents();
        this.loadData();
    }

    initElements() {
        this.elements = {
            tbody: document.getElementById('zt-tbody'),
            total: document.getElementById('stat-total'),
            explosion: document.getElementById('stat-explosion'),
            rate: document.getElementById('stat-rate'),
            continuous: document.getElementById('stat-continuous'),
            updateTime: document.getElementById('update-time'),
            filterContinuous: document.getElementById('filter-continuous'),
            filterSeal: document.getElementById('filter-seal'),
            filterSector: document.getElementById('filter-sector'),
            searchStock: document.getElementById('search-stock'),
            refreshBtn: document.getElementById('refresh-btn')
        };
    }

    bindEvents() {
        // 刷新按钮
        this.elements.refreshBtn.addEventListener('click', () => this.loadData());

        // 筛选器
        this.elements.filterContinuous.addEventListener('change', (e) => {
            this.filters.continuous = parseInt(e.target.value);
            this.renderTable();
        });
        this.elements.filterSeal.addEventListener('change', (e) => {
            this.filters.seal = parseInt(e.target.value);
            this.renderTable();
        });
        this.elements.filterSector.addEventListener('change', (e) => {
            this.filters.sector = e.target.value;
            this.renderTable();
        });
        this.elements.searchStock.addEventListener('input', (e) => {
            this.filters.search = e.target.value.toLowerCase();
            this.renderTable();
        });

        // 排序
        document.querySelectorAll('th[data-sort]').forEach(th => {
            th.addEventListener('click', () => this.handleSort(th.dataset.sort));
        });
    }

    async loadData() {
        try {
            const [poolRes, statsRes, sectorRes] = await Promise.all([
                fetch('/api/zt_pool/today'),
                fetch('/api/stats/dashboard'),
                fetch('/api/sector/ranking?limit=20')
            ]);

            const poolData = await poolRes.json();
            const statsData = await statsRes.json();
            const sectorData = await sectorRes.json();

            this.data = poolData.data || [];

            this.updateStats(statsData.data);
            this.updateSectorFilter(sectorData.data);
            this.renderTable();
            this.elements.updateTime.textContent = statsData.data?.update_time || '--';
        } catch (err) {
            console.error('加载数据失败:', err);
            this.elements.tbody.innerHTML = '<tr><td colspan="8" class="loading">加载失败</td></tr>';
        }
    }

    updateStats(stats) {
        if (!stats) return;
        this.elements.total.textContent = stats.total_zt || 0;
        this.elements.explosion.textContent = stats.explosion_count || 0;
        this.elements.rate.textContent = (stats.explosion_rate || 0) + '%';
        this.elements.continuous.textContent = stats.continuous_count || 0;
    }

    updateSectorFilter(sectors) {
        const select = this.elements.filterSector;
        const currentValue = select.value;
        select.innerHTML = '<option value="">全部</option>';
        (sectors || []).forEach(s => {
            const opt = document.createElement('option');
            opt.value = s.sector_name;
            opt.textContent = s.sector_name;
            select.appendChild(opt);
        });
        select.value = currentValue;
    }

    handleSort(column) {
        if (this.sortColumn === column) {
            this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc';
        } else {
            this.sortColumn = column;
            this.sortOrder = 'desc';
        }
        this.renderTable();
    }

    getFilteredData() {
        return this.data.filter(item => {
            if (item.continuous_days < this.filters.continuous) return false;
            if ((item.seal_amount || 0) < this.filters.seal) return false;
            if (this.filters.sector && item.sector !== this.filters.sector) return false;
            if (this.filters.search) {
                const match = item.stock_code.toLowerCase().includes(this.filters.search) ||
                              item.stock_name.toLowerCase().includes(this.filters.search);
                if (!match) return false;
            }
            return true;
        }).sort((a, b) => {
            const aVal = a[this.sortColumn] || 0;
            const bVal = b[this.sortColumn] || 0;
            return this.sortOrder === 'asc' ? aVal - bVal : bVal - aVal;
        });
    }

    renderTable() {
        const filtered = this.getFilteredData();
        if (filtered.length === 0) {
            this.elements.tbody.innerHTML = '<tr><td colspan="8" class="loading">暂无数据</td></tr>';
            return;
        }

        this.elements.tbody.innerHTML = filtered.map(item => `
            <tr>
                <td>${item.stock_code}</td>
                <td class="stock-up">${item.stock_name}</td>
                <td>${item.continuous_days || 1}</td>
                <td>${this.formatAmount(item.seal_amount)}</td>
                <td class="${item.explosion_count > 0 ? 'stock-explosion' : ''}">${item.explosion_count || 0}</td>
                <td class="${item.super_net_inflow >= 0 ? 'positive' : 'negative'}">${this.formatFlow(item.super_net_inflow)}</td>
                <td class="${item.big_net_inflow >= 0 ? 'positive' : 'negative'}">${this.formatFlow(item.big_net_inflow)}</td>
                <td>${item.sector || '-'}</td>
            </tr>
        `).join('');
    }

    formatAmount(val) {
        if (!val) return '-';
        if (val >= 10000) return (val / 10000).toFixed(1) + '亿';
        return val.toFixed(0) + '万';
    }

    formatFlow(val) {
        if (!val && val !== 0) return '-';
        const abs = Math.abs(val);
        if (abs >= 10000) return (val >= 0 ? '+' : '-') + (abs / 10000).toFixed(2) + '亿';
        return (val >= 0 ? '+' : '-') + abs.toFixed(0) + '万';
    }
}

// 启动
document.addEventListener('DOMContentLoaded', () => {
    window.app = new ZtPoolApp();

    // 自动刷新 - 每分钟
    setInterval(() => window.app.loadData(), 60000);
});
```

- [ ] **Step 4: 提交**

```bash
git add web_ui/index.html web_ui/styles.css web_ui/app.js
git commit -m "feat: add Web UI for ZT pool dashboard"
```

---

## Task 6: 集成测试

**Files:**
- Modify: `web_server.py` (添加静态文件挂载)

- [ ] **Step 1: 更新 web_server.py 添加静态文件支持**

在 `create_app()` 函数中添加：

```python
# 在 init_database() 之后添加
web_ui_path = Path(__file__).parent / "web_ui"
app.mount("/web_ui", StaticFiles(directory=str(web_ui_path)), name="web_ui")
```

- [ ] **Step 2: 本地启动测试**

Run: `cd e:/gp/gp-v2 && python web_server.py`
Expected: 服务启动在 0.0.0.0:8000

- [ ] **Step 3: 浏览器访问验证**

打开浏览器访问 http://localhost:8000
Expected: 显示涨停板池Dashboard页面

- [ ] **Step 4: 提交**

```bash
git add web_server.py
git commit -m "chore: add static files mount for web UI"
```

---

## Task 7: 清理与文档

**Files:**
- Create: `README.md`
- Create: `run.py` (启动脚本)

- [ ] **Step 1: 创建 README.md**

```markdown
# A股涨停板池系统

实时监控A股涨停板池，支持资金流向分析、板块联动追踪。

## 功能特性

- 实时涨停池数据（每分钟自动刷新）
- 资金流向监控（超大单、大单净流入）
- Dashboard统计面板
- 多维度筛选（连板数、封板资金、板块）
- 历史数据存储（支持复盘）

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
python run.py

# 访问
http://localhost:8000
```

## 项目结构

- `data_fetcher.py` - 数据获取接口
- `storage.py` - SQLite存储层
- `scheduler.py` - 定时任务调度
- `web_server.py` - FastAPI服务
- `web_ui/` - 前端页面
```

- [ ] **Step 2: 创建 run.py**

```python
"""启动脚本"""
from web_server import create_app
import uvicorn

if __name__ == "__main__":
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

- [ ] **Step 3: 提交**

```bash
git add README.md run.py
git commit -m "docs: add README and run script"
```

---

## 实现顺序

1. **Task 1** - 项目初始化（requirements.txt, schema.sql）
2. **Task 2** - 存储层（storage.py）
3. **Task 3** - 定时任务（scheduler.py）
4. **Task 4** - Web服务器（web_server.py）
5. **Task 5** - 前端页面（web_ui/*）
6. **Task 6** - 集成测试
7. **Task 7** - 清理文档

---

## 扩展预留口 (v2+)

| 功能 | 文件位置 | 说明 |
|------|----------|------|
| 多因子筛选 | app.js | 增加技术指标筛选 |
| 分时图 | web_ui/ | 详情弹窗加入K线/分时 |
| 历史查询 | web_server.py | 增加日期选择器 |
| 北向资金 | storage.py | 增加北向资金字段 |
| 趋势跟踪 | 新增模块 | 主力资金历史趋势 |
