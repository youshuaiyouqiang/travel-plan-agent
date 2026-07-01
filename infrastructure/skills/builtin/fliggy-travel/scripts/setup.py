#!/usr/bin/env python3
"""飞猪 flyai-cli 安装与初始化脚本。"""

import os
import shutil
import subprocess
import sys


def check_cmd(name: str) -> str | None:
    return shutil.which(name)


def resolve_flyai_bin() -> str | None:
    env_bin = os.environ.get("FLYAI_BIN", "").strip()
    if env_bin and os.path.exists(env_bin):
        return env_bin

    flyai = shutil.which("flyai")
    if flyai:
        return flyai

    try:
        prefix = subprocess.check_output(["npm", "config", "get", "prefix"], text=True).strip()
    except Exception:
        return None

    candidate = os.path.join(prefix, "bin", "flyai")
    if os.path.exists(candidate):
        return candidate

    return None


def run(cmd: list[str], check: bool = True) -> int:
    print(f"  → {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False)
    if check and result.returncode != 0:
        print(f"  ✗ 命令失败 (exit {result.returncode})", file=sys.stderr)
    return result.returncode


def main():
    print("=== 飞猪 flyai-cli 安装 ===\n")

    node = check_cmd("node")
    npm = check_cmd("npm")
    if not node or not npm:
        print("✗ 未检测到 Node.js / npm，请先安装: https://nodejs.org/", file=sys.stderr)
        sys.exit(1)
    node_ver = subprocess.check_output(["node", "--version"]).decode().strip()
    print(f"✓ Node.js {node_ver}")

    flyai = resolve_flyai_bin()
    if flyai:
        print(f"✓ flyai-cli 已安装: {flyai}")
    else:
        print("○ flyai-cli 未安装，正在安装...")
        if run(["npm", "install", "-g", "@fly-ai/flyai-cli"]) != 0:
            sys.exit(1)
        print("✓ flyai-cli 安装完成")
        flyai = resolve_flyai_bin()

    if flyai:
        print(f"✓ flyai binary: {flyai}")
    else:
        print("⚠ 未找到 flyai 二进制，后续命令可能失败", file=sys.stderr)

    api_key = os.environ.get("FLYAI_API_KEY", "")
    if api_key:
        print("\n○ 检测到 FLYAI_API_KEY，正在写入配置...")
        if flyai:
            run([flyai, "config", "set", "FLYAI_API_KEY", api_key], check=False)
        else:
            run(["flyai", "config", "set", "FLYAI_API_KEY", api_key], check=False)
    else:
        print("\n○ 未检测到 FLYAI_API_KEY，基础查询可继续使用；如需增强功能可手动执行: flyai config set FLYAI_API_KEY <your-key>")

    print("\n=== 安装完成 ===")
    print("使用 flyai_quick.py 快速调用飞猪 API")


if __name__ == "__main__":
    main()
