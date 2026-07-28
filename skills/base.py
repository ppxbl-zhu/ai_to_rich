"""
Base Skill — 所有数据Skill的基类
每个Skill独立可调用、自带错误处理、可被LLM通过function calling发现
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from loguru import logger


class BaseSkill(ABC):
    """Skill基类 — 每个数据能力封装为一个Skill"""

    name: str = "base"
    description: str = ""
    schema: Dict = {}  # OpenAI function calling schema

    def __init__(self):
        self.last_result: Optional[Dict] = None
        self.call_count: int = 0

    @abstractmethod
    def execute(self, **kwargs) -> Dict[str, Any]:
        """执行Skill, 返回结构化结果"""
        ...

    def __call__(self, **kwargs) -> Dict[str, Any]:
        """可调用接口"""
        self.call_count += 1
        try:
            self.last_result = self.execute(**kwargs)
            return self.last_result
        except Exception as e:
            logger.error(f"[Skill:{self.name}] 执行失败: {e}")
            self.last_result = {"error": str(e), "skill": self.name}
            return self.last_result

    def to_tool_def(self) -> Dict:
        """转换为LLM function calling工具定义"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.schema,
            },
        }

    def is_available(self) -> bool:
        """检查Skill是否可用"""
        return True

    def get_info(self) -> Dict:
        return {
            "name": self.name,
            "description": self.description,
            "available": self.is_available(),
            "calls": self.call_count,
            "last_error": self.last_result.get("error") if self.last_result else None,
        }


class SkillRegistry:
    """Skill注册表 — 管理所有可用Skill"""

    def __init__(self):
        self._skills: Dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill):
        self._skills[skill.name] = skill
        logger.debug(f"[SkillRegistry] 注册: {skill.name}")

    def get(self, name: str) -> Optional[BaseSkill]:
        return self._skills.get(name)

    def list_all(self) -> List[BaseSkill]:
        return list(self._skills.values())

    def list_available(self) -> List[BaseSkill]:
        return [s for s in self._skills.values() if s.is_available()]

    def get_tool_defs(self) -> List[Dict]:
        """获取所有Skill的LLM工具定义"""
        return [s.to_tool_def() for s in self.list_available()]

    def execute(self, name: str, **kwargs) -> Dict[str, Any]:
        """按名称执行Skill"""
        skill = self.get(name)
        if not skill:
            return {"error": f"Skill '{name}' 未注册"}
        return skill(**kwargs)

    def get_infos(self) -> List[Dict]:
        return [s.get_info() for s in self._skills.values()]

    def __len__(self):
        return len(self._skills)


# 全局注册表
skill_registry = SkillRegistry()
