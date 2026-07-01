from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field

from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CLAW_",extra="ignore")

    model:str = "qwen3.5-122b-a10b"
    api_key:str = ""
    base_url:str | None = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    workspace: Path = Field(default_factory = lambda:Path.cwd())
    data_dir: Path = Field(default_factory=lambda: Path.cwd() / "data")
    max_iterations: int = 15
    max_context_turns:int = 16
    max_context_chars: int = 400000
    max_history_messages: int = 12
    max_memory_items: int = 10
    memory_distill_threshold: int = 2
    memory_distill_min_convs: int = 1
    memory_stale_days: int = 90
    memory_stm_expire_days: int = 30
    memory_extraction_enabled: bool = True
    log_level: str = "DEBUG"
    log_dir: Path = Field(default_factory=lambda: Path.cwd() / "data" / "logs")
    log_to_console: bool = True
    log_to_file: bool = True
    shell_timeout_seconds: int = 20
    allow_shell:bool = True
    allow_http:bool = True

    database_path: Path = Field(default_factory=lambda: Path.cwd() / "data" / "claw.db")

    redis_url: str = "redis://localhost:6379/0"
    session_backend: str = "file"
    rate_limit_rpm: int = 60

    emotion_enabled: bool = True
    emotion_backend: str = "local"

    use_native_tool_calling: bool = True

    audit_enabled: bool = True
    audit_log_dir: Path = Field(default_factory=lambda: Path.cwd() / "data" / "audit")

    metrics_enabled: bool = True
    metrics_port: int = 9090

settings = Settings()
