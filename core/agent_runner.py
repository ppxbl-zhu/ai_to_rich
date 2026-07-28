"""
Agent Runner — Agent调度器
路由事件/时间触发到正确的Agent, 管理Agent生命周期
"""
from typing import Dict, Type, Optional, Any, Callable
from datetime import datetime
from loguru import logger

from core.event_bus import Event, EventType, event_bus
from core.context_manager import TradingContext, get_context, reset_context
from core.state_machine import TradingState, state_machine


class AgentStatus:
    """Agent运行状态"""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class AgentRunResult:
    """Agent执行结果"""

    def __init__(self, agent_name: str, status: str, output: Any = None,
                 error: str = None, duration_ms: float = 0, tokens_used: int = 0):
        self.agent_name = agent_name
        self.status = status
        self.output = output
        self.error = error
        self.duration_ms = duration_ms
        self.tokens_used = tokens_used
        self.timestamp = datetime.now()

    def __repr__(self):
        return f"AgentRunResult({self.agent_name}, {self.status}, {self.duration_ms:.0f}ms)"


class BaseAgent:
    """Agent基类 — 所有Agent继承此类"""

    agent_name: str = "base"
    agent_description: str = ""

    def __init__(self):
        self.status = AgentStatus.IDLE
        self.last_result: Optional[AgentRunResult] = None

    def run(self, context: TradingContext, **kwargs) -> AgentRunResult:
        """执行Agent (子类重写)"""
        raise NotImplementedError

    def can_run(self, context: TradingContext) -> bool:
        """检查是否可以运行 (子类可重写来添加前置条件)"""
        return True


class AgentRegistry:
    """Agent注册表"""

    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {}
        self._schedules: Dict[str, Dict] = {}       # agent_name -> schedule config
        self._event_handlers: Dict[EventType, list] = {}  # event_type -> [agent_names]

    def register(self, agent: BaseAgent):
        """注册Agent"""
        self._agents[agent.agent_name] = agent
        logger.info(f"注册Agent: {agent.agent_name} — {agent.agent_description}")

    def get(self, name: str) -> Optional[BaseAgent]:
        return self._agents.get(name)

    def list_agents(self) -> list:
        return [
            {"name": a.agent_name, "description": a.agent_description, "status": a.status}
            for a in self._agents.values()
        ]

    def schedule(self, agent_name: str, trigger_type: str, trigger_value: str,
                 enabled: bool = True):
        """为Agent注册调度规则"""
        self._schedules[agent_name] = {
            "trigger_type": trigger_type,     # "cron" | "event" | "state_change"
            "trigger_value": trigger_value,
            "enabled": enabled,
        }

    def bind_event(self, event_type: EventType, agent_name: str):
        """绑定Agent到事件"""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(agent_name)

    def get_event_agents(self, event_type: EventType) -> list:
        return self._event_handlers.get(event_type, [])


class AgentRunner:
    """
    Agent调度器
    1. 接收事件 → 路由到注册的Agent
    2. 接收定时触发 → 执行对应Agent
    3. 管理Agent执行上下文
    """

    def __init__(self, registry: AgentRegistry = None):
        self.registry = registry or AgentRegistry()
        self._run_history: list = []

    def run_agent(self, agent_name: str, context: TradingContext = None,
                  **kwargs) -> AgentRunResult:
        """同步运行一个Agent"""
        context = context or get_context()
        agent = self.registry.get(agent_name)

        if not agent:
            return AgentRunResult(agent_name, AgentStatus.FAILED,
                                  error=f"Agent未注册: {agent_name}")

        if not agent.can_run(context):
            return AgentRunResult(agent_name, AgentStatus.IDLE,
                                  error="前置条件不满足")

        t0 = datetime.now()
        try:
            logger.info(f"启动Agent: {agent_name}")
            agent.status = AgentStatus.RUNNING
            result = agent.run(context, **kwargs)
            agent.status = AgentStatus.COMPLETED
            agent.last_result = result
            self._run_history.append(result)
            return result
        except Exception as e:
            logger.error(f"Agent执行失败 {agent_name}: {e}")
            agent.status = AgentStatus.FAILED
            result = AgentRunResult(agent_name, AgentStatus.FAILED, error=str(e))
            agent.last_result = result
            self._run_history.append(result)
            return result

    def handle_event(self, event: Event):
        """处理事件 — 路由到绑定的Agent"""
        agent_names = self.registry.get_event_agents(event.type)
        if not agent_names:
            return

        context = get_context()
        for name in agent_names:
            # 事件处理的Agent异步执行(在当前实现中是同步, 但记录不阻塞)
            try:
                result = self.run_agent(name, context, event=event)
                if result.status == AgentStatus.FAILED:
                    logger.warning(f"事件处理失败: {event.type.value} -> {name}")
            except Exception as e:
                logger.error(f"事件处理异常: {event.type.value} -> {name}: {e}")

    def handle_scheduled(self, agent_name: str, context: TradingContext = None):
        """处理定时任务触发"""
        return self.run_agent(agent_name, context)

    def get_history(self, limit: int = 20) -> list:
        return self._run_history[-limit:]

    def get_status(self) -> dict:
        """获取所有Agent状态"""
        return {
            name: {
                "status": agent.status,
                "last_run": str(agent.last_result.timestamp) if agent.last_result else None,
                "last_duration_ms": agent.last_result.duration_ms if agent.last_result else 0,
            }
            for name, agent in self.registry._agents.items()
        }


# 全局单例
agent_registry = AgentRegistry()
agent_runner = AgentRunner(agent_registry)


def setup_default_agents():
    """
    注册默认Agent并绑定事件
    在应用启动时调用
    """
    from agents.research_agent import ResearchAgent
    from agents.select_agent import SelectAgent
    from agents.monitor_agent import MonitorAgent
    from agents.review_agent import ReviewAgent

    # 注册Agent
    agent_registry.register(ResearchAgent())
    agent_registry.register(SelectAgent())
    agent_registry.register(MonitorAgent())
    agent_registry.register(ReviewAgent())

    # 绑定事件
    agent_registry.bind_event(EventType.MARKET_OPEN, "monitor_agent")
    agent_registry.bind_event(EventType.MARKET_CLOSE, "review_agent")
    agent_registry.bind_event(EventType.ALERT_TRIGGERED, "monitor_agent")
    agent_registry.bind_event(EventType.STRATEGY_SIGNAL, "select_agent")
    agent_registry.bind_event(EventType.OPTIMIZATION_COMPLETE, "review_agent")

    logger.info(f"默认Agent注册完成: {agent_registry.list_agents()}")
