"""
A股资金流向监控系统 - 配置模块
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ============ 数据源配置 ============
DATA_SOURCE = os.getenv('DATA_SOURCE', 'akshare')  # akshare / tushare
TUSHARE_TOKEN = os.getenv('TUSHARE_TOKEN', '')

# ============ 股票筛选 ============
DEFAULT_STOCK_COUNT = int(os.getenv('DEFAULT_STOCK_COUNT', '50'))
# 排除的股票前缀：创业板300、科创板688、北交所8/4
EXCLUDE_PREFIXES = ('300', '688', '8', '4')

# ============ 信号阈值 ============
# 强烈买入：超大单净流入 > 1亿 且 主力占比 > 15%
STRONG_BUY_SUPER_LARGE_THRESHOLD = 100_000_000  # 1亿
STRONG_BUY_MAIN_RATIO_THRESHOLD = 15.0          # 15%

# 买入：主力净流入 > 5000万 且 主力占比 > 8%
BUY_MAIN_INFLOW_THRESHOLD = 50_000_000  # 5000万
BUY_MAIN_RATIO_THRESHOLD = 8.0          # 8%

# 卖出：主力净流出 > 5000万
SELL_MAIN_OUTFLOW_THRESHOLD = 50_000_000  # 5000万

# ============ 监控配置 ============
MONITOR_INTERVAL = int(os.getenv('MONITOR_INTERVAL', '60'))  # 秒
MAX_WORKERS = int(os.getenv('MAX_WORKERS', '5'))             # 并发线程数

# ============ 实时行情刷新 ============
# 在资金流扫描间隔内，额外刷新实时行情（价格/涨幅/成交额）的间隔（秒）
# 设为 0 则禁用，建议 5-15 秒
# 优先使用东方财富push2 API（延迟<3秒），新浪作为降级备选
REALTIME_QUOTE_INTERVAL = int(os.getenv('REALTIME_QUOTE_INTERVAL', '5'))
# 实时行情刷新时，只刷新有信号的股票（节省请求量）
REALTIME_ONLY_SIGNALED = os.getenv('REALTIME_ONLY_SIGNALED', 'true').lower() == 'true'

# ============ 东方财富WebSocket配置 ============
# 启用WebSocket推送模式（需安装websockets库，pip install websockets）
# 开启后实时行情通过WS推送获取，关闭则使用HTTP轮询
ENABLE_EM_WEBSOCKET = os.getenv('ENABLE_EM_WEBSOCKET', 'false').lower() == 'true'
# WS推送模式下，行情变化超过此阈值才触发回调（涨跌幅变化，单位%）
WS_CHANGE_THRESHOLD = float(os.getenv('WS_CHANGE_THRESHOLD', '0.3'))

# ============ 增量检测配置 ============
# 启用增量检测（对比前后两次扫描的净额变化）
ENABLE_INCREMENTAL = os.getenv('ENABLE_INCREMENTAL', 'true').lower() == 'true'
# 突发异动：扫描间隔内净流入增量超过此值（元）
SUDDEN_INFLOW_THRESHOLD = float(os.getenv('SUDDEN_INFLOW_THRESHOLD', '30000000'))  # 3000万
# 突发异动：增量占比超过此值（%）
SUDDEN_RATIO_THRESHOLD = float(os.getenv('SUDDEN_RATIO_THRESHOLD', '5.0'))  # 5%
# 突发流出：扫描间隔内净流出增量超过此值
SUDDEN_OUTFLOW_THRESHOLD = float(os.getenv('SUDDEN_OUTFLOW_THRESHOLD', '30000000'))  # 3000万

# ============ 大单明细配置 ============
# 启用大单明细扫描
ENABLE_BIG_DEAL = os.getenv('ENABLE_BIG_DEAL', 'true').lower() == 'true'
# 大单明细：只统计最近N分钟的大单
BIG_DEAL_MINUTES = int(os.getenv('BIG_DEAL_MINUTES', '5'))  # 5分钟
# 大单明细：单笔买盘金额超过此值视为大单（元）
BIG_DEAL_AMOUNT_THRESHOLD = float(os.getenv('BIG_DEAL_AMOUNT_THRESHOLD', '500000'))  # 50万

# ============ 买入确认条件（评分制）============
# 启用买入确认条件过滤
ENABLE_BUY_CONFIRM = os.getenv('ENABLE_BUY_CONFIRM', 'true').lower() == 'true'

# 确认阈值：评分>=此值则确认买入（满分100）
BUY_CONFIRM_THRESHOLD = int(os.getenv('BUY_CONFIRM_THRESHOLD', '60'))

# 涨幅安全：当日涨幅在 [MIN, MAX] 区间得满分，略偏得半分
BUY_CHANGE_PCT_MIN = float(os.getenv('BUY_CHANGE_PCT_MIN', '-2.0'))   # -2%（允许小幅低开）
BUY_CHANGE_PCT_MAX = float(os.getenv('BUY_CHANGE_PCT_MAX', '7.0'))    # 7%（放宽追高限制）

# 换手率：在 [MIN, MAX] 区间得满分，换手率0视为数据缺失给半分
BUY_TURNOVER_MIN = float(os.getenv('BUY_TURNOVER_MIN', '1.0'))        # 1%（降低下限）
BUY_TURNOVER_MAX = float(os.getenv('BUY_TURNOVER_MAX', '20.0'))       # 20%（放宽上限）

# 流入流出比：流入/流出 > 此值得满分（现改为优先用主力占比判断）
BUY_INFLOW_OUTFLOW_RATIO = float(os.getenv('BUY_INFLOW_OUTFLOW_RATIO', '1.5'))  # 1.5倍

# 量价配合：成交量 > 5日均量的此倍数才得满分（放量）
BUY_VOLUME_RATIO = float(os.getenv('BUY_VOLUME_RATIO', '1.2'))  # 1.2倍（降低门槛）

# 均线趋势：5日均线 > 10日均线 > 20日均线（多头排列）才得满分
BUY_REQUIRE_MAV_BULL = os.getenv('BUY_REQUIRE_MAV_BULL', 'true').lower() == 'true'

# 连续流入：要求连续N次扫描增量都为正得满分，累计净流入为正得2/3分
BUY_CONSECUTIVE_INFLOW = int(os.getenv('BUY_CONSECUTIVE_INFLOW', '2'))  # 连续2次

# 板块共振：所属行业板块主力净流入 > 0 才得分
BUY_REQUIRE_SECTOR_BULL = os.getenv('BUY_REQUIRE_SECTOR_BULL', 'false').lower() == 'true'

# 只在交易时段发出买入确认信号（盘后只显示观察信号）
BUY_TRADING_TIME_ONLY = os.getenv('BUY_TRADING_TIME_ONLY', 'true').lower() == 'true'

# ============ 邮件通知 ============
ENABLE_EMAIL = os.getenv('ENABLE_EMAIL', 'false').lower() == 'true'
SMTP_SERVER = os.getenv('SMTP_SERVER', '')
SMTP_PORT = int(os.getenv('SMTP_PORT', '465'))
SMTP_USER = os.getenv('SMTP_USER', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
EMAIL_TO = os.getenv('EMAIL_TO', '')  # 收件人，多个用逗号分隔

# ============ 微信通知 (Server酱) ============
ENABLE_WECHAT = os.getenv('ENABLE_WECHAT', 'false').lower() == 'true'
SERVERCHAN_KEY = os.getenv('SERVERCHAN_KEY', '')

# ============ 声音提醒 ============
ENABLE_SOUND = os.getenv('ENABLE_SOUND', 'true').lower() == 'true'

# ============ 模拟交易 ============
ENABLE_SIMULATED_TRADING = os.getenv('ENABLE_SIMULATED_TRADING', 'false').lower() == 'true'
INITIAL_CAPITAL = float(os.getenv('INITIAL_CAPITAL', '1000000'))  # 初始资金100万
TRADE_POSITION_RATIO = float(os.getenv('TRADE_POSITION_RATIO', '0.1'))  # 单只仓位10%

# ============ 日志配置 ============
LOG_DIR = os.getenv('LOG_DIR', 'logs')  # 日志存放目录，按日期分文件

# ============ 尾盘选股配置 ============
# 启用尾盘选股
ENABLE_LATE_SCREENING = os.getenv('ENABLE_LATE_SCREENING', 'true').lower() == 'true'

# 自动运行时间（HH:MM）
LATE_SCREENING_TIME = os.getenv('LATE_SCREENING_TIME', '14:45')

# 市值上限（元，默认400亿）
SCREENING_MAX_MARKET_CAP = float(os.getenv('SCREENING_MAX_MARKET_CAP', '40000000000'))

# 涨停排除阈值（涨幅>=此值视为涨停，留0.2%余量）
SCREENING_LIMIT_UP_THRESHOLD = float(os.getenv('SCREENING_LIMIT_UP_THRESHOLD', '9.8'))

# 大资金门槛（主力净流入超过此值，默认5000万）
SCREENING_MAIN_INFLOW_MIN = float(os.getenv('SCREENING_MAIN_INFLOW_MIN', '50000000'))

# ---- 前期堆量检测参数 ----
# 堆量回看天数（近N日内寻找堆量段）
SCREENING_VOLUME_SURGE_LOOKBACK = int(os.getenv('SCREENING_VOLUME_SURGE_LOOKBACK', '30'))
# 堆量判定：连续N日成交量 > 均量的倍数
SCREENING_VOLUME_SURGE_CONSECUTIVE = int(os.getenv('SCREENING_VOLUME_SURGE_CONSECUTIVE', '3'))
# 堆量判定：单日成交量 > 前期20日均量的倍数
SCREENING_VOLUME_SURGE_RATIO = float(os.getenv('SCREENING_VOLUME_SURGE_RATIO', '1.5'))
# 堆量上升判定：堆量期间涨幅下限（%）
SCREENING_VOLUME_SURGE_RISE_MIN = float(os.getenv('SCREENING_VOLUME_SURGE_RISE_MIN', '3.0'))

# ---- 洗盘/吸筹判定参数 ----
# 洗盘回撤幅度上限（从堆量高点回撤%，超过则视为破位）
SCREENING_PULLBACK_MAX = float(os.getenv('SCREENING_PULLBACK_MAX', '20.0'))
# 洗盘回撤幅度下限（回撤太少可能没洗干净）
SCREENING_PULLBACK_MIN = float(os.getenv('SCREENING_PULLBACK_MIN', '3.0'))
# 洗盘期间缩量比：洗盘期均量 / 堆量期均量 < 此值
SCREENING_PULLBACK_SHRINK_RATIO = float(os.getenv('SCREENING_PULLBACK_SHRINK_RATIO', '0.7'))

# ---- 金叉突破信号参数 ----
# MA5上穿MA20：前一日MA5 <= MA20，当日MA5 > MA20
SCREENING_MA_CROSS_ENABLED = os.getenv('SCREENING_MA_CROSS_ENABLED', 'true').lower() == 'true'
# 当日倍量：今日成交量 > 近5日均量的倍数
SCREENING_BREAKOUT_VOLUME_RATIO = float(os.getenv('SCREENING_BREAKOUT_VOLUME_RATIO', '1.5'))

# ---- MACD确认参数 ----
# 要求MACD金叉（DIF > DEA）或DIF在零轴上方
SCREENING_MACD_ENABLED = os.getenv('SCREENING_MACD_ENABLED', 'true').lower() == 'true'
# MACD零轴上方加分（不强制，金叉即可）
SCREENING_MACD_ABOVE_ZERO_BONUS = os.getenv('SCREENING_MACD_ABOVE_ZERO_BONUS', 'true').lower() == 'true'

# ---- 三线站稳参数 ----
# 阳线站上三线：收盘价 > MA5 且 > MA10 且 > MA20，且为阳线
SCREENING_STAND_ABOVE_MA_ENABLED = os.getenv('SCREENING_STAND_ABOVE_MA_ENABLED', 'true').lower() == 'true'

# ============ 212战法选股配置 ============
# 启用212战法选股
ENABLE_SCREENER_212 = os.getenv('ENABLE_SCREENER_212', 'true').lower() == 'true'

# 回调天数上限（中间阴线最多几天，默认3天）
S212_MAX_PULLBACK_DAYS = int(os.getenv('S212_MAX_PULLBACK_DAYS', '3'))

# 首阴缩量比：阴线日均量 / 2连板日均量 < 此值才合格
S212_PULLBACK_SHRINK_RATIO = float(os.getenv('S212_PULLBACK_SHRINK_RATIO', '0.7'))

# 首阴回调幅度范围（%）
S212_PULLBACK_MIN = float(os.getenv('S212_PULLBACK_MIN', '3.0'))
S212_PULLBACK_MAX = float(os.getenv('S212_PULLBACK_MAX', '20.0'))

# 封板最低资金（元，默认1000万）
S212_MIN_SEAL_AMOUNT = float(os.getenv('S212_MIN_SEAL_AMOUNT', '10000000'))

# 炸板次数上限（超过则淘汰）
S212_MAX_BREAK_COUNT = int(os.getenv('S212_MAX_BREAK_COUNT', '3'))

# 反包日量能要求：反包日成交量 / 首阴日成交量 > 此值
S212_REBOUND_VOL_RATIO = float(os.getenv('S212_REBOUND_VOL_RATIO', '1.2'))

# ============ 尾盘分时指标配置 ============
# VWAP支撑：股价低于分时均价线此比例则一票否决
SCREENING_VWAP_VETO_ENABLED = os.getenv('SCREENING_VWAP_VETO_ENABLED', 'true').lower() == 'true'
SCREENING_VWAP_MIN_RATIO = float(os.getenv('SCREENING_VWAP_MIN_RATIO', '1.01'))

# 尾盘抢筹量比阈值（14:30-14:55量比 > 此值加分）
SCREENING_TAIL_VOLUME_RATIO = float(os.getenv('SCREENING_TAIL_VOLUME_RATIO', '1.5'))

# RSI超买阈值（RSI(6) > 此值大扣分）
SCREENING_RSI_OVERBOUGHT = float(os.getenv('SCREENING_RSI_OVERBOUGHT', '85.0'))

# KDJ金叉加分区域（K值在此区间上穿D值时加分）
SCREENING_KDJ_GOLDEN_CROSS_ZONE_LOW = float(os.getenv('SCREENING_KDJ_GOLDEN_CROSS_ZONE_LOW', '40.0'))
SCREENING_KDJ_GOLDEN_CROSS_ZONE_HIGH = float(os.getenv('SCREENING_KDJ_GOLDEN_CROSS_ZONE_HIGH', '60.0'))

# 筹码集中度阈值（简化替代：1 - (高点价-当前价)/高点价）
SCREENING_CHIP_GOOD = float(os.getenv('SCREENING_CHIP_GOOD', '0.8'))
SCREENING_CHIP_BAD = float(os.getenv('SCREENING_CHIP_BAD', '0.3'))

# 板块共振：涨幅排名前百分之几算领涨板块
SCREENING_SECTOR_TOP_PCT = float(os.getenv('SCREENING_SECTOR_TOP_PCT', '5.0'))

# ============ 高阶尾盘指标配置 ============

# ---- 大盘/指数情绪滤网 ----
# 启用大盘情绪滤网（上涨家数占比过低时降权或终止选股）
SCREENING_MARKET_FILTER_ENABLED = os.getenv('SCREENING_MARKET_FILTER_ENABLED', 'true').lower() == 'true'
# 上涨家数占比下限（低于此值触发滤网）
SCREENING_MARKET_UP_RATIO_MIN = float(os.getenv('SCREENING_MARKET_UP_RATIO_MIN', '0.30'))
# 滤网模式：'strict' 终止选股 | 'penalty' 降低所有评分
SCREENING_MARKET_FILTER_MODE = os.getenv('SCREENING_MARKET_FILTER_MODE', 'penalty')
# penalty模式的衰减系数（评分乘以此值）
SCREENING_MARKET_PENALTY_FACTOR = float(os.getenv('SCREENING_MARKET_PENALTY_FACTOR', '0.7'))

# ---- 盘口委比与内外盘 ----
# 启用盘口数据检验（诱多陷阱否决）
SCREENING_ORDER_BOOK_ENABLED = os.getenv('SCREENING_ORDER_BOOK_ENABLED', 'true').lower() == 'true'
# 委比下限（%），低于此值视为卖压过大
SCREENING_ORDER_BOOK_MIN_COMMITTEE_RATIO = float(os.getenv('SCREENING_ORDER_BOOK_MIN_COMMITTEE_RATIO', '-30.0'))
# 外盘/内盘下限，低于此值视为主动卖出过多
SCREENING_ORDER_BOOK_MIN_OUTIN_RATIO = float(os.getenv('SCREENING_ORDER_BOOK_MIN_OUTIN_RATIO', '0.7'))

# ---- 横向阻力位突破（20日新高）----
# 启用20日新高突破加分
SCREENING_BREAKOUT_20D_ENABLED = os.getenv('SCREENING_BREAKOUT_20D_ENABLED', 'true').lower() == 'true'
# 创20日新高加分值
SCREENING_BREAKOUT_20D_BONUS = float(os.getenv('SCREENING_BREAKOUT_20D_BONUS', '15.0'))
# 突破时放量倍数要求（量比 > 此值才给加分）
SCREENING_BREAKOUT_20D_VOL_RATIO = float(os.getenv('SCREENING_BREAKOUT_20D_VOL_RATIO', '1.2'))

# ---- 抗跌相对强度 ----
# 启用抗跌相对强度检验（大盘跳水时个股抗跌加分）
SCREENING_RELATIVE_STRENGTH_ENABLED = os.getenv('SCREENING_RELATIVE_STRENGTH_ENABLED', 'true').lower() == 'true'
# 大盘跳水检测时段（开始时间, 结束时间）
SCREENING_RS_DIVE_START = os.getenv('SCREENING_RS_DIVE_START', '13:30')
SCREENING_RS_DIVE_END = os.getenv('SCREENING_RS_DIVE_END', '14:00')
# 指数在该时段跌幅超过此值(%)视为跳水
SCREENING_RS_DIVE_THRESHOLD = float(os.getenv('SCREENING_RS_DIVE_THRESHOLD', '-0.3'))
# 强抗跌加分（个股在VWAP之上）
SCREENING_RS_STRONG_BONUS = float(os.getenv('SCREENING_RS_STRONG_BONUS', '10.0'))
# 极强抗跌加分（个股逆势走高）
SCREENING_RS_EXTREME_BONUS = float(os.getenv('SCREENING_RS_EXTREME_BONUS', '15.0'))
# 大盘指数代码（沪深300）
SCREENING_RS_INDEX_CODE = os.getenv('SCREENING_RS_INDEX_CODE', '000300')

# ============ 尾盘选股增强指标配置 ============
# ---- 量价背离检测 ----
# 启用量价背离检测（价格创新高但量能萎缩则扣分/否决）
SCREENING_DIVERGENCE_ENABLED = os.getenv('SCREENING_DIVERGENCE_ENABLED', 'true').lower() == 'true'
# 量价顶背离否决：近N日价格创新高但均量低于前高段均量的比例阈值
# 0.7 表示当前量仅为前高量的70%以下视为顶背离
SCREENING_DIVERGENCE_VOL_RATIO = float(os.getenv('SCREENING_DIVERGENCE_VOL_RATIO', '0.7'))
# 量价背离扣分比例（评分乘以此值）
SCREENING_DIVERGENCE_PENALTY = float(os.getenv('SCREENING_DIVERGENCE_PENALTY', '0.7'))

# ---- 涨幅位置分档 ----
# 启用涨幅位置分档评分（涨幅过高则扣分）
SCREENING_CHANGE_TIER_ENABLED = os.getenv('SCREENING_CHANGE_TIER_ENABLED', 'true').lower() == 'true'
# 各档位阈值（涨幅%）
SCREENING_CHANGE_TIER_BEST_MIN = float(os.getenv('SCREENING_CHANGE_TIER_BEST_MIN', '1.0'))    # 最佳区间下限
SCREENING_CHANGE_TIER_BEST_MAX = float(os.getenv('SCREENING_CHANGE_TIER_BEST_MAX', '3.0'))    # 最佳区间上限
SCREENING_CHANGE_TIER_GOOD_MAX = float(os.getenv('SCREENING_CHANGE_TIER_GOOD_MAX', '5.0'))    # 良好区间上限
SCREENING_CHANGE_TIER_HIGH_MAX = float(os.getenv('SCREENING_CHANGE_TIER_HIGH_MAX', '7.0'))    # 偏高区间上限
# 各档位折扣系数
SCREENING_CHANGE_TIER_BEST_SCORE = float(os.getenv('SCREENING_CHANGE_TIER_BEST_SCORE', '1.0'))    # 最佳: 满分
SCREENING_CHANGE_TIER_GOOD_SCORE = float(os.getenv('SCREENING_CHANGE_TIER_GOOD_SCORE', '0.8'))    # 良好: 8折
SCREENING_CHANGE_TIER_HIGH_SCORE = float(os.getenv('SCREENING_CHANGE_TIER_HIGH_SCORE', '0.6'))    # 偏高: 6折
SCREENING_CHANGE_TIER_EXTREME_SCORE = float(os.getenv('SCREENING_CHANGE_TIER_EXTREME_SCORE', '0.4'))  # 极高: 4折

# ---- OBV能量潮 ----
# 启用OBV能量潮确认（验证量能趋势）
SCREENING_OBV_ENABLED = os.getenv('SCREENING_OBV_ENABLED', 'true').lower() == 'true'
# OBV加分值
SCREENING_OBV_BONUS = float(os.getenv('SCREENING_OBV_BONUS', '5.0'))
# OBV扣分比例（OBV下行时评分乘以此值）
SCREENING_OBV_PENALTY = float(os.getenv('SCREENING_OBV_PENALTY', '0.85'))

# ---- 布林带位置 ----
# 启用布林带位置检测
SCREENING_BOLL_ENABLED = os.getenv('SCREENING_BOLL_ENABLED', 'true').lower() == 'true'
# 布林带上轨外扣分比例
SCREENING_BOLL_ABOVE_UPPER_PENALTY = float(os.getenv('SCREENING_BOLL_ABOVE_UPPER_PENALTY', '0.7'))
# 布林带中轨上方加分值
SCREENING_BOLL_MID_ABOVE_BONUS = float(os.getenv('SCREENING_BOLL_MID_ABOVE_BONUS', '3.0'))

# ---- 多日主力资金趋势 ----
# 启用多日主力资金趋势检测
SCREENING_CAPITAL_TREND_ENABLED = os.getenv('SCREENING_CAPITAL_TREND_ENABLED', 'true').lower() == 'true'
# 连续净流入天数（>=此值加分）
SCREENING_CAPITAL_TREND_CONSECUTIVE_DAYS = int(os.getenv('SCREENING_CAPITAL_TREND_CONSECUTIVE_DAYS', '3'))
# 连续净流入加分值
SCREENING_CAPITAL_TREND_BONUS = float(os.getenv('SCREENING_CAPITAL_TREND_BONUS', '8.0'))
# 仅当日流入（非连续）扣分比例
SCREENING_CAPITAL_TREND_SINGLE_PENALTY = float(os.getenv('SCREENING_CAPITAL_TREND_SINGLE_PENALTY', '0.9'))
# 连续净流出否决（连续N天净流出则一票否决）
SCREENING_CAPITAL_TREND_OUTFLOW_VETO_DAYS = int(os.getenv('SCREENING_CAPITAL_TREND_OUTFLOW_VETO_DAYS', '3'))

# ---- 尾盘集合竞价分析 ----
# 启用尾盘集合竞价分析
SCREENING_CALL_AUCTION_ENABLED = os.getenv('SCREENING_CALL_AUCTION_ENABLED', 'true').lower() == 'true'
# 集合竞价量 > 全天均量此倍数视为抢筹
SCREENING_CALL_AUCTION_VOL_SURGE = float(os.getenv('SCREENING_CALL_AUCTION_VOL_SURGE', '3.0'))
# 集合竞价抢筹加分值
SCREENING_CALL_AUCTION_BONUS = float(os.getenv('SCREENING_CALL_AUCTION_BONUS', '8.0'))
# 集合竞价价格跳水（低于收盘价0.5%）否决
SCREENING_CALL_AUCTION_DROP_PCT = float(os.getenv('SCREENING_CALL_AUCTION_DROP_PCT', '-0.5'))

# ---- 北向资金确认 ----
# 启用北向资金确认
SCREENING_NORTHBOUND_ENABLED = os.getenv('SCREENING_NORTHBOUND_ENABLED', 'true').lower() == 'true'
# 北向净买入加分阈值（元，默认5000万）
SCREENING_NORTHBOUND_BUY_MIN = float(os.getenv('SCREENING_NORTHBOUND_BUY_MIN', '50000000'))
# 北向净买入加分值
SCREENING_NORTHBOUND_BONUS = float(os.getenv('SCREENING_NORTHBOUND_BONUS', '8.0'))
# 北向净卖出扣分比例
SCREENING_NORTHBOUND_SELL_PENALTY = float(os.getenv('SCREENING_NORTHBOUND_SELL_PENALTY', '0.85'))
# 北向净卖出阈值（元，默认5000万）
SCREENING_NORTHBOUND_SELL_MIN = float(os.getenv('SCREENING_NORTHBOUND_SELL_MIN', '50000000'))

# ---- 次日关键价位预计算 ----
# 启用次日关键价位预计算
SCREENING_NEXT_DAY_LEVELS_ENABLED = os.getenv('SCREENING_NEXT_DAY_LEVELS_ENABLED', 'true').lower() == 'true'

# ---- 板块资金流共振 ----
# 启用板块资金流共振（超越板块涨幅看资金流向）
SCREENING_SECTOR_FUND_ENABLED = os.getenv('SCREENING_SECTOR_FUND_ENABLED', 'true').lower() == 'true'
# 板块主力净流入加分值
SCREENING_SECTOR_FUND_BONUS = float(os.getenv('SCREENING_SECTOR_FUND_BONUS', '5.0'))
# 板块涨幅前5%但主力净流出否决
SCREENING_SECTOR_FUND_VETO_ENABLED = os.getenv('SCREENING_SECTOR_FUND_VETO_ENABLED', 'true').lower() == 'true'

# ============ 涨停次日买入评估配置 ============
# 启用涨停次日买入评估
ZT_NEXT_DAY_ENABLED = os.getenv('ZT_NEXT_DAY_ENABLED', 'true').lower() == 'true'

# ---- 快筛层参数 ----
# 最低封板资金（元，默认1000万）
ZT_NEXT_DAY_MIN_SEAL_AMOUNT = float(os.getenv('ZT_NEXT_DAY_MIN_SEAL_AMOUNT', '10000000'))
# 最大炸板次数
ZT_NEXT_DAY_MAX_BREAK_COUNT = int(os.getenv('ZT_NEXT_DAY_MAX_BREAK_COUNT', '3'))
# 尾盘封板截止时间（HH:MM，首次封板晚于此时间视为尾盘封板）
ZT_NEXT_DAY_LATE_SEAL_TIME = os.getenv('ZT_NEXT_DAY_LATE_SEAL_TIME', '14:45')
# 最低换手率（%）
ZT_NEXT_DAY_MIN_TURNOVER = float(os.getenv('ZT_NEXT_DAY_MIN_TURNOVER', '2.0'))
# 最高换手率（%）
ZT_NEXT_DAY_MAX_TURNOVER = float(os.getenv('ZT_NEXT_DAY_MAX_TURNOVER', '30.0'))
# 最低总市值（元，默认30亿）
ZT_NEXT_DAY_MIN_MARKET_CAP = float(os.getenv('ZT_NEXT_DAY_MIN_MARKET_CAP', '3000000000'))
# 最高总市值（元，默认500亿）
ZT_NEXT_DAY_MAX_MARKET_CAP = float(os.getenv('ZT_NEXT_DAY_MAX_MARKET_CAP', '50000000000'))

# ---- 评分调节参数 ----
# 高位涨停扣分系数（5日累计涨幅>30%时，总分乘此值）
ZT_NEXT_DAY_HIGH_POSITION_PENALTY = float(os.getenv('ZT_NEXT_DAY_HIGH_POSITION_PENALTY', '0.7'))
# 连续放量扣分系数（5日无缩量日时，总分乘此值）
ZT_NEXT_DAY_CONSECUTIVE_VOL_PENALTY = float(os.getenv('ZT_NEXT_DAY_CONSECUTIVE_VOL_PENALTY', '0.8'))
# 板块领涨+资金共振加分
ZT_NEXT_DAY_SECTOR_BONUS = float(os.getenv('ZT_NEXT_DAY_SECTOR_BONUS', '8.0'))
# 首板底部启动加分
ZT_NEXT_DAY_BOTTOM_START_BONUS = float(os.getenv('ZT_NEXT_DAY_BOTTOM_START_BONUS', '5.0'))
# 3连板以上加分
ZT_NEXT_DAY_MULTI_BOARD_BONUS = float(os.getenv('ZT_NEXT_DAY_MULTI_BOARD_BONUS', '5.0'))
# 尾盘回封扣分
ZT_NEXT_DAY_LATE_RESEAL_PENALTY = float(os.getenv('ZT_NEXT_DAY_LATE_RESEAL_PENALTY', '5.0'))

# ---- 推荐分级阈值 ----
ZT_NEXT_DAY_STRONG_THRESHOLD = float(os.getenv('ZT_NEXT_DAY_STRONG_THRESHOLD', '65.0'))
ZT_NEXT_DAY_RECOMMEND_THRESHOLD = float(os.getenv('ZT_NEXT_DAY_RECOMMEND_THRESHOLD', '50.0'))
ZT_NEXT_DAY_WATCH_THRESHOLD = float(os.getenv('ZT_NEXT_DAY_WATCH_THRESHOLD', '35.0'))
# 强烈推荐还需封板质量子分>=此值
ZT_NEXT_DAY_STRONG_SEAL_MIN = float(os.getenv('ZT_NEXT_DAY_STRONG_SEAL_MIN', '18.0'))
