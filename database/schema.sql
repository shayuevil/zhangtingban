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

-- 预测结果历史表
CREATE TABLE IF NOT EXISTS prediction_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT NOT NULL,
    stock_name TEXT NOT NULL,
    date TEXT NOT NULL,
    total_score INTEGER,
    up_probability REAL,
    down_probability REAL,
    flat_probability REAL,
    recommendation TEXT,
    factor_scores_json TEXT,
    raw_data_json TEXT,
    data_completeness REAL,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(stock_code, date)
);

-- 历史涨停统计表 (用于历史规律因子)
CREATE TABLE IF NOT EXISTS stock_zt_statistics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT NOT NULL UNIQUE,
    stock_name TEXT,
    total_zt_count INTEGER DEFAULT 0,
    avg_next_day_change REAL DEFAULT 0,
    avg_seal_amount REAL DEFAULT 0,
    avg_continuous_days REAL DEFAULT 0,
    volatility_score REAL DEFAULT 50,
    last_updated TEXT
);

-- 北向资金历史表
CREATE TABLE IF NOT EXISTS northbound_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT NOT NULL,
    date TEXT NOT NULL,
    net_buy REAL,
    hold_ratio REAL,
    consecutive_days INTEGER DEFAULT 0,
    UNIQUE(stock_code, date)
);

-- 预测结果索引
CREATE INDEX IF NOT EXISTS idx_pred_date ON prediction_history(date);
CREATE INDEX IF NOT EXISTS idx_pred_code ON prediction_history(stock_code);
CREATE INDEX IF NOT EXISTS idx_nb_date ON northbound_history(date);
