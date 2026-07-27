#!/usr/bin/env python3
"""架构分层依赖检查器（零容忍守卫）.

使用 ``ast.parse`` 扫描全部 Python 源文件，检测违反分层依赖规则的导入语句。
规则矩阵定义于 ``docs/superpowers/plans/2026-07-25-architecture-cleanup.md`` §4.P0
与 AGENTS.md §8 架构守卫：

- ``domain`` 不得导入 ``infrastructure``、``api``、``application``、``fastapi``，或具体外部 I/O SDK；
- ``application`` 不得导入 ``infrastructure``、``api``、``fastapi``；
- ``api`` 不得导入 ``infrastructure`` 或 ``domain`` 仓储实现模块（``domain.*.repository`` / ``domain.*.repositories``）；
- ``infrastructure`` 可以导入 domain 端口和模型，不得导入 ``api``。

覆盖的导入形式：顶层导入、函数/方法内导入、``TYPE_CHECKING`` 块导入、``try/except ImportError``
块导入、别名导入（``import x as y``）。相对导入（``from . import ...``）视为同包内导入，不检查。

P7 起：基线已归零并删除，本检查器改为零容忍——发现任何违规即以退出码 1 失败。
不允许通过 ``--baseline`` 或其他豁免机制绕过。

使用方式：

    # 默认检查当前目录
    python scripts/check_architecture.py

    # 指定扫描根目录
    python scripts/check_architecture.py --root .

退出码：

- 0 — 无违规
- 1 — 发现任何分层依赖违规
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

# ── 分层标识 ──────────────────────────────────────────────

LAYER_DOMAIN = "domain"
LAYER_APPLICATION = "application"
LAYER_API = "api"
LAYER_INFRASTRUCTURE = "infrastructure"

_CHECKED_LAYERS = frozenset({LAYER_DOMAIN, LAYER_APPLICATION, LAYER_API, LAYER_INFRASTRUCTURE})

# ── domain 禁止导入的具体外部 I/O SDK 顶层包名 ────────────
# 仅收录代表基础设施关注点的驱动/SDK；pydantic、typing 等通用工具不在此列。
FORBIDDEN_DOMAIN_SDKS = frozenset(
    {
        "sqlalchemy",
        "aiosqlite",
        "sqlite3",
        "openai",
        "anthropic",
        "httpx",
        "requests",
        "aiohttp",
        "urllib3",
        "bcrypt",
        "passlib",
        "cryptography",
        "fastapi",
        "starlette",
        "uvicorn",
        "redis",
        "mcp",
    }
)

# ── 扫描时跳过的目录名（非业务源码） ──────────────────────
_EXCLUDED_DIRS = frozenset(
    {
        "__pycache__",
        ".git",
        ".github",
        ".idea",
        ".trae",
        ".agents",
        ".codegraph",
        ".dbg",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        ".venv311",
        "frontend",
        "data",
        "node_modules",
        "dist",
        "build",
    }
)


# ── 违规条目 ──────────────────────────────────────────────


@dataclass(frozen=True)
class Violation:
    """单条分层依赖违规。

    Attributes:
        file: 相对根目录的文件路径，使用正斜杠以保证跨平台一致。
        line: 导入语句在源文件中的行号（1-based）。
        module: 被导入的模块全名（如 ``infrastructure.persistence.database``）。
        layer_rule: 触发的规则标识，用于后续分类清理。
    """

    file: str
    line: int
    module: str
    layer_rule: str

    def as_dict(self) -> dict:
        """返回可 JSON 序列化的字典表示。"""
        return asdict(self)

    def key(self) -> tuple[str, int, str, str]:
        """返回稳定标识元组（保留以便历史日志对比）。"""
        return (self.file, self.line, self.module, self.layer_rule)


# ── 文件发现与分层判定 ────────────────────────────────────


def _iter_python_files(root: Path) -> Iterable[Path]:
    """遍历根目录下所有 ``*.py`` 文件，跳过非业务源码目录。"""
    for path in root.rglob("*.py"):
        # 跳过位于排除目录下的文件
        if any(part in _EXCLUDED_DIRS for part in path.parts):
            continue
        yield path


def _layer_of(file_path: Path, root: Path) -> str | None:
    """根据文件相对路径的首段判定所属分层；非四层之一返回 None。"""
    try:
        rel = file_path.relative_to(root)
    except ValueError:
        return None
    parts = rel.parts
    if not parts:
        return None
    return parts[0] if parts[0] in _CHECKED_LAYERS else None


def _normalize_file_path(file_path: Path, root: Path) -> str:
    """返回使用正斜杠的相对路径字符串。"""
    return file_path.relative_to(root).as_posix()


# ── 导入语句抽取 ──────────────────────────────────────────


def _extract_imports(tree: ast.AST) -> Iterable[tuple[int, str]]:
    """从 AST 中抽取所有绝对导入语句。

    每项返回 ``(line_number, module_name)``。相对导入（``level > 0``）被跳过。
    覆盖 ``ast.Import``、``ast.ImportFrom``，包括函数内、TYPE_CHECKING 块和
    try/except 块中的导入——``ast.walk`` 会无差别遍历全部节点。
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield (node.lineno, alias.name)
        elif isinstance(node, ast.ImportFrom):
            # 跳过相对导入：level > 0 表示 from . / from .. 等
            if node.level and node.level > 0:
                continue
            if node.module is None:
                continue
            yield (node.lineno, node.module)


