#!/usr/bin/env python3
"""飞猪 flyai-cli 快速命令封装。"""

import argparse
import os
import shutil
import subprocess
import sys


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


def ensure_cli():
    if not resolve_flyai_bin():
        print("错误: flyai-cli 未安装，请先运行 setup.py", file=sys.stderr)
        sys.exit(1)


def run_cli(args: list[str]):
    flyai_bin = resolve_flyai_bin()
    if not flyai_bin:
        print("错误: flyai-cli 未安装，请先运行 setup.py", file=sys.stderr)
        sys.exit(1)
    cmd = [flyai_bin] + args
    print(f"→ {' '.join(cmd)}")
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


def cmd_search(args):
    ensure_cli()
    run_cli(["keyword-search", "--query", args.keyword])


def cmd_ai_search(args):
    ensure_cli()
    run_cli(["ai-search", "--query", args.query])


def cmd_flight(args):
    ensure_cli()
    cli_args = ["search-flight", "--origin", args.origin, "--destination", args.destination, "--dep-date", args.dep_date]
    run_cli(cli_args)


def cmd_train(args):
    ensure_cli()
    cli_args = ["search-train", "--origin", args.origin, "--destination", args.destination, "--dep-date", args.dep_date]
    run_cli(cli_args)


def cmd_hotel(args):
    ensure_cli()
    cli_args = ["search-hotel", "--dest-name", args.dest_name, "--check-in-date", args.check_in_date, "--check-out-date", args.check_out_date]
    run_cli(cli_args)


def main():
    parser = argparse.ArgumentParser(description="飞猪 flyai-cli 快速命令")
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search", help="关键词搜索")
    p_search.add_argument("--keyword", required=True, help="搜索关键词")

    p_ai = sub.add_parser("ai-search", help="AI 智能搜索")
    p_ai.add_argument("--query", required=True, help="搜索问题")

    p_flight = sub.add_parser("flight", help="机票搜索")
    p_flight.add_argument("--origin", required=True, help="出发城市")
    p_flight.add_argument("--destination", required=True, help="到达城市")
    p_flight.add_argument("--dep-date", "--date", dest="dep_date", required=True, help="出发日期 (YYYY-MM-DD)")

    p_train = sub.add_parser("train", help="火车票搜索")
    p_train.add_argument("--origin", required=True, help="出发城市")
    p_train.add_argument("--destination", required=True, help="到达城市")
    p_train.add_argument("--dep-date", "--date", dest="dep_date", required=True, help="出发日期 (YYYY-MM-DD)")

    p_hotel = sub.add_parser("hotel", help="酒店搜索")
    p_hotel.add_argument("--dest-name", required=True, help="目的地城市")
    p_hotel.add_argument("--check-in-date", "--checkin", dest="check_in_date", required=True, help="入住日期 (YYYY-MM-DD)")
    p_hotel.add_argument("--check-out-date", "--checkout", dest="check_out_date", required=True, help="离店日期 (YYYY-MM-DD)")

    args = parser.parse_args()
    {"search": cmd_search, "ai-search": cmd_ai_search,
     "flight": cmd_flight, "train": cmd_train, "hotel": cmd_hotel}[args.command](args)


if __name__ == "__main__":
    main()
