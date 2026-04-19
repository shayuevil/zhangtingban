"""定时任务调度 - 每分钟刷新涨停池数据"""
import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

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

    # 启动时立即执行一次（注释掉，因为 data_fetcher 还未实现）
    # fetch_and_save_zt_pool(data_fetcher, storage)
    # fetch_sector_ranking(data_fetcher, storage)

    return scheduler
