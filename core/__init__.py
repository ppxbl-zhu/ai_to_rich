"""核心框架 — Agent调度、事件总线、状态机"""
from core.event_bus import EventBus, EventType, Event, event_bus
from core.context_manager import TradingContext, get_context, reset_context
from core.state_machine import TradingStateMachine, TradingState, state_machine
from core.agent_runner import (
    AgentRunner, AgentRegistry, BaseAgent, AgentRunResult,
    agent_runner, agent_registry, setup_default_agents,
)
