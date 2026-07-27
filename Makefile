.PHONY: install dev lint format typecheck test run frontend clean help

# 默认目标
help: ## 显示所有可用命令
	@echo "Yunhe 通用智能体平台 — 开发命令"
	@echo ""
	@echo "  make install    安装后端依赖（含 dev 工具）"
	@echo "  make dev        安装后端 + 前端依赖"
	@echo "  make run        启动后端 + 前端（开发模式）"
	@echo "  make backend    仅启动后端"
	@echo "  make frontend   仅启动前端"
	@echo "  make lint       代码检查（ruff）"
	@echo "  make format     代码格式化（ruff）"
	@echo "  make typecheck  类型检查（mypy）"
	@echo "  make test       运行测试"
	@echo "  make clean      清理缓存文件"

install: ## 安装后端依赖
	pip install -e ".[dev]"

dev: install ## 安装后端 + 前端依赖
	cd frontend && npm install

run: ## 启动后端 + 前端
	@echo "启动后端 (http://127.0.0.1:8000) 和前端 (http://localhost:5173)..."
	@python -m uvicorn api.server:app --host 127.0.0.1 --port 8000 --reload &
	@cd frontend && npm run dev

backend: ## 仅启动后端
	python -m uvicorn api.server:app --host 127.0.0.1 --port 8000 --reload

frontend: ## 仅启动前端
	cd frontend && npm run dev

lint: ## 代码检查
	ruff check .

format: ## 代码格式化
	ruff format .
	ruff check --fix .

typecheck: ## 类型检查
	mypy api application config domain infrastructure

test: ## 运行测试（与 CI 一致的 coverage 命令）
	python -m pytest --cov=api --cov=application --cov=domain --cov=infrastructure --cov-fail-under=70

clean: ## 清理缓存
	@echo "清理 __pycache__ / .pytest_cache / .mypy_cache / .ruff_cache ..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "清理完成"
