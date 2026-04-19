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
