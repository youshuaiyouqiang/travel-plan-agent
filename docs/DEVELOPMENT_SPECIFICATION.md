# Claw7 开发规范文档（AI 开发强制约束）

> **文档性质**：长期开发规范，约束所有后续开发（含 AI 辅助开发）的日常编码行为。
>
> **适用项目**：Claw7 多智能体旅游规划系统
>
> **覆盖范围**：后端（Python/FastAPI）。前端（React/TSX）规范另行维护。
>
> **配套文档**：`DEVELOPMENT_STANDARDS.md`（现状评估 + 一次性重构路线图）。本文件是**长期规范**，STANDARDS 是**改造计划**，两者不冲突。
>
> **最后更新**：2026-07-05
>
> **版本**：v2.1（基于 v2.0 修正过时状态描述，同步项目重构后的实际配置）

---

## 🚨 重要声明

**本规范是强制性标准，违反规范将导致代码被拒绝合并。**

- ✅ **必须**：标注为"必须""严禁"的条款，违反即拒绝合并
- ⚠️ **应该**：标注为"应该""不应该"的条款，强烈建议遵守
- 💡 **可以**：标注为"可以""建议"的条款，酌情采纳

> ⚠️ **与 v1.0 的关键差异**：v1.0 错误地要求使用 Black/isort/flake8（项目实际用 Ruff）、Pydantic v1 写法（项目用 v2）、InnoDB/utf8mb4（项目用 SQLite）。v2.0 已全部修正为项目真实技术栈。v2.1 进一步同步了重构后的实际状态。

---

## 📋 目录

