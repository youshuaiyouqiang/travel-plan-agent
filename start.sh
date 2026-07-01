#!/usr/bin/env bash
# Claw 项目一键启动脚本（Bash 版，适用于 Git Bash / WSL / macOS）
# 启动后端 FastAPI（http://localhost:8000）和前端 Vite（http://localhost:5173）。
# 首次运行自动安装 Python 与前端依赖。Ctrl+C 退出时自动清理子进程。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
SKIP_INSTALL="${SKIP_INSTALL:-0}"

c_ok()   { printf "\033[32m[OK]\033[0m %s\n" "$1"; }
c_step() { printf "\n\033[36m[*]\033[0m %s\n" "$1"; }
c_warn() { printf "\033[33m[!]\033[0m %s\n" "$1"; }
c_err()  { printf "\033[31m[X]\033[0m %s\n" "$1"; }

# 子进程 PID 收集，退出时清理
BACKEND_PID=""
FRONTEND_PID=""
cleanup() {
    c_step "清理子进程"
    [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null || true
    [ -n "$BACKEND_PID" ]  && kill "$BACKEND_PID"  2>/dev/null || true
    c_ok "已退出"
}
trap cleanup EXIT INT TERM

# ---------- 1. 环境检查 ----------
c_step "环境检查"

if command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON="python"
else
    c_err "未找到 python / python3，请先安装 Python 3.10+"; exit 1
fi
c_ok "Python: $PYTHON ($($PYTHON --version 2>&1))"

if ! command -v npm >/dev/null 2>&1; then
    c_err "未找到 npm，请先安装 Node.js 18+"; exit 1
fi
c_ok "npm: $(npm --version)"

if [ ! -f ".env" ]; then
    c_warn "未找到 .env，从 .env.example 复制（请随后填入 API Key）"
    cp ".env.example" ".env"
fi

# ---------- 2. 依赖安装 ----------
if [ "$SKIP_INSTALL" != "1" ]; then
    c_step "检查 Python 依赖"
    if ! $PYTHON -c "import fastapi, uvicorn, openai" 2>/dev/null; then
        c_warn "安装 Python 依赖（requirements.txt）"
        $PYTHON -m pip install -r requirements.txt
    fi
    c_ok "Python 依赖就绪"

    c_step "检查前端依赖"
    if [ ! -d "frontend/node_modules" ]; then
        c_warn "安装前端依赖（首次较慢）"
        ( cd frontend && npm install )
    fi
    c_ok "前端依赖就绪"
else
    c_warn "跳过依赖安装 (SKIP_INSTALL=1)"
fi

# ---------- 3. 启动服务 ----------
c_step "启动后端 FastAPI (http://${BACKEND_HOST}:${BACKEND_PORT})"
$PYTHON -m uvicorn api.server:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" --reload &
BACKEND_PID=$!
c_ok "后端 PID=$BACKEND_PID"

c_step "启动前端 Vite (http://localhost:${FRONTEND_PORT})"
( cd frontend && PORT="$FRONTEND_PORT" npm run dev ) &
FRONTEND_PID=$!
c_ok "前端 PID=$FRONTEND_PID"

c_ok "两个服务已启动。按 Ctrl+C 退出并自动清理。"
echo "    后端: http://${BACKEND_HOST}:${BACKEND_PORT}"
echo "    前端: http://localhost:${FRONTEND_PORT}"
echo "    API 文档: http://${BACKEND_HOST}:${BACKEND_PORT}/docs"

wait
