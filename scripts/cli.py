"""
QuantAgent CLI — 统一命令行入口
"""
import sys
import argparse
from pathlib import Path
from loguru import logger


def setup_logging(level: str = "INFO"):
    """配置日志"""
    logger.remove()
    logger.add(
        sys.stdout,
        level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        colorize=True,
    )


def cmd_init(args):
    """初始化数据库"""
    from data.storage.sqlite_storage import storage
    storage.init_db()
    logger.info("数据库初始化完成!")


def cmd_status(args):
    """显示系统状态"""
    from core.state_machine import state_machine
    from core.agent_runner import agent_registry, agent_runner
    from data.storage.sqlite_storage import storage

    # 更新状态机
    state_machine.update()

    print("=" * 50)
    print("  QuantAgent 系统状态")
    print("=" * 50)
    print(f"  交易日状态: {state_machine.state_label} ({state_machine.state.value})")
    print(f"  是否交易时段: {'是' if state_machine.is_trading else '否'}")

    print("\n--- Agent状态 ---")
    for a in agent_registry.list_agents():
        print(f"  {a['name']}: {a['status']} — {a['description']}")

    # 数据库状态
    stats = storage.get_trade_stats(30)
    print(f"\n--- 近30日交易统计 ---")
    print(f"  总交易: {stats.get('total', 0)}")
    print(f"  胜率: {stats.get('win_rate', 0):.1f}%")
    print(f"  总盈亏: {stats.get('total_pnl', 0):.2f}")

    print()


def cmd_run(args):
    """运行特定Agent"""
    from core.agent_runner import agent_runner, setup_default_agents
    from core.agent_runner import agent_registry

    # 确保Agent已注册
    if not agent_registry.get("research_agent"):
        try:
            setup_default_agents()
        except Exception as e:
            logger.warning(f"Agent注册跳过(可能部分依赖缺失): {e}")

    agent_name = args.agent
    agent = agent_registry.get(agent_name)
    if not agent:
        logger.error(f"未知Agent: {agent_name}")
        logger.info(f"可用Agent: {[a['name'] for a in agent_registry.list_agents()]}")
        return

    result = agent_runner.run_agent(agent_name)
    print(f"\nAgent执行结果: {result}")


def cmd_schedule(args):
    """启动调度器"""
    from scheduler.runner import start_scheduler
    logger.info("启动调度器...")
    start_scheduler()


def cmd_backtest(args):
    """运行回测"""
    logger.info(f"回测: {args.start} ~ {args.end}")
    try:
        from backtest.engine import BacktestEngine
        engine = BacktestEngine()
        result = engine.run(
            start_date=args.start,
            end_date=args.end,
            strategies=args.strategies.split(",") if args.strategies else None,
        )
        print(f"\n回测结果:\n{result}")
    except ImportError:
        logger.warning("回测引擎尚未实现")


def cmd_optimize(args):
    """运行GA优化"""
    logger.info(f"GA优化: 种群={args.population}, 代数={args.generations}")
    try:
        from optimizer.ga_engine import GAEngine
        engine = GAEngine(
            population_size=args.population,
            max_generations=args.generations,
        )
        result = engine.evolve()
        print(f"\n优化完成: 最优适应度={result.get('best_fitness', 'N/A')}")
    except ImportError:
        logger.warning("GA引擎尚未实现")


def cmd_web(args):
    """启动Web Dashboard"""
    logger.info(f"启动Web Dashboard: http://{args.host}:{args.port}")
    try:
        import uvicorn
        from web.app import app
        uvicorn.run(app, host=args.host, port=args.port)
    except ImportError:
        logger.warning("Web Dashboard尚未实现")


def main():
    parser = argparse.ArgumentParser(
        description="QuantAgent — AI驱动的量化交易系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  quant-agent init              # 初始化数据库
  quant-agent status            # 查看系统状态
  quant-agent run research      # 运行市场调研Agent
  quant-agent run select        # 运行选股Agent
  quant-agent backtest          # 运行回测
  quant-agent optimize          # 运行GA优化
  quant-agent web               # 启动Web仪表盘
        """,
    )

    parser.add_argument("--log-level", default="INFO", help="日志级别")

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # init
    subparsers.add_parser("init", help="初始化数据库")

    # status
    subparsers.add_parser("status", help="显示系统状态")

    # run
    run_parser = subparsers.add_parser("run", help="运行Agent")
    run_parser.add_argument("agent", help="Agent名称 (research|select|monitor|review)")

    # schedule
    subparsers.add_parser("schedule", help="启动定时调度器")

    # backtest
    bt_parser = subparsers.add_parser("backtest", help="运行回测")
    bt_parser.add_argument("--start", default="2021-01-01", help="开始日期")
    bt_parser.add_argument("--end", default="2026-06-30", help="结束日期")
    bt_parser.add_argument("--strategies", default=None, help="策略列表(逗号分隔)")

    # optimize
    opt_parser = subparsers.add_parser("optimize", help="运行GA优化")
    opt_parser.add_argument("--population", type=int, default=50, help="种群大小")
    opt_parser.add_argument("--generations", type=int, default=20, help="最大代数")

    # web
    web_parser = subparsers.add_parser("web", help="启动Web Dashboard")
    web_parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    web_parser.add_argument("--port", type=int, default=5001, help="监听端口")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    setup_logging(args.log_level)

    commands = {
        "init": cmd_init,
        "status": cmd_status,
        "run": cmd_run,
        "schedule": cmd_schedule,
        "backtest": cmd_backtest,
        "optimize": cmd_optimize,
        "web": cmd_web,
    }

    cmd = commands.get(args.command)
    if cmd:
        cmd(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
