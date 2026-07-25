from __future__ import annotations

from functools import cached_property
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field

from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="YUNHE_", extra="ignore")

    # ===== 项目根目录 =====
    project_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[1])

    # ===== LLM 配置 =====
    model: str = "qwen3.5-122b-a10b"
    api_key: str = ""
    base_url: str | None = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # ===== LLM 备用 Provider（P1-15：FallbackLLM 降级链）=====
    # 留空则不启用 fallback，仅使用主 provider。
    # 配置后，主 provider 故障（限流/连接错误/服务不可用）时自动切换到备用。
    fallback_api_key: str = ""
    fallback_base_url: str | None = None
    fallback_model: str = ""

    # ===== 数据目录 =====
    data_dir: Path = Field(default_factory=lambda: Settings._root() / "data")
    database_path: Path = Field(default_factory=lambda: Settings._root() / "data" / "yunhe.db")

    # ===== 日志 =====
    log_level: str = "DEBUG"
    log_dir: Path = Field(default_factory=lambda: Settings._root() / "data" / "logs")
    log_to_console: bool = True
    log_to_file: bool = True

    # ===== 审计 =====
    audit_enabled: bool = True
    audit_log_dir: Path = Field(default_factory=lambda: Settings._root() / "data" / "audit")
    # P2-3：审计日志保留天数，启动时自动清理超过保留期的 audit-YYYY-MM-DD.jsonl 文件
    audit_retention_days: int = 30

    # ===== Agent 运行参数 =====
    max_iterations: int = 15
    max_context_turns: int = 16
    max_context_chars: int = 400000
    max_history_messages: int = 12
    max_memory_items: int = 10
    memory_distill_threshold: int = 2
    memory_distill_min_convs: int = 1
    memory_stale_days: int = 90
    memory_stm_expire_days: int = 30
    memory_extraction_enabled: bool = True
    use_native_tool_calling: bool = True

    # ===== 安全策略 =====
    shell_timeout_seconds: int = 20
    allow_shell: bool = True
    allow_http: bool = True

    # ===== 后端存储 =====
    redis_url: str = "redis://localhost:6379/0"
    session_backend: str = "file"
    rate_limit_rpm: int = 60

    # ===== 监控 =====
    metrics_enabled: bool = True
    metrics_port: int = 9090

    # ===== 新闻来源治理 =====
    # 单一系统管理员 username，启动期解析为 user_id；空值表示未配置管理员。
    # 生产环境必须配置且对应用户必须存在，否则管理员 API 不可用。
    admin_username: str = ""

    # ===== 运行环境 =====
    # ``production`` 启用 fail-fast 行为；``development`` 允许宽松降级。
    # 由 ``YUNHE_ENVIRONMENT`` 环境变量控制；默认 ``development``。
    environment: str = "development"

    @staticmethod
    def _root() -> Path:
        return Path(__file__).resolve().parents[1]

    @cached_property
    def builtin_agents_dir(self) -> Path:
        return self.project_root / "application" / "builtin_agents"

    @cached_property
    def skills_dir(self) -> Path:
        return self.project_root / "infrastructure" / "skills" / "builtin"

    @cached_property
    def mcp_servers_dir(self) -> Path:
        return self.project_root / "infrastructure" / "mcp" / "servers"


settings = Settings()
