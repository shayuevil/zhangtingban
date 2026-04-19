"""定时任务调度 - 每分钟刷新涨停池数据"""
import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


def fetch_and_save_zt_pool(data_fetcher, storage):
    """抓取并保存涨停池数据"""
    today = datetime.now().strftime("%Y-%m-%d")
    today_for_akshare = datetime.now().strftime("%Y%m%d")  # akshare需要YYYYMMDD格式
    logger.info(f"开始抓取 {today} 涨停池数据...")

    try:
        # 1. 获取涨停池
        zt_data = data_fetcher.get_zt_pool(today_for_akshare)
        if not zt_data:
            logger.warning("涨停池数据为空")
            return

        logger.info(f"获取到 {len(zt_data)} 只涨停股")

        # 2. 获取资金流向（批量）
        stock_codes = [s["code"] for s in zt_data]
        money_flow = data_fetcher.get_money_flow_batch(stock_codes, len(stock_codes))

        # 3. 合并数据 - 字段映射
        code_to_flow = {mf["code"]: mf for mf in money_flow}
        for stock in zt_data:
            flow = code_to_flow.get(stock["code"], {})
            # 资金流向字段映射
            stock["super_net_inflow"] = flow.get("super_large_order", 0)
            stock["big_net_inflow"] = flow.get("large_order", 0)
            stock["main_net_inflow"] = flow.get("main_force_inflow", 0)
            # 字段名映射: break_count -> explosion_count, consecutive_days -> continuous_days
            stock["explosion_count"] = stock.pop("break_count", 0)
            stock["continuous_days"] = stock.pop("consecutive_days", 1)
            # 行业字段映射
            stock["sector"] = stock.pop("industry", "")
            # 封板次数映射（如果有的话）
            stock["seal_count"] = stock.get("seal_count", 0)

        # 4. 保存到数据库
        count = storage.save_zt_pool(zt_data, today)
        logger.info(f"成功保存 {count} 条涨停数据")

    except Exception as e:
        logger.error(f"抓取涨停池失败: {e}")
        import traceback
        traceback.print_exc()


def fetch_sector_ranking(data_fetcher, storage):
    """抓取并保存板块排名"""
    today = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"开始抓取 {today} 板块数据...")

    try:
        sector_data = data_fetcher.get_sector_ranking()
        if sector_data:
            # 字段映射: sector -> name
            for sector in sector_data:
                sector["name"] = sector.pop("sector", "")
            count = storage.save_sector_ranking(sector_data, today)
            logger.info(f"成功保存 {count} 条板块数据")

    except Exception as e:
        logger.error(f"抓取板块数据失败: {e}")
        import traceback
        traceback.print_exc()


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

    return scheduler


def start_scheduler(data_fetcher, storage):
    """启动调度器（立即执行一次，然后开始定时）"""
    scheduler = create_scheduler(data_fetcher, storage)

    # 启动时立即执行一次
    logger.info("启动时立即执行一次数据抓取...")
    fetch_and_save_zt_pool(data_fetcher, storage)
    fetch_sector_ranking(data_fetcher, storage)

    # 启动调度器
    scheduler.start()
    logger.info("调度器已启动")

    return scheduler
