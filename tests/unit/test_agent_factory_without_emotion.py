"""Task 2 删除情感识别的静态守卫测试。

覆盖范围：
- ``domain/user/emotion/`` 目录必须删除
- 关键模块不得再 import ``domain.user.emotion`` 或读取 ``CLAW_EMOTION_`` 配置
- ``Agent`` 构造器不得再接收 ``emotion_detector`` 参数
- ``ContextPreparer`` 与 ``ChatPreparation`` 不得再保留 emotion 字段
- 审计日志、Prometheus 指标不得保留 emotion 相关方法或收集器
- 用户画像不得保留 ``emotion_history`` 字段

设计要点：采用静态扫描而非启动 ``build_orchestrator``，避免引入真实 LLM/网络副作用。
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_emotion_module_directory_is_absent():
    emotion_dir = ROOT / "domain" / "user" / "emotion"
    assert not emotion_dir.exists(), f"emotion 模块目录仍存在：{emotion_dir}"


@pytest.mark.parametrize(
    "rel_path",
    [
        "app.py",
        "config/settings.py",
        "domain/travel/core.py",
        "domain/travel/services/context_preparer.py",
        "domain/travel/prompting.py",
        "domain/travel/prompt_context.py",
        "domain/shared/metrics/collector.py",
        "domain/shared/audit/logger.py",
        "domain/user/profile/manager.py",
        "domain/user/profile/schema.py",
    ],
)
def test_no_emotion_references_in_key_modules(rel_path: str):
    text = _read(ROOT / rel_path)
    assert "domain.user.emotion" not in text, f"{rel_path} 仍引用 domain.user.emotion"
    assert "EmotionDetector" not in text, f"{rel_path} 仍引用 EmotionDetector"
    assert "EmotionResult" not in text, f"{rel_path} 仍引用 EmotionResult"
    assert "CLAW_EMOTION_" not in text, f"{rel_path} 仍包含 CLAW_EMOTION_ 配置前缀"
    assert "emotion_detector" not in text, f"{rel_path} 仍包含 emotion_detector 标识符"
    assert "emotion_result" not in text, f"{rel_path} 仍包含 emotion_result 标识符"
    assert "emotion_history" not in text, f"{rel_path} 仍包含 emotion_history 标识符"
    assert "record_emotion" not in text, f"{rel_path} 仍包含 record_emotion 标识符"
    assert "log_emotion_detect" not in text, f"{rel_path} 仍包含 log_emotion_detect 标识符"


def test_metrics_collector_no_longer_registers_emotion_counter():
    collector_path = ROOT / "domain" / "shared" / "metrics" / "collector.py"
    text = _read(collector_path)
    assert "emotion_detected" not in text
    assert "record_emotion" not in text
    # 通过 AST 进一步确认没有 emotion 相关函数定义
    tree = ast.parse(text)
    function_names = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert "record_emotion" not in function_names


def test_audit_logger_no_longer_exposes_emotion_detect():
    logger_path = ROOT / "domain" / "shared" / "audit" / "logger.py"
    text = _read(logger_path)
    tree = ast.parse(text)
    method_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "log_emotion_detect" not in method_names
    assert "emotion_detect" not in text
    assert "emotion" not in text.lower(), "audit logger 仍包含 emotion 字样"


def test_agent_constructor_signature_has_no_emotion_parameter():
    from domain.travel.core import Agent

    sig = inspect.signature(Agent.__init__)
    assert "emotion_detector" not in sig.parameters, "Agent.__init__ 仍接收 emotion_detector 参数"


def test_context_preparer_no_longer_takes_emotion_detector():
    from domain.travel.services.context_preparer import ChatPreparation, ContextPreparer

    preparer_sig = inspect.signature(ContextPreparer.__init__)
    assert "emotion_detector" not in preparer_sig.parameters

    # ChatPreparation 数据类不得保留 emotion_result 字段
    fields = {f.name for f in ChatPreparation.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    assert "emotion_result" not in fields
    assert "emotion_context" not in fields


def test_prompt_context_no_longer_carries_emotion_context():
    from domain.travel.prompt_context import PromptContext

    fields = {f.name for f in PromptContext.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    assert "emotion_context" not in fields


def test_user_profile_schema_no_longer_carries_emotion_history():
    from domain.user.profile.schema import UserProfile

    fields = {f.name for f in UserProfile.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    assert "emotion_history" not in fields


def test_settings_no_longer_exposes_emotion_flags():
    from config.settings import Settings

    # Pydantic Settings 通过 model_fields 暴露字段
    field_names = set(Settings.model_fields.keys())
    assert "emotion_enabled" not in field_names
    assert "emotion_backend" not in field_names
