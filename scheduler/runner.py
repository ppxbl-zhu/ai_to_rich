"""调度器入口"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

_scheduler: BackgroundScheduler = None


def start_scheduler():
    """启动调度器"""
    global _scheduler
    if _scheduler is not None:
        logger.warning("调度器已在运行")
        return

    _scheduler = BackgroundScheduler()

    # 注册定时任务

    # 每日凌晨数据刷新
    _scheduler.add_job(
        _run_data_refresh,
        CronTrigger(hour=0, minute=5),
        id="data_refresh",
        name="数据刷新",
    )

    # 每日GA微调 (凌晨2点)
    _scheduler.add_job(
        _run_daily_ga,
        CronTrigger(hour=2, minute=0),
        id="daily_ga",
        name="每日GA微调",
    )

    # 盘前研究 (8:00)
    _scheduler.add_job(
        _run_research,
        CronTrigger(hour=8, minute=0),
        id="morning_research",
        name="盘前市场调研",
    )

    # 竞价选股 (9:14:50)
    _scheduler.add_job(
        _run_auction_pick,
        CronTrigger(hour=9, minute=14, second=50),
        id="auction_pick",
        name="集合竞价选股",
    )

    # 尾盘扫描 (14:30)
    _scheduler.add_job(
        _run_eod_scan,
        CronTrigger(hour=14, minute=30),
        id="eod_scan",
        name="尾盘扫描",
    )

    # 盘后复盘 (15:30)
    _scheduler.add_job(
        _run_review,
        CronTrigger(hour=15, minute=30),
        id="daily_review",
        name="盘后复盘",
    )

    # 周末GA大种群优化 (周六全天)
    _scheduler.add_job(
        _run_weekly_ga,
        CronTrigger(day_of_week="sat", hour=0, minute=30),
        id="weekly_ga",
        name="周末GA优化",
    )

    _scheduler.start()
    logger.info("调度器已启动, 共注册 {} 个任务", len(_scheduler.get_jobs()))

    # 保持运行
    try:
        import signal
        signal.pause()
    except KeyboardInterrupt:
        _scheduler.shutdown()
        logger.info("调度器已停止")


def stop_scheduler():
    """停止调度器"""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown()
        _scheduler = None


def _run_data_refresh():
    from core.agent_runner import agent_runner
    logger.info("[调度] 数据刷新")
    # agent_runner.handle_scheduled("data_refresh")


def _run_daily_ga():
    from core.agent_runner import agent_runner
    logger.info("[调度] 每日GA微调")
    # agent_runner.handle_scheduled("ga_daily")


def _run_research():
    from core.agent_runner import agent_runner
    logger.info("[调度] 盘前市场调研")
    # agent_runner.handle_scheduled("research_agent")


def _run_auction_pick():
    from core.agent_runner import agent_runner
    logger.info("[调度] 集合竞价选股")
    # agent_runner.handle_scheduled("select_agent")


def _run_eod_scan():
    from core.agent_runner import agent_runner
    logger.info("[调度] 尾盘扫描")
    # agent_runner.handle_scheduled("eod_scan")


def _run_review():
    from core.agent_runner import agent_runner
    logger.info("[调度] 盘后复盘")
    # agent_runner.handle_scheduled("review_agent")


def _run_weekly_ga():
    from core.agent_runner import agent_runner
    logger.info("[调度] 周末GA大种群优化")
    # agent_runner.handle_scheduled("ga_weekly")
