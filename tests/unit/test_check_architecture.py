"""``scripts/check_architecture.py`` 的单元测试。

P7 起：基线已删除，检查器改为零容忍模式。覆盖分层依赖规则的检测能力：
- 顶层导入、函数内导入、TYPE_CHECKING 块导入、别名导入
- domain/application/api/infrastructure 四层规则矩阵
- 零容忍 CLI 行为：无违规通过；任何违规即失败
- 文件路径使用正斜杠以保证跨平台一致
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_architecture.py"


def _load_checker_module():
    """以模块方式加载 ``scripts/check_architecture.py``，避免污染 sys.path。"""
    spec = importlib.util.spec_from_file_location("check_architecture", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_architecture"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def checker():
    """加载架构检查器模块。"""
    return _load_checker_module()


def _write(root: Path, rel: str, content: str) -> None:
    """在临时根目录下写入相对路径文件。"""
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _violations_as_set(violations) -> set[tuple[str, int, str, str]]:
    """把 Violation 列表归一化为可比较的元组集合。"""
    return {(v.file, v.line, v.module, v.layer_rule) for v in violations}


def test_domain_top_level_infrastructure_import_detected(checker, tmp_path):
    """domain 顶层 import infrastructure 必须被识别。"""
    _write(
        tmp_path,
        "domain/sample/agent.py",
        "from infrastructure.llm.openai import OpenAILLM\n",
    )
    violations = checker.find_violations(tmp_path)
    assert _violations_as_set(violations) == {
        ("domain/sample/agent.py", 1, "infrastructure.llm.openai", "domain_no_infrastructure"),
    }


def test_domain_function_level_import_detected(checker, tmp_path):
    """domain 函数内 import infrastructure 必须被识别。"""
    _write(
        tmp_path,
        "domain/sample/service.py",
        "def f():\n    from infrastructure.persistence.database import get_connection\n    return get_connection\n",
    )
    violations = checker.find_violations(tmp_path)
    assert _violations_as_set(violations) == {
        ("domain/sample/service.py", 2, "infrastructure.persistence.database", "domain_no_infrastructure"),
    }


def test_domain_type_checking_block_import_detected(checker, tmp_path):
    """domain 在 TYPE_CHECKING 块中 import application 必须被识别。"""
    _write(
        tmp_path,
        "domain/sample/typed.py",
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from application.session.schema import SessionMode\n",
    )
    violations = checker.find_violations(tmp_path)
    assert _violations_as_set(violations) == {
        ("domain/sample/typed.py", 3, "application.session.schema", "domain_no_application"),
    }


def test_domain_aliased_import_detected(checker, tmp_path):
    """domain 别名 import fastapi 必须被识别。"""
    _write(
        tmp_path,
        "domain/sample/api_shim.py",
        "import fastapi as fa\n",
    )
    violations = checker.find_violations(tmp_path)
    assert _violations_as_set(violations) == {
        ("domain/sample/api_shim.py", 1, "fastapi", "domain_no_fastapi"),
    }


def test_domain_io_sdk_import_detected(checker, tmp_path):
    """domain 导入外部 I/O SDK 必须被识别。"""
    _write(
        tmp_path,
        "domain/sample/db_shim.py",
        "import sqlalchemy\nimport openai\nimport bcrypt\n",
    )
    violations = checker.find_violations(tmp_path)
    assert _violations_as_set(violations) == {
        ("domain/sample/db_shim.py", 1, "sqlalchemy", "domain_no_io_sdk"),
        ("domain/sample/db_shim.py", 2, "openai", "domain_no_io_sdk"),
        ("domain/sample/db_shim.py", 3, "bcrypt", "domain_no_io_sdk"),
    }


def test_application_infrastructure_import_detected(checker, tmp_path):
    """application 导入 infrastructure 必须被识别。"""
    _write(
        tmp_path,
        "application/news/service.py",
        "from infrastructure.persistence.news_repository import NewsSourceRepository\n",
    )
    violations = checker.find_violations(tmp_path)
    assert _violations_as_set(violations) == {
        ("application/news/service.py", 1, "infrastructure.persistence.news_repository", "application_no_infrastructure"),
    }


def test_application_fastapi_import_detected(checker, tmp_path):
    """application 导入 fastapi 必须被识别。"""
    _write(
        tmp_path,
        "application/web/dep.py",
        "from fastapi import Depends\n",
    )
    violations = checker.find_violations(tmp_path)
    assert _violations_as_set(violations) == {
        ("application/web/dep.py", 1, "fastapi", "application_no_fastapi"),
    }


def test_application_domain_import_allowed(checker, tmp_path):
    """application 导入 domain 模型/仓储不是违规（规则只禁止 infra/api/fastapi）。"""
    _write(
        tmp_path,
        "application/authz/service.py",
        "from domain.travel.itinerary.repository import ItineraryRepository\n",
    )
    violations = checker.find_violations(tmp_path)
    assert violations == []


def test_api_infrastructure_import_detected(checker, tmp_path):
    """api 导入 infrastructure 必须被识别。"""
    _write(
        tmp_path,
        "api/v1/session.py",
        "from infrastructure.persistence.database import get_connection\n",
    )
    violations = checker.find_violations(tmp_path)
    assert _violations_as_set(violations) == {
        ("api/v1/session.py", 1, "infrastructure.persistence.database", "api_no_infrastructure"),
    }


def test_api_domain_repository_import_detected(checker, tmp_path):
    """api 导入 domain 仓储实现模块必须被识别。"""
    _write(
        tmp_path,
        "api/v1/feedback.py",
        "from domain.feedback.repository import FeedbackRepository\n",
    )
    violations = checker.find_violations(tmp_path)
    assert _violations_as_set(violations) == {
        ("api/v1/feedback.py", 1, "domain.feedback.repository", "api_no_domain_repository_impl"),
    }


def test_api_domain_model_import_allowed(checker, tmp_path):
    """api 导入 domain 模型/Schema（非 repository 模块）不是违规。"""
    _write(
        tmp_path,
        "api/v1/agent.py",
        "from domain.agent.schema import AgentConfig\n",
    )
    violations = checker.find_violations(tmp_path)
    assert violations == []


def test_infrastructure_api_import_detected(checker, tmp_path):
    """infrastructure 导入 api 必须被识别。"""
    _write(
        tmp_path,
        "infrastructure/persistence/shim.py",
        "from api.v1 import router\n",
    )
    violations = checker.find_violations(tmp_path)
    assert _violations_as_set(violations) == {
        ("infrastructure/persistence/shim.py", 1, "api.v1", "infrastructure_no_api"),
    }


def test_infrastructure_domain_import_allowed(checker, tmp_path):
    """infrastructure 导入 domain 端口/模型不是违规。"""
    _write(
        tmp_path,
        "infrastructure/persistence/repositories/session.py",
        "from domain.user.session.ports import SessionPort\n",
    )
    violations = checker.find_violations(tmp_path)
    assert violations == []


def test_tests_and_scripts_not_checked(checker, tmp_path):
    """tests/ 和 scripts/ 目录不参与分层规则检查。"""
    _write(tmp_path, "tests/unit/test_x.py", "from infrastructure.persistence.database import get_connection\n")
    _write(tmp_path, "scripts/helper.py", "from infrastructure.persistence.database import get_connection\n")
    violations = checker.find_violations(tmp_path)
    assert violations == []


def test_relative_intra_package_import_allowed(checker, tmp_path):
    """同层相对导入不违规。"""
    _write(
        tmp_path,
        "domain/agent/factory.py",
        "from .schema import AgentConfig\nfrom ..shared.types import Identifier\n",
    )
    violations = checker.find_violations(tmp_path)
    assert violations == []


def test_file_paths_use_forward_slash(checker, tmp_path):
    """违规条目的 file 字段必须使用正斜杠，保证 CI 跨平台一致。"""
    _write(
        tmp_path,
        "domain/deep/nested/file.py",
        "import infrastructure\n",
    )
    violations = checker.find_violations(tmp_path)
    assert len(violations) == 1
    assert "\\" not in violations[0].file
    assert violations[0].file == "domain/deep/nested/file.py"


# ── 零容忍 CLI 测试（P7 新增） ─────────────────────────────


def test_cli_no_violations_passes(checker, tmp_path):
    """零容忍模式：无违规时退出码 0。"""
    _write(tmp_path, "domain/sample/agent.py", "from dataclasses import dataclass\n")
    _write(tmp_path, "api/v1/route.py", "from fastapi import APIRouter\n")
    rc = checker.run_cli(["--root", str(tmp_path)])
    assert rc == 0


def test_cli_any_violation_fails(checker, tmp_path):
    """零容忍模式：任何违规立即退出码 1。"""
    _write(tmp_path, "domain/sample/agent.py", "import infrastructure\n")
    rc = checker.run_cli(["--root", str(tmp_path)])
    assert rc == 1


def test_cli_multiple_violations_all_reported(checker, tmp_path):
    """零容忍模式：多条违规必须全部报告。"""
    _write(tmp_path, "domain/a.py", "import infrastructure\n")
    _write(tmp_path, "domain/b.py", "import fastapi\n")
    _write(tmp_path, "api/v1/x.py", "import infrastructure\n")
    rc = checker.run_cli(["--root", str(tmp_path)])
    assert rc == 1


def test_cli_root_defaults_to_current(checker, tmp_path, monkeypatch):
    """--root 缺省时扫描当前工作目录。"""
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "domain/sample/agent.py", "import infrastructure\n")
    rc = checker.run_cli([])
    assert rc == 1
