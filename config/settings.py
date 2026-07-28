"""
全局配置 — 因子权重、阈值、数据源等
继承并扩展 auction-stock-picker/config/settings.py
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# === 路径配置 ===
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
OUTPUT_DIR = DATA_DIR / "output"
LOG_DIR = PROJECT_ROOT / "logs"

for d in [CACHE_DIR, OUTPUT_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# === 部署模式 ===
DEPLOYMENT_MODE = os.getenv("DEPLOYMENT_MODE", "local")

# === 数据源配置 ===
REQUEST_INTERVAL = 0.5         # AKShare 请求间隔(秒)
EASTMONEY_TIMEOUT = 10         # 东方财富超时(秒)
MAX_RETRIES = 3                # 最大重试次数

# === 集合竞价配置 ===
AUCTION_START = "09:15:00"
AUCTION_END = "09:25:00"
SNAPSHOT_INTERVAL = 30         # 快照间隔(秒)
FINAL_SNAPSHOT_TIME = "09:24:30"

# === 筛选阈值 ===
MIN_MARKET_CAP = 20            # 最小流通市值(亿)
MAX_MARKET_CAP = 500           # 最大流通市值(亿)
MIN_AUCTION_CHANGE = 1.0       # 最小竞价涨幅(%)
MAX_AUCTION_CHANGE = 6.0       # 最大竞价涨幅(%)
MIN_VOLUME_RATIO = 1.5         # 最小竞价量比
MIN_AUCTION_AMOUNT = 100       # 最小竞价金额(万元)
LIMIT_UP_THRESHOLD = 9.5       # 涨停阈值(%)

# === 技术策略配置 ===
TREND_MA_SHORT = 5             # 短期均线
TREND_MA_MID = 20              # 中期均线
TREND_MA_LONG = 60             # 长期均线
TREND_MIN_VOLUME_RATIO = 1.5   # 最小放量倍数

REVERSAL_RSI_OVERSOLD = 30     # 超卖RSI
REVERSAL_MAX_DRAWDOWN = -20    # 最大回撤阈值(%)
REVERSAL_MIN_BOUNCE = 2.0      # 最小反弹(%)

# === 热点板块配置 ===
HOT_SECTOR_TOP_N = 20
MIN_SECTOR_STOCKS = 3

# === 因子权重配置 (总和100) ===
FACTOR_WEIGHTS = {
    "auction": 50,             # 竞价因子
    "sector": 0,               # 板块因子(东财不可用,待Tushare替代)
    "technical": 30,           # 技术因子
    "fundamental": 5,          # 基本面因子
    "capital": 15,             # 资金因子
}

# === 竞价因子子权重 ===
AUCTION_FACTOR_WEIGHTS = {
    "auction_change": 0.10,
    "volume_ratio": 0.10,
    "auction_amount": 0.05,
    "price_stability": 0.05,
    "volume_price_match": 0.05,
}

# === 板块因子子权重 ===
SECTOR_FACTOR_WEIGHTS = {
    "sector_rank": 0.10,
    "sector_fund_inflow": 0.08,
    "sector_persistence": 0.07,
}

# === 技术因子子权重 ===
TECHNICAL_FACTOR_WEIGHTS = {
    "ma_alignment": 0.06,
    "volume_breakout": 0.05,
    "relative_position": 0.05,
    "macd_signal": 0.04,
}

# === 基本面因子子权重 ===
FUNDAMENTAL_FACTOR_WEIGHTS = {
    "pe_percentile": 0.03,
    "revenue_growth": 0.03,
    "market_cap": 0.04,
}

# === 资金因子子权重 ===
CAPITAL_FACTOR_WEIGHTS = {
    "main_flow": 0.05,
    "north_flow": 0.03,
    "dragon_tiger": 0.02,
}

# === 扣分配置 ===
PENALTY_CONFIG = {
    "major_shareholder_reduction": -15,
    "earnings_warning": -20,
    "lockup_expiry": -10,
}

# === 止损/止盈 ===
STOP_LOSS_PCT = -0.03
TAKE_PROFIT_PCT = (0.05, 0.08)
TRAILING_STOP_PCT = 0.05       # 移动止损: 从最高点回落5%

# === 模拟盘配置 ===
SIM_INITIAL_CAPITAL = float(os.getenv("SIM_INITIAL_CAPITAL", "100000"))
SIM_MAX_POSITIONS = int(os.getenv("SIM_MAX_POSITIONS", "5"))
SIM_MAX_POSITION_PCT = float(os.getenv("SIM_MAX_POSITION_PCT", "0.25"))
SIM_COMMISSION = float(os.getenv("SIM_COMMISSION", "0.0005"))
SIM_STAMP_TAX = float(os.getenv("SIM_STAMP_TAX", "0.001"))
SIM_SLIPPAGE = float(os.getenv("SIM_SLIPPAGE", "0.001"))

# === 回测配置 ===
BACKTEST_CONFIG = {
    "commission": 0.0005,
    "stamp_tax": 0.001,
    "slippage": 0.001,
    "t_plus_1": True,
    "limit_up_down": True,     # 涨跌停约束
}

# === 通知配置 ===
# Server酱 SendKeys
SCT_SEND_KEYS_STR = os.getenv("SCT_SEND_KEYS", "")
SCT_SEND_KEYS = [k.strip() for k in SCT_SEND_KEYS_STR.split(",") if k.strip()]

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# === 日志配置 ===
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}"

# === LLM配置 (从 llm_config 导入时合并) ===
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "8000"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))

# === GA默认参数 ===
GA_POPULATION_SIZE_DAILY = int(os.getenv("GA_POPULATION_SIZE_DAILY", "20"))
GA_POPULATION_SIZE_WEEKLY = int(os.getenv("GA_POPULATION_SIZE_WEEKLY", "50"))
GA_POPULATION_SIZE_MONTHLY = int(os.getenv("GA_POPULATION_SIZE_MONTHLY", "100"))
GA_MAX_GENERATIONS_DAILY = int(os.getenv("GA_MAX_GENERATIONS_DAILY", "5"))
GA_MAX_GENERATIONS_WEEKLY = int(os.getenv("GA_MAX_GENERATIONS_WEEKLY", "20"))
GA_MAX_GENERATIONS_MONTHLY = int(os.getenv("GA_MAX_GENERATIONS_MONTHLY", "50"))
GA_PARALLEL_WORKERS = int(os.getenv("GA_PARALLEL_WORKERS", "4"))
GA_EARLY_STOP_GENERATIONS = int(os.getenv("GA_EARLY_STOP_GENERATIONS", "10"))