1. [技术栈基线](#1-技术栈基线)
2. [代码组织规范](#2-代码组织规范)
3. [命名规范](#3-命名规范)
4. [数据库规范](#4-数据库规范)
5. [错误处理规范](#5-错误处理规范)
6. [输入验证规范](#6-输入验证规范)
7. [安全规范](#7-安全规范)
8. [测试规范](#8-测试规范)
9. [API 设计规范](#9-api-设计规范)
10. [文档与注释规范](#10-文档与注释规范)
11. [性能规范](#11-性能规范)
12. [代码审查清单](#12-代码审查清单)
13. [禁止事项](#13-禁止事项)
14. [工具与配置](#14-工具与配置)
15. [开发流程](#15-开发流程)
16. [附录：快速参考](#16-附录快速参考)

---

## 1. 技术栈基线

> ⚠️ **本节为强制基线**。所有代码必须基于以下技术栈，禁止擅自更换。

| 维度 | 选型 | 版本 | 说明 |
|------|------|------|------|
| Python | CPython | **>= 3.11** | `pyproject.toml: requires-python` |
| Web 框架 | FastAPI | >= 0.110.0 | 异步框架 |
| 数据验证 | Pydantic | **>= 2.5.0（v2 API）** | 禁止使用 v1 API |
| 数据库 | SQLite | sqlite3 标准库 | 当前引擎，非 MySQL/PostgreSQL |
| LLM SDK | openai | >= 1.0.0 | |
| 缓存/限流 | redis | >= 5.0.0 | 已声明依赖 |
| 监控 | prometheus-client | >= 0.20.0 | |
| 代码风格 | **Ruff** | >= 0.4.0 | **替代** Black/isort/flake8，勿再引入 |
| 类型检查 | mypy | >= 1.10.0 | |
| 测试 | pytest + pytest-asyncio | >= 8.0.0 | `asyncio_mode = "auto"` |

### 1.1 类型注解约定（Python 3.11+）

```python
# ✅ 正确：使用内置泛型 + X | None
def get_user(user_id: str) -> User | None: ...
def list_users() -> list[User]: ...
def count() -> dict[str, int]: ...
def check() -> tuple[bool, str]: ...

# ❌ 错误：旧写法
from typing import List, Dict, Tuple, Optional  # 禁止
def get_user(user_id: str) -> Optional[User]: ...  # 用 X | None
def list_users() -> List[User]: ...  # 用 list[User]
```

### 1.2 Pydantic v2 约定

```python
# ✅ 正确（v2）
from pydantic import BaseModel, Field, field_validator, ConfigDict

class RegisterRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"username": "test_user"}}
    )
    username: str = Field(..., min_length=2, max_length=32)
    
    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        return v

# ❌ 错误（v1 写法，已废弃，禁止使用）
class RegisterRequest(BaseModel):
    class Config:                    # v1，改用 model_config
        schema_extra = {...}
    @validator("username")           # v1，改用 @field_validator
    def validate_username(cls, v):   # 缺少 @classmethod
        return v
    items: list = Field(..., min_items=1)  # v1，改用 min_length
    code: str = Field(..., regex="...")    # v1，改用 pattern
```

---

## 2. 代码组织规范

### 2.1 文件大小限制

**必须**：
- 单文件 ≤ 400 行（含空行和注释）
- 单函数 ≤ 50 行
- 单类 ≤ 300 行
- 圈复杂度 ≤ 10

⚠️ **应该**：
- 单文件 ≤ 200 行
- 单函数 ≤ 30 行

> 💡 **说明**：行数仅作警戒线，核心是"单一职责 + 高内聚低耦合"。某些 ORM 模型聚合、配置表可超限，但需在文件头注释说明原因。

**违规示例**：
```python
# ❌ 违规：文件过大
# api/server.py（重构前 1539 行）—— 已按资源拆分到 api/v1/（当前 ~127 行）
```

### 2.2 目录结构

> 保持项目现有 DDD 分层，`domain/` 按业务领域划分（非按技术分层）。

```
claw7/
├── api/                        # API 层
│   ├── server.py              # 仅 app 创建 + 全局配置（< 200 行）
│   ├── deps.py                # 依赖注入
│   ├── middleware/            # 中间件（auth、error_handler）
│   └── v1/                    # API v1（按资源拆分，15 个模块）
│       ├── __init__.py        # router 聚合 + 旧路由重定向
│       ├── auth.py            # 认证
│       ├── chat.py            # 对话
│       ├── session.py         # 会话管理 + 方案确认
│       ├── agent.py           # 智能体 CRUD
│       ├── skill.py           # 技能
│       ├── mcp.py             # MCP 服务器/工具
│       ├── itinerary.py       # 行程
│       ├── album.py           # 相册
│       ├── memory.py          # 记忆
│       ├── news.py            # 新闻/热搜
│       ├── geocode.py         # 地理编码
│       ├── share.py           # 分享
│       ├── debug.py           # 调试
│       ├── health.py          # 健康检查
│       └── feedback.py        # 反馈
├── application/               # 应用层
│   ├── exceptions/            # 自定义异常（8 个异常类）
│   ├── dto/                   # 请求/响应模型
│   │   ├── request/           # 18 个请求 DTO
│   │   └── response/          # 3 个响应 DTO
│   └── scheduler.py           # 定时任务
├── domain/                    # 领域层（按业务领域划分）
│   ├── agent/                 # 智能体（含 orchestrator）
│   ├── travel/                # 旅游
│   │   ├── services/          # 旅行服务类（core.py 拆分后）
│   │   │   ├── context_preparer.py
│   │   │   ├── early_action_handler.py
│   │   │   ├── itinerary_generator.py
│   │   │   ├── cache_manager.py
│   │   │   ├── prompt_helper.py
│   │   │   └── memory_processor.py
│   │   └── core.py            # Agent 主类（~290 行）
│   ├── user/                  # 用户
│   ├── reasoning/             # 推理
│   ├── memory/                # 记忆
│   ├── feedback/              # 反馈
│   └── shared/                # 共享
├── infrastructure/            # 基础设施层
│   ├── persistence/           # 持久化（database.py + 迁移函数）
│   ├── llm/                   # LLM 客户端（含 FallbackLLM）
│   ├── mcp/                   # MCP
│   ├── tools/                 # 工具
│   ├── skills/                # 技能
│   ├── security/              # 安全（password.py - bcrypt）
│   └── cache/                 # 缓存（rate_limit.py - Redis 限流）
├── config/                    # 配置
│   └── settings.py
├── tests/                     # 测试
│   ├── unit/                  # 单元测试（9 个模块）
│   ├── integration/           # 集成测试（6 个模块）
│   └── e2e/                   # 端到端（占位）
└── frontend/                  # 前端（规范另行维护）
```

### 2.3 依赖方向

**必须**：
```
API 层 → 应用层 → 领域层
                 ↓
           基础设施层
```

**严禁**：
- 领域层依赖应用层
- 领域层直接依赖基础设施层（应通过接口/抽象）
- 同层之间的循环依赖

```python
# ✅ 合规：上层依赖下层
# api/v1/auth.py
from application.service.auth import AuthService

# ✅ 合规：领域层通过抽象依赖基础设施（依赖倒置）
# domain/service/auth.py
from domain.shared.repository import IUserRepository  # 接口，非具体实现

# ❌ 违规：领域层直接 import 基础设施具体类
# domain/service/auth.py
from infrastructure.persistence.repository.user import UserRepository  # 严禁
```

---

## 3. 命名规范

### 3.1 类名

**必须**：PascalCase（大驼峰），名词或名词短语，清晰表达职责。

```python
# ✅ 合规
class UserAuthService: ...
class ItineraryRepository: ...
class CreateItineraryRequest: ...

# ❌ 违规
class user_auth_service: ...  # 小写
class Auth: ...               # 不清晰
```

### 3.2 函数/方法名

**必须**：snake_case，动词或动词短语。

```python
# ✅ 合规
def get_user_by_id(user_id: str) -> User: ...
def create_itinerary(request: CreateItineraryRequest) -> Itinerary: ...

# ❌ 违规
def getUser(user_id): ...     # 驼峰
def user(id): ...             # 不清晰
```

### 3.3 变量名

**必须**：snake_case，清晰表达含义，避免单字母（循环变量除外）。

```python
# ✅ 合规
user_id = "123"
for index, item in enumerate(items): ...

# ❌ 违规
userId = "123"                # 驼峰
x = "123"                     # 不清晰
```

### 3.4 常量名

**必须**：UPPER_SNAKE_CASE。

```python
# ✅ 合规
MAX_RETRY_COUNT = 3
DEFAULT_TIMEOUT = 30
API_VERSION = "v1"

# ❌ 违规
maxRetryCount = 3             # 驼峰
default_timeout = 30          # 小写
```

### 3.5 私有成员

**必须**：
- 私有/保护成员：前缀单下划线 `_`
- 名称改写（强私有）：前缀双下划线 `__`
- 魔术方法：前后双下划线 `__xxx__`

```python
class UserService:
    def __init__(self):
        self._users = []           # 保护成员
        self.__secret_key = "xxx"  # 强私有（名称改写）
    
    def _validate_input(self): ... # 私有方法
    def __str__(self): ...         # 魔术方法
```

---

## 4. 数据库规范

> ⚠️ **项目使用 SQLite**（`sqlite3` 标准库），非 MySQL/PostgreSQL。以下规范针对 SQLite 适配，**禁止**使用 InnoDB/utf8mb4 等 MySQL 专有概念。

### 4.1 查询安全

**必须**：
- 所有 SQL 参数化：`conn.execute("... WHERE id = ?", (id,))`
- **严禁** f-string 拼接 SQL
- **严禁** `%` 格式化拼接 SQL

> ✅ **当前状态**：项目已全面参数化。`api/v1/memory.py` 中存在少量 f-string SQL，但表名来自硬编码白名单常量（非用户输入），参数仍使用 `?` 占位符，属于安全模式。

### 4.2 数据库迁移

**必须**：
- 使用项目现有的版本化迁移系统（`schema_migrations` 追踪表 + `_upgrade_N`/`_downgrade_N` 函数）
- 每次迁移必须同时提供 `_upgrade_N` 和 `_downgrade_N` 函数
- 修改表结构必须创建新的迁移版本
- 迁移记录自动存入 `schema_migrations` 表

⚠️ **应该**：
- 迁移函数添加 docstring 说明变更内容
- 一个迁移版本只做一件事
- SQLite 不支持 `DROP COLUMN`（3.35 以前），downgrade 时记录警告即可

> 💡 **当前状态**：项目已有 10 个版本化迁移（`_upgrade_1` ~ `_upgrade_10`），覆盖 experience_tag、actual_cost、custom_agents、mcp_servers、delegation、quality_issues、news_favorites、sessions.user_id、itineraries 多方案、sessions 确认列。

```python
# ✅ 合规：项目迁移系统
# infrastructure/persistence/database.py

def _upgrade_11(conn) -> None:
    """迁移 11：新增 xxx 列"""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(table_name)").fetchall()}
    if "new_column" not in cols:
        conn.execute("ALTER TABLE table_name ADD COLUMN new_column TEXT DEFAULT ''")
        conn.commit()

def _downgrade_11(conn) -> None:
    """迁移 11 回滚：SQLite 无法 DROP COLUMN，记录警告"""
    logger.warning("Migration 11 downgrade: SQLite cannot DROP COLUMN")

# 注册迁移
_MIGRATIONS = {
    11: ("新增 xxx 列", _upgrade_11, _downgrade_11),
}
```

### 4.3 表设计（SQLite 适配）

**必须**：
- 主键：保持现有 `TEXT` 类型（如 `user_id`），保证兼容性
- 必须包含 `created_at`、`updated_at` 字段
- 软删除使用 `deleted_at` 字段（而非物理删除）

⚠️ **应该**：
- 添加表注释（SQLite 用 `--` 注释或应用层文档）
- 高频查询字段建索引

> ❌ **禁止**：要求 `InnoDB 引擎`、`utf8mb4 字符集`、`BIGINT AUTO_INCREMENT` —— 这些是 MySQL 概念，SQLite 不支持。

```sql
-- ✅ 合规：SQLite 表结构
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
```

### 4.4 索引设计

**必须**：
- 主键自动创建索引
- 外键字段必须建索引
- 高频查询条件字段必须建索引

⚠️ **应该**：
- 唯一约束使用 `UNIQUE`
- 避免过度索引（影响写入性能）

---

## 5. 错误处理规范

### 5.1 异常层级

**必须**：
- 所有自定义异常继承 `ClawException`
- 异常包含：错误码 `code`、消息 `message`、显式 HTTP 状态码 `http_status`、详细信息 `details`

> ⚠️ **设计要点**：`http_status` **显式声明**，**严禁**用 `code // 1000` 推导（该公式在错误码扩展时会崩溃，如 `100001 // 1000 = 100` 不是有效 HTTP 状态码）。

```python
# application/exceptions/base.py
class ClawException(Exception):
    """业务异常基类"""
    def __init__(
        self,
        code: int,
        message: str,
        http_status: int = 400,
        details: dict | None = None,
    ):
        self.code = code            # 业务错误码（6 位）
        self.message = message
        self.http_status = http_status  # 显式 HTTP 状态码
        self.details = details or {}
        super().__init__(message)

# application/exceptions/not_found.py
class NotFoundException(ClawException):
    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            code=404001,
            message=f"{resource} not found: {resource_id}",
            http_status=404,        # 显式声明，不用 code // 1000
        )

class ValidationException(ClawException):
    def __init__(self, field: str, reason: str):
        super().__init__(
            code=400001,
            message=f"Validation failed: {field} - {reason}",
            http_status=400,
        )
```

### 5.2 异常抛出

**必须**：
- 使用自定义异常
- 异常包含足够上下文
- **严禁**抛出通用 `Exception`

```python
# ✅ 合规
def get_user_by_id(user_id: str) -> User:
    user = find_user(user_id)
    if not user:
        raise NotFoundException("User", user_id)
    return user

# ❌ 违规：抛出通用 Exception
raise Exception("User not found")  # 不清晰
```

### 5.3 异常捕获

**必须**：
- 捕获具体异常类型，**严禁**裸 `except Exception`
- **严禁**吞掉异常（至少记录日志）

```python
# ✅ 合规
try:
    user = get_user_by_id(user_id)
except NotFoundException:
    logger.warning("User not found: %s", user_id)
    raise
except DatabaseError as e:
    logger.error("Database error: %s", e)
    raise ClawException(500001, "Internal error", http_status=500) from e

# ❌ 违规：吞掉异常
try:
    user = get_user_by_id(user_id)
except Exception:
    return None  # 严禁！吞掉异常
```

### 5.4 全局异常处理器

**必须**：使用全局异常处理器，统一错误响应格式。

```python
# api/middleware/error_handler.py
from fastapi import Request
from fastapi.responses import JSONResponse
from application.exceptions.base import ClawException

async def claw_exception_handler(request: Request, exc: ClawException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,   # 显式 HTTP 状态码
        content={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
            "trace_id": getattr(request.state, "trace_id", None),
        },
    )
```

### 5.5 错误码体系

| 区间 | 含义 | 示例 |
|------|------|------|
| 400xxx | 客户端参数错误 | 400001 验证失败 |
| 401xxx | 认证失败 | 401001 未登录 |
| 403xxx | 权限不足 | 403001 禁止访问 |
| 404xxx | 资源不存在 | 404001 用户不存在 |
| 409xxx | 冲突 | 409001 用户已存在 |
| 429xxx | 限流 | 429001 请求过频 |
| 500xxx | 服务器错误 | 500001 内部错误 |
| 503xxx | 服务不可用 | 503001 服务暂时不可用 |

### 5.6 统一响应格式

```json
// 成功
{ "code": 0, "message": "success", "data": { ... } }

// 失败
{ "code": 404001, "message": "User not found: xxx", "details": {}, "trace_id": "xxx" }
```

---

## 6. 输入验证规范

### 6.1 使用 Pydantic v2

**必须**：
- 所有输入使用 Pydantic v2 模型
- **严禁**直接使用 `request.json()` 手动解析
- 添加字段验证规则（`min_length`、`max_length`、`ge`、`le` 等）

> ✅ **当前状态**：项目已有 18 个请求 DTO 模型（`RegisterRequest`/`ChatRequest`/`CreateItineraryRequest` 等），所有 `request.json()` 调用已全部替换为 Pydantic v2 模型验证。

```python
# ✅ 合规（Pydantic v2）
from pydantic import BaseModel, Field, field_validator, ConfigDict
from datetime import date

class CreateItineraryRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "北京三日游",
                "start_date": "2026-10-01",
                "end_date": "2026-10-03",
                "destinations": ["北京"]
            }
        }
    )
    title: str = Field(..., min_length=1, max_length=100, description="行程标题")
    description: str | None = Field(None, max_length=500, description="行程描述")
    start_date: date = Field(..., description="开始日期")
    end_date: date = Field(..., description="结束日期")
    destinations: list[str] = Field(..., min_length=1, max_length=10, description="目的地列表")
    
    @field_validator("end_date")
    @classmethod
    def end_date_must_be_after_start_date(cls, v: date, info) -> date:
        start = info.data.get("start_date")
        if start and v < start:
            raise ValueError("结束日期必须晚于开始日期")
        return v

# 使用
@router.post("/itineraries", status_code=201)
async def create_itinerary(body: CreateItineraryRequest):
    # body 已通过 Pydantic 验证
    ...

# ❌ 违规：直接使用 request.json()
@router.post("/itineraries")
async def create_itinerary(request: Request):
    body = await request.json()  # 严禁！未验证
    ...
```

### 6.2 验证规则

**必须**：
- 字符串：`min_length`、`max_length`
- 数字：`ge`、`le`、`gt`、`lt`
- 列表：`min_length`、`max_length`（v2 写法，**非** `min_items`）
- 必填字段：`...`（Ellipsis）

⚠️ **应该**：
- 使用 `pattern` 验证格式（v2 写法，**非** `regex`）
- 使用 `@field_validator` 验证复杂逻辑

```python
# ✅ 合规（v2）
class RegisterRequest(BaseModel):
    username: str = Field(
        ...,
        min_length=3,
        max_length=32,
        pattern=r"^[a-zA-Z0-9_]+$",   # v2 用 pattern，非 regex
        description="用户名"
    )
    password: str = Field(..., min_length=8, max_length=128)
    
    @field_validator("password")
    @classmethod
    def password_must_contain_uppercase(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("密码必须包含至少一个大写字母")
        return v
```

---

## 7. 安全规范

### 7.1 密码存储

**必须**：
- 新密码使用 bcrypt 哈希（`rounds=12`）
- 每个密码使用独立盐（bcrypt 自动处理）
- **严禁**明文存储
- **严禁**使用 MD5/SHA1

> ✅ **当前状态**：项目已在 `infrastructure/security/password.py` 实现 bcrypt 哈希（rounds=12）+ PBKDF2 向后兼容验证。旧密码验证成功后自动迁移为 bcrypt。

```python
# ✅ 合规：bcrypt（新密码）+ PBKDF2 兼容（旧密码）
import bcrypt

_BCRYPT_ROUNDS = 12

def hash_password(password: str) -> str:
    """新密码用 bcrypt"""
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=_BCRYPT_ROUNDS),
    ).decode("utf-8")

def verify_password(password: str, stored: str) -> bool:
    """验证密码：兼容旧 PBKDF2 格式"""
    if "$" in stored and not stored.startswith("$2"):
        return _verify_pbkdf2(password, stored)  # 旧格式
    return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))

# ❌ 违规
user.password = password                              # 明文！严禁
user.password = hashlib.md5(password.encode()).hexdigest()  # MD5！严禁
```

### 7.2 SQL 注入防护

**必须**：
- 所有 SQL 参数化
- **严禁** f-string 或 `%` 拼接 SQL 中用户可控的值

> ✅ **当前状态**：项目已全面参数化。`api/v1/memory.py` 中有少量 f-string 用于拼接表名，但表名来自硬编码白名单（`{"long_term": "long_term_memories", "short_term": "short_term_memories"}`），非用户输入，属于安全模式。

### 7.3 XSS 防护

**必须**：
- 输出编码（HTML 转义）
- 设置 `Content-Security-Policy` Header

⚠️ **应该**：
- 输入白名单验证
- 使用 `HttpOnly` Cookie

```python
# ✅ 合规：输出编码
from html import escape

def render_user_input(user_input: str) -> str:
    return escape(user_input)

# ✅ 合规：安全 Header
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
```

### 7.4 速率限制

**必须**：
- 使用 Redis 实现速率限制（支持分布式）
- 返回 `X-RateLimit-*` Header

> ✅ **当前状态**：项目已在 `infrastructure/cache/rate_limit.py` 实现 `RateLimiter` 类，采用 Redis 滑动窗口 + 内存回退策略。当 Redis 不可用时自动降级为内存限流，保证服务可用。

```python
# ✅ 合规：Redis 滑动窗口
import time
import redis

class RateLimiter:
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)
    
    def is_allowed(self, key: str, limit: int, window: int) -> tuple[bool, dict]:
        now = time.time()
        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(key, 0, now - window)
        pipe.zcard(key)
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, window)
        results = pipe.execute()
        count = results[1]
        allowed = count < limit
        return allowed, {
            "limit": limit,
            "remaining": max(0, limit - count - 1),
            "reset": now + window,
        }

# ❌ 违规：进程内字典（多 worker 无效）
rate_limit_store: dict = {}
```

### 7.5 敏感信息保护

**必须**：
- 敏感信息（密码、token、密钥）不出现在日志
- 敏感信息不硬编码在代码
- 使用环境变量或密钥管理

⚠️ **应该**：
- 日志脱敏（手机号、邮箱、token）
- 生产环境使用 HTTPS

```python
# ✅ 合规：日志脱敏
import re

def mask_sensitive_info(text: str) -> str:
    text = re.sub(r"(\d{3})\d{4}(\d{4})", r"\1****\2", text)  # 手机号
    text = re.sub(r"(\w{1,3})\w+(@\w+)", r"\1***\2", text)     # 邮箱
    return text

logger.info("User registered: %s", mask_sensitive_info(user.email))

# ❌ 违规
logger.info("User password: %s", password)  # 严禁！
```

### 7.6 OWASP Top 10 (2021) 防护

| 编号 | 类别 | 防护措施 |
|------|------|---------|
| A01 | 访问控制失效 | 路由级权限校验 |
| A02 | 加密失败 | bcrypt 密码、HTTPS |
| A03 | 注入 | 参数化 SQL、Pydantic 验证 |
| A04 | 不安全设计 | 威胁建模、输入白名单 |
| A05 | 安全配置错误 | 配置分离、禁用调试模式 |
| A06 | 易受攻击的组件 | `safety check` 定期扫描 |
| A07 | 认证失败 | JWT 短期 token、限流 |
| A08 | 数据完整性失败 | CI 签名校验 |
| A09 | 日志监控不足 | 结构化日志、审计 |
| A10 | 服务端请求伪造 | 出站请求白名单 |

---

## 8. 测试规范

### 8.1 测试覆盖率

**必须**：
- 单元测试覆盖率 ≥ 70%
- 关键路径（认证、支付、核心业务）必须有测试
- 所有公共接口必须有测试

⚠️ **应该**：
- 覆盖率达到 80%
- 集成测试覆盖关键流程
- E2E 测试覆盖核心场景

### 8.2 测试组织

**必须**：
- 测试分层：`tests/unit/`、`tests/integration/`、`tests/e2e/`
- 文件命名：`test_<module>.py`
- 函数命名：`test_<function>_<scenario>`

```
tests/
├── unit/                  # 单元测试（不依赖外部）
│   ├── test_domain/
│   └── test_application/
├── integration/           # 集成测试（API + DB）
│   └── test_api/
└── e2e/                   # 端到端
```

### 8.3 测试编写

**必须**：
- 测试独立（不依赖其他测试）
- 测试可重复（每次运行结果相同）
- 单元测试不依赖数据库/网络（用 mock）

⚠️ **应该**：
- 使用 Arrange-Act-Assert 模式
- 一个测试只测一个场景
- 使用描述性测试名称

```python
# ✅ 合规：AAA 模式 + mock
import pytest
from unittest.mock import MagicMock
from domain.service.auth import AuthService

def test_get_user_by_id_not_found():
    # Arrange
    repo = MagicMock()
    repo.find_by_id.return_value = None
    service = AuthService(repo)
    
    # Act / Assert
    with pytest.raises(NotFoundException):
        service.get_user_by_id("user_not_exist")

# ❌ 违规：测试不清晰 + 依赖真实数据库
def test_create():
    r = CreateItineraryRequest("北京三日游", date(2026, 10, 1), date(2026, 10, 3), ["北京"])
    s = ItineraryService()  # 没有注入依赖，会连真实数据库
    i = s.create(r)
    assert i is not None
```

---

## 9. API 设计规范

### 9.1 版本控制

**必须**：
- 所有路由前缀 `/api/v1/`
- 破坏性变更用 `/api/v2/`，旧版保留至少 6 个月
- 文档标注弃用时间

```python
# ✅ 合规
# api/v1/__init__.py
router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["认证"])

# api/server.py
app.include_router(v1_router, prefix="/api/v1")

# ❌ 违规：无版本控制
@app.post("/api/itineraries")
async def create_itinerary(): ...
```

### 9.2 响应格式

**必须**：
- 统一响应格式
- 成功：`{ "code": 0, "message": "success", "data": { ... } }`
- 失败：`{ "code": 404001, "message": "...", "details": {}, "trace_id": "..." }`

```python
# ❌ 违规：不一致格式
{"detail": "User not found"}
{"error": "..."}
{"status": "error", "message": "..."}
```

### 9.3 HTTP 状态码

**必须**：正确使用 HTTP 状态码。

| 状态码 | 含义 | 使用场景 |
|--------|------|---------|
| 200 | 成功 | GET、PUT、PATCH、DELETE 成功 |
| 201 | 创建成功 | POST 创建资源 |
| 400 | 参数错误 | 请求体验证失败 |
| 401 | 未认证 | 未登录 |
| 403 | 无权限 | 已登录但无权限 |
| 404 | 资源不存在 | 资源未找到 |
| 429 | 速率限制 | 请求过频 |
| 500 | 服务器错误 | 内部异常 |

```python
# ✅ 合规
@router.post("/users", status_code=201)
async def create_user(body: CreateUserRequest): ...

@router.get("/users/{user_id}")
async def get_user(user_id: str):
    user = get_user_by_id(user_id)
    if not user:
        raise NotFoundException("User", user_id)  # 404
    return user

# ❌ 违规
@router.post("/users", status_code=200)  # 创建应该用 201
async def create_user(): ...

return {"error": "User not found"}, 200  # 应该是 404
```

### 9.4 路由拆分

**必须**：按资源拆分路由到独立文件，使用 `APIRouter`。

| 文件 | 资源 | 前缀 |
|------|------|------|
| `api/v1/auth.py` | 认证 | `/api/v1/auth` |
| `api/v1/chat.py` | 对话/流式 | `/api/v1/chat` |
| `api/v1/session.py` | 会话管理 + 方案确认 | `/api/v1/sessions` + `/api/v1/session` |
| `api/v1/agent.py` | 智能体 CRUD | `/api/v1/agents` |
| `api/v1/skill.py` | 技能 | `/api/v1/skills` |
| `api/v1/mcp.py` | MCP 服务器/工具 | `/api/v1/mcp` |
| `api/v1/itinerary.py` | 行程 | `/api/v1/itineraries` |
| `api/v1/album.py` | 相册 + 文件服务 | `/api/v1/itineraries` + `/api/v1/album` |
| `api/v1/memory.py` | 记忆 | `/api/v1/memory` |
| `api/v1/news.py` | 新闻/热搜 | `/api/v1/news` |
| `api/v1/geocode.py` | 地理编码 | `/api/v1/geocode` |
| `api/v1/share.py` | 分享（公开） | `/api/v1/share` |
| `api/v1/debug.py` | 调试 | `/api/v1/debug` |
| `api/v1/health.py` | 健康检查/指标 | `/api/v1/health` |
| `api/v1/feedback.py` | 反馈 | `/api/v1/feedback` |

---

## 10. 文档与注释规范

### 10.1 Docstring

**必须**：
- 所有公共接口必须有 docstring
- 使用 Google 风格
- 包含 Args、Returns、Raises

```python
# ✅ 合规
def get_user_by_id(user_id: str) -> User:
    """根据用户ID获取用户
    
    Args:
        user_id: 用户ID
        
    Returns:
        User: 用户对象
        
    Raises:
        NotFoundException: 用户不存在
    """
    ...

# ❌ 违规：无 docstring
def get_user_by_id(user_id: str) -> User:
    ...
```

### 10.2 注释

**必须**：
- 复杂逻辑必须添加注释
- 魔法数字定义为常量并注释
- 临时 hack 必须添加 `TODO` + 日期

```python
# ✅ 合规
MAX_RETRY_COUNT = 3  # 最大重试次数
for attempt in range(MAX_RETRY_COUNT):
    try:
        return api_call()
    except Exception:
        if attempt == MAX_RETRY_COUNT - 1:
            raise
        time.sleep(2 ** attempt)  # 指数退避，避免雪崩

# TODO: 优化性能（2026-07-05）—— 当前 O(n²)，目标 O(n log n)
```

### 10.3 API 文档

**必须**：
- 使用 FastAPI 自带 OpenAPI 文档
- 所有接口添加 `summary`、`description`
- 所有模型添加 `example`

```python
@router.post(
    "/itineraries",
    response_model=CreateItineraryResponse,
    status_code=201,
    summary="创建行程",
    description="创建一个新的旅游行程",
)
async def create_itinerary(body: CreateItineraryRequest):
    """创建行程"""
    ...
```

---

## 11. 性能规范

### 11.1 数据库查询（SQLite 适配）

**必须**：
- 避免无分页的大数据量查询
- 高频查询字段建索引
- 避免 N+1 查询

⚠️ **应该**：
- 使用分页
- 批量操作代替循环单条

> 💡 **SQLite 说明**：SQLite 是单文件嵌入式数据库，连接池意义有限，重点优化查询本身。

```python
# ✅ 合规：分页
def get_itineraries(page: int = 1, page_size: int = 20):
    offset = (page - 1) * page_size
    return conn.execute(
        "SELECT * FROM itineraries ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (page_size, offset)
    ).fetchall()

# ❌ 违规：无分页
def get_itineraries():
    return conn.execute("SELECT * FROM itineraries").fetchall()  # 可能返回大量数据
```

### 11.2 缓存

⚠️ **应该**：
- 热点数据用 Redis 缓存
- 设置合理过期时间
- 防止缓存穿透、击穿、雪崩

```python
# ✅ 合规
redis_client = redis.from_url(settings.REDIS_URL)

def get_user_by_id(user_id: str) -> User | None:
    cache_key = f"user:{user_id}"
    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)
    user = find_user_in_db(user_id)
    if user:
        redis_client.setex(cache_key, 3600, json.dumps(user.to_dict()))
    return user
```

### 11.3 异步处理

**必须**：
- I/O 操作使用 `async/await`
- 耗时操作不阻塞主线程

⚠️ **应该**：
- 耗时后台任务用异步任务队列（如需引入需评估必要性，勿盲目加 Celery）

```python
# ✅ 合规：异步 I/O
async def fetch_weather(city: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{WEATHER_API}/{city}")
        return response.json()

# ❌ 违规：同步阻塞
def fetch_weather(city: str) -> dict:
    response = requests.get(f"{WEATHER_API}/{city}")  # 阻塞事件循环
    return response.json()
```

---

## 12. 代码审查清单

### 12.1 必查项

**安全**：
- [ ] 是否包含敏感信息（密码、token、私钥）
- [ ] 是否有 SQL 注入风险（f-string 拼接）
- [ ] 密码是否使用 bcrypt 哈希
- [ ] 速率限制是否使用 Redis

**错误处理**：
- [ ] 是否使用自定义异常（非裸 `Exception`）
- [ ] 错误响应格式是否统一
- [ ] 是否吞掉异常

**数据库**：
- [ ] SQL 是否参数化
- [ ] 是否有 N+1 查询
- [ ] 大数据量查询是否分页

**输入验证**：
- [ ] 是否使用 Pydantic v2 模型
- [ ] 是否有长度/范围限制
- [ ] 是否有 `request.json()` 残留

**类型**：
- [ ] 是否使用 Python 3.11+ 内置泛型（`list[str]` 而非 `List[str]`）
- [ ] 是否使用 `X | None` 而非 `Optional[X]`

### 12.2 应查项

**代码质量**：
- [ ] 命名是否规范
- [ ] 是否有重复代码
- [ ] 是否有硬编码/魔法数字
- [ ] 单文件是否超过 400 行
- [ ] 单函数是否超过 50 行

**测试**：
- [ ] 是否有单元测试
- [ ] 覆盖率是否 ≥ 70%
- [ ] 测试是否独立可重复

**文档**：
- [ ] 公开接口是否有 docstring
- [ ] 复杂逻辑是否有注释

---

## 13. 禁止事项

### 13.1 严禁（违反即拒绝合并）

**代码组织**：
- ❌ 在 `api/server.py` 直接写 `@app.*` 路由
- ❌ 单文件 > 400 行（无正当理由）
- ❌ 单函数 > 50 行

**数据库**：
- ❌ f-string 或 `%` 拼接 SQL
- ❌ 不使用迁移工具修改表结构
- ❌ 要求 InnoDB/utf8mb4（SQLite 项目）

**错误处理**：
- ❌ 抛出通用 `Exception`
- ❌ 裸 `except Exception` 吞掉异常
- ❌ 用 `code // 1000` 推导 HTTP 状态码

**输入验证**：
- ❌ 直接使用 `request.json()` 手动解析
- ❌ 使用 Pydantic v1 API（`@validator`、`class Config`、`min_items`、`regex`）

**安全**：
- ❌ 明文存储密码
- ❌ 使用 MD5/SHA1 哈希密码
- ❌ 硬编码敏感信息
- ❌ 敏感信息出现在日志

**工具栈**：
- ❌ 引入 Black/isort/flake8（项目用 Ruff）
- ❌ 使用 `from typing import List/Dict/Tuple`（用内置泛型）

### 13.2 不应该

- ❌ 不应该有重复代码（DRY）
- ❌ 不应该有硬编码
- ❌ 不应该无分页查询大量数据
- ❌ 不应该无 docstring
- ❌ 不应该盲目引入 Celery/Kafka 等重型中间件（需评估必要性）

---

## 14. 工具与配置

> ⚠️ **项目已用 Ruff 替代 Black/isort/flake8**，禁止再引入这三者。

### 14.1 已有配置（pyproject.toml）

```toml
[tool.ruff]
line-length = 120
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B"]
# 忽略规则说明：
# - E501: 行长度（已用 line-length=120 控制）
# - E401/E402: import 位置（项目部分模块有特殊导入顺序）
# - F401: 未使用导入（清理中，逐步消除）
# - F541/F841: f-string/变量警告
# - B007/B008/B904/B905: 安全/风格警告
# - I001: import 排序（与 from __future__ 放置冲突）
# - UP035/UP037/UP017/UP042/UP045: Python 3.11+ 类型注解风格（项目混用）
ignore = [
    "E501", "E401", "E402", "F401", "F541", "F841",
    "B007", "B008", "B904", "B905", "I001",
    "UP035", "UP037", "UP017", "UP042", "UP045",
]

[tool.mypy]
python_version = "3.11"
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

> ⚠️ **配置更新原则**：Ruff ignore 列表随项目清理进度逐步缩减。每次修复一类警告后，从 ignore 中移除对应规则，最终目标为仅保留 `["E501", "B008"]`。

### 14.2 工具命令

| 工具 | 命令 | 用途 | 必要性 |
|------|------|------|--------|
| Ruff | `ruff check .` | 代码检查（替代 flake8） | **必须** |
| Ruff | `ruff format .` | 格式化（替代 Black） | **必须** |
| pytest | `pytest` | 运行测试 | **必须** |
| pytest | `pytest --cov=. --cov-report=term-missing` | 覆盖率 | **应该** |
| mypy | `mypy api application domain infrastructure` | 类型检查 | 可选（项目存在历史类型债务） |
| bandit | `bandit -r api application domain infrastructure` | 安全扫描 | 可选（CI 中为非阻塞） |

> ❌ **禁止**的命令：`black .`、`isort .`、`flake8 .`

### 14.3 覆盖率配置

```ini
# .coveragerc
[run]
source = api, application, domain, infrastructure
omit = */tests/*

[report]
exclude_lines =
    pragma: no cover
    if __name__ == .__main__.:
```

---

## 15. 开发流程

### 15.1 每次开发

1. 拉取最新代码
2. 创建功能分支（`git checkout -b feature/xxx`）
3. 编写代码（遵循本规范）
4. 编写测试（覆盖率 ≥ 70%）
5. 运行检查：
   ```bash
   ruff check .
   pytest
   ```
6. 提交代码（清晰的 commit message）
7. 创建 Pull Request
8. 代码审查（对照第 12 章清单）
9. 合并到主分支

> ⚠️ **可选检查**：如需更严格的质量控制，可额外运行 `mypy api application domain infrastructure`（类型检查）和 `pytest --cov=. --cov-report=term-missing`（覆盖率报告）。项目当前存在历史类型债务，mypy 暂不作为强制要求。

### 15.2 定期维护

- 每周：依赖更新、覆盖率检查、技术债务评估
- 每月：安全扫描（`bandit` + `safety`）、性能检查
- 每季度：架构评估、规范更新

---

## 16. 附录：快速参考

### A. 技术栈速查

| 维度 | 选型 | 备注 |
|------|------|------|
| Python | >= 3.11 | 内置泛型 `list[str]`、`X \| None` |
| 验证 | Pydantic v2 | `@field_validator`、`ConfigDict`、`pattern`、`min_length` |
| 数据库 | SQLite | 参数化查询，无 InnoDB |
| 风格 | Ruff | 替代 Black/isort/flake8 |
| 类型 | mypy | `python_version = "3.11"` |

### B. 命名速查

| 类型 | 规范 | 示例 |
|------|------|------|
| 类名 | PascalCase | `UserAuthService` |
| 函数/变量 | snake_case | `get_user_by_id` |
| 常量 | UPPER_SNAKE_CASE | `MAX_RETRY_COUNT` |
| 私有成员 | 前缀 `_` | `_validate_input` |

### C. 错误码速查

| HTTP 状态码 | 错误码 | 含义 |
|-------------|--------|------|
| 400 | 400xxx | 参数错误 |
| 401 | 401xxx | 认证失败 |
| 403 | 403xxx | 权限不足 |
| 404 | 404xxx | 资源不存在 |
| 409 | 409xxx | 冲突 |
| 429 | 429xxx | 速率限制 |
| 500 | 500xxx | 服务器错误 |
| 503 | 503xxx | 服务不可用 |

### D. Pydantic v1 → v2 迁移速查

| v1（禁用） | v2（必须） |
|------------|-----------|
| `@validator("x")` | `@field_validator("x")` + `@classmethod` |
| `class Config: schema_extra` | `model_config = ConfigDict(json_schema_extra=...)` |
| `min_items` / `max_items` | `min_length` / `max_length` |
| `regex="..."` | `pattern="..."` |
| `Optional[X]` | `X \| None` |
| `.dict()` | `.model_dump()` |
| `.json()` | `.model_dump_json()` |

### E. 检查命令速查

```bash
# 一键检查（每次提交前运行）
ruff check .
pytest

# 完整检查（定期维护）
ruff check .
pytest --cov=. --cov-report=term-missing
bandit -r api application domain infrastructure
```

---

**文档版本**：v2.1（同步项目重构后实际状态）
**维护者**：Claw7 开发团队
**更新频率**：随重大重构同步更新
