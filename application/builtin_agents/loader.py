from __future__ import annotations
import logging
from pathlib import Path
import yaml

from domain.agent.schema import AgentConfig

logger = logging.getLogger(__name__)


class BuiltinAgentLoader:
    """从 YAML 文件加载内置智能体配置。

    新增内置智能体只需在 agents/builtin/ 下加一个 YAML 文件，
    无需改任何代码。
    """

    def __init__(self, builtin_dir: Path) -> None:
        self._dir = builtin_dir

    def load_all(self) -> list[AgentConfig]:
        """扫描目录，加载所有 .yaml 配置文件。"""
        configs = []
        if not self._dir.exists():
            logger.warning("Builtin agents dir not found: %s", self._dir)
            return configs

        for yaml_file in sorted(self._dir.glob("*.yaml")):
            try:
                config = self._load_one(yaml_file)
                if config:
                    configs.append(config)
                    logger.info("Loaded builtin agent: %s", config.id)
            except Exception as e:
                logger.error("Failed to load %s: %s", yaml_file, e)

        return configs

    def _load_one(self, yaml_file: Path) -> AgentConfig | None:
        data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        return AgentConfig(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            icon=data.get("icon", "🤖"),
            system_prompt=data.get("system_prompt", ""),
            skills=data.get("skills", []),
            welcome_message=data.get("welcome_message", ""),
            temperature=data.get("temperature", 0.7),
            source="builtin",
        )