def _top_level_package(module: str) -> str:
    """返回模块全名的顶层包名（首个 ``.`` 之前的部分）。"""
    return module.split(".", 1)[0]


def _last_segment(module: str) -> str:
    """返回模块全名的末段（最后一个 ``.`` 之后的部分）。"""
    return module.rsplit(".", 1)[-1]


# ── 规则矩阵 ──────────────────────────────────────────────


def _check_domain_import(module: str) -> str | None:
    """对 domain 层文件应用规则；返回触发的 layer_rule 或 None。"""
    top = _top_level_package(module)
    if top == LAYER_INFRASTRUCTURE:
        return "domain_no_infrastructure"
    if top == LAYER_API:
        return "domain_no_api"
    if top == LAYER_APPLICATION:
        return "domain_no_application"
    if top == "fastapi":
        return "domain_no_fastapi"
    if top in FORBIDDEN_DOMAIN_SDKS:
        return "domain_no_io_sdk"
    return None


def _check_application_import(module: str) -> str | None:
    """对 application 层文件应用规则；返回触发的 layer_rule 或 None。"""
    top = _top_level_package(module)
    if top == LAYER_INFRASTRUCTURE:
        return "application_no_infrastructure"
    if top == LAYER_API:
        return "application_no_api"
    if top == "fastapi":
        return "application_no_fastapi"
    return None


def _check_api_import(module: str) -> str | None:
    """对 api 层文件应用规则；返回触发的 layer_rule 或 None。

    domain 仓储实现模块判定：模块路径以 ``domain.`` 开头且末段为
    ``repository`` 或 ``repositories``（含其子模块）。P2 已将这些实现迁至
    ``infrastructure/persistence/repositories/`` 并以端口替代。
    """
    top = _top_level_package(module)
    if top == LAYER_INFRASTRUCTURE:
        return "api_no_infrastructure"
    if top == LAYER_DOMAIN and _last_segment(module) in {"repository", "repositories"}:
        return "api_no_domain_repository_impl"
    return None


def _check_infrastructure_import(module: str) -> str | None:
    """对 infrastructure 层文件应用规则；返回触发的 layer_rule 或 None。"""
    top = _top_level_package(module)
    if top == LAYER_API:
        return "infrastructure_no_api"
    return None


def _rule_for_layer(layer: str, module: str) -> str | None:
    """根据文件分层派发到对应规则检查器。"""
    if layer == LAYER_DOMAIN:
        return _check_domain_import(module)
    if layer == LAYER_APPLICATION:
        return _check_application_import(module)
    if layer == LAYER_API:
        return _check_api_import(module)
    if layer == LAYER_INFRASTRUCTURE:
        return _check_infrastructure_import(module)
    return None


# ── 核心扫描 ──────────────────────────────────────────────


def find_violations(root: Path) -> list[Violation]:
    """扫描根目录下全部 Python 源文件，返回排序后的违规列表。

    Args:
        root: 扫描根目录。

    Returns:
        按 ``(file, line, module, layer_rule)`` 稳定排序的违规列表。
    """
    violations: list[Violation] = []
    for py_file in _iter_python_files(root):
        layer = _layer_of(py_file, root)
        if layer is None:
            continue
        try:
            source = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # 无法读取的文件跳过；不视为违规
            continue
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            # 语法错误的文件由 ruff/mypy 拦截；此处跳过避免误判
            continue
        rel_file = _normalize_file_path(py_file, root)
        for line_no, module in _extract_imports(tree):
            rule = _rule_for_layer(layer, module)
            if rule is not None:
                violations.append(
                    Violation(file=rel_file, line=line_no, module=module, layer_rule=rule)
                )
    violations.sort(key=lambda v: v.key())
    return violations


# ── CLI ───────────────────────────────────────────────────


def _format_violation(v: Violation, prefix: str = "  ") -> str:
    """格式化单条违规用于控制台输出。"""
    return f"{prefix}{v.file}:{v.line}  [{v.layer_rule}]  {v.module}"


def run_cli(argv: list[str] | None = None) -> int:
    """CLI 入口；返回进程退出码。

    P7 起：零容忍模式。无基线、无豁免；发现任何分层依赖违规即失败。

    Args:
        argv: 参数列表；为 None 时取 ``sys.argv[1:]``。

    Returns:
        0 表示通过（无违规），1 表示失败（发现违规）。
    """
    parser = argparse.ArgumentParser(
        description="架构分层依赖检查器（零容忍守卫）",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="扫描根目录（默认当前目录）",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    current = find_violations(root)

    if not current:
        print("架构检查通过：无分层依赖违规")
        return 0

    print(f"发现 {len(current)} 处分层依赖违规：", file=sys.stderr)
    for v in current:
        print(_format_violation(v), file=sys.stderr)
    return 1


def main() -> None:
    """脚本入口。"""
    sys.exit(run_cli())


if __name__ == "__main__":
    main()
