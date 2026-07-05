from __future__ import annotations
import os
import re
import logging
from abc import ABC, abstractmethod
from pathlib import Path
import yaml

from domain.agent.schema import SkillInfo

logger = logging.getLogger(__name__)


class SkillProvider(ABC):
    """Skill 提供者抽象接口。

    当前实现：FileSkillProvider（从文件系统读取）
    未来可实现：DBSkillProvider（从数据库读取）
                RemoteSkillProvider（从远程市场读取）
    """

    @abstractmethod
    def list_skills(self) -> list[SkillInfo]:
        """返回所有 skill。"""

    @abstractmethod
    def get_skill(self, name: str) -> SkillInfo | None:
        """按名称获取 skill。"""


class FileSkillProvider(SkillProvider):
    """从 skills/ 目录读取 skill 定义。"""

    def __init__(self, skills_dir: Path) -> None:
        self._skills_dir = skills_dir
        self._skills: dict[str, SkillInfo] = {}
        self._load()

    def _load(self) -> None:
        if not self._skills_dir.exists():
            logger.warning("Skills dir not found: %s", self._skills_dir)
            return

        for skill_dir in self._skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill = self._parse_skill(skill_dir)
            if skill:
                self._skills[skill.name] = skill

    def _parse_skill(self, skill_dir: Path) -> SkillInfo | None:
        skill_md = skill_dir / "SKILL.md"
        yaml_file = skill_dir / "agents" / "openai.yaml"

        if not skill_md.exists():
            return None

        requires_env: list[str] = []
        skill_name = skill_dir.name
        description = ""

        try:
            content = skill_md.read_text(encoding="utf-8")
            fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            if fm_match:
                fm = yaml.safe_load(fm_match.group(1))
                full_name = fm.get("name", "")
                skill_name = full_name.split("@")[-1] if "@" in full_name else full_name
                description = fm.get("description", "")
                requires_env = fm.get("requires", {}).get("env", [])
        except Exception as e:
            logger.error("Failed to parse %s: %s", skill_md, e)

        display_name = skill_name
        default_prompt = ""
        tools: list[str] = []
        category: str = "general"

        if yaml_file.exists():
            try:
                data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                interface = data.get("interface", {})
                display_name = interface.get("display_name", skill_name)
                default_prompt = interface.get("default_prompt", "")
                tools = interface.get("tools", [])
                category = interface.get("category", "general")
                i18n = data.get("i18n", {})
                zh = i18n.get("zh", {})
                if zh.get("name"):
                    display_name = zh["name"]
                if zh.get("description"):
                    description = zh["description"]
            except Exception as e:
                logger.error("Failed to parse %s: %s", yaml_file, e)

        return SkillInfo(
            name=skill_name,
            display_name=display_name,
            description=description,
            default_prompt=default_prompt,
            requires_env=requires_env,
            env_configured=all(os.getenv(env) for env in requires_env),
            icon="🔧",
            tools=tools,
            category=category,
        )

    def list_skills(self) -> list[SkillInfo]:
        return list(self._skills.values())

    def get_skill(self, name: str) -> SkillInfo | None:
        return self._skills.get(name)
