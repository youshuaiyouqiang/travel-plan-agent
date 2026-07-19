# 云合项目彻底根治重构执行手册

> **文档性质**：这是一份**可执行的重构手册**，不是评估报告。每个步骤都有具体操作、代码示例、验证命令和回滚方案。
>
> **目标**：彻底根治项目三大顽疾——依赖方向违规（54 处）、测试覆盖率不足（~10%）、超大文件（9 个超标），使项目达到企业级标准并让 `AGENTS.md` 规范真正落地。
>
> **适用项目**：云合 多智能体系统
>
> **配套规范**：`AGENTS.md` v2.1（长期开发规范）
>
> **关联文档**：`docs/api/ARCHITECTURE_IMPROVEMENT.md`（问题评估）、`docs/api/API.md`（接口参考）
>
> **版本**：v1.0
> **编写日期**：2026-07-13

---

## 📋 目录

1. [重构原则与纪律](#1-重构原则与纪律)
2. [前置准备：建立安全网](#2-前置准备建立安全网)
3. [第一波：零风险清理（Day 1）](#3-第一波零风险清理day-1)
4. [第二波：AGENTS.md 约束力修复（Day 2）](#4-第二波agentsmd-约束力修复day-2)
5. [第三波：领域层依赖解耦（Day 3-7）](#5-第三波领域层依赖解耦day-3-7)
6. [第四波：测试覆盖率提升（Day 8-12）](#6-第四波测试覆盖率提升day-8-12)
7. [第五波：超大文件拆分（Day 13-15）](#7-第五波超大文件拆分day-13-15)
8. [第六波：工程化补全（Day 16-18）](#8-第六波工程化补全day-16-18)
9. [验收与回归](#9-验收与回归)
10. [回滚预案](#10-回滚预案)
11. [AGENTS.md 修订清单](#11-agentsmd-修订清单)

---

## 1. 重构原则与纪律

### 1.1 三条铁律

1. **不停止功能开发**：重构期间业务需求照常推进，技术债偿还分配约 30% 容量。
2. **每个步骤可验证**：每个操作都有可运行的验证命令，不靠"感觉"判断。
3. **每个步骤可回滚**：每波改动都是独立 commit，出问题可 `git revert` 单波回滚。

### 1.2 分支策略

```bash
# 整个重构在一个长期分支上进行，每个"波"是一个子分支
git checkout -b refactor/root-cleanup          # 第一波
git checkout -b refactor/agents-md-fix         # 第二波
git checkout -b refactor/domain-decouple       # 第三波（最大，可再拆子分支）
git checkout -b refactor/test-coverage         # 第四波
git checkout -b refactor/file-split             # 第五波
git checkout -b refactor/engineering            # 第六波

# 每波完成后合回 refactor/main，最后一次性合回 main
```

### 1.3 环境约定

> ⚠️ **本项目运行在 Windows 上**（`win32 10.0.26200 x64`）。
>
> - 文档中的 shell 命令以 Windows `cmd` 语法为主（`dir`、`del`、`echo.`、`rmdir /s /q` 等）
> - 路径分隔符使用反斜杠 `\`（如 `domain\travel\geo\`）
> - `git mv` 命令在 Windows 上可直接使用（git 会自动处理路径分隔符）
> - 检测脚本统一使用 `py -3 -X utf8 -c "..."` 形式，确保跨平台可用
> - **若交接 AI 在 Linux/Mac 上执行**，需将路径分隔符 `\` 改为 `/`，`dir` 改为 `ls`，`del` 改为 `rm`，`echo.` 改为 `touch`

### 1.4 提交规范

每个步骤一个 commit，格式：

```
refactor(波次-步骤): 简述

- 具体改动1
- 具体改动2

验证: ruff check . && pytest
```

---

## 2. 前置准备：建立安全网

### 2.1 确认当前基线

在开始任何重构前，先记录"重构前"的基线数据，作为对比基准。

```bash
# 记录基线（在项目根目录运行）
echo === 重构前基线 === > refactor_baseline.txt
echo 日期: %date% %time% >> refactor_baseline.txt

# 1. 依赖违规数
py -3 -X utf8 -c "
import os, re
v = 0
for r, d, files in os.walk('domain'):
    if '__pycache__' in r: continue
    for f in files:
        if not f.endswith('.py'): continue
        for i, line in enumerate(open(os.path.join(r, f), encoding='utf-8').read().splitlines(), 1):
            s = line.strip()
            if s.startswith('#'): continue
            if re.search(r'from infrastructure\.|import infrastructure\.', s):
                v += 1
print(f'依赖违规: {v} 处')
" >> refactor_baseline.txt

# 2. 超标文件数
py -3 -X utf8 -c "
import os
v = []
for top in ['api', 'application', 'domain', 'infrastructure', 'config', 'tests']:
    for r, d, files in os.walk(top):
        if '__pycache__' in r: continue
        for f in files:
            if f.endswith('.py'):
                n = sum(1 for _ in open(os.path.join(r, f), encoding='utf-8'))
                if n > 400: v.append(n)
print(f'超标文件: {len(v)} 个')
" >> refactor_baseline.txt

# 3. 测试通过情况
pytest --tb=no -q >> refactor_baseline.txt 2>&1

# 查看基线
type refactor_baseline.txt
```

### 2.2 确保 CI 基线绿色

```bash
# 确保当前 main 分支 CI 全绿
ruff check .
pytest
```

如果 pytest 有失败，**先修复失败再开始重构**。不要在红色基线上叠加重构。

---

## 3. 第一波：零风险清理（Day 1）

> **目标**：清理噪音文件，让项目目录干净，让 AI 和开发者不再被误导。
> **风险**：极低（只删空文件、修编码、补占位）
> **预计工时**：0.5 天

### 步骤 1.1：删除空文件和空目录

```bash
# 删除空的 requirements.txt（项目用 pyproject.toml 管理依赖）
git rm requirements.txt

# 删除空的 api/routes/ 目录（重构遗留）
git rm api/routes/__init__.py
# 如果目录为空，git 会自动移除

# 删除根目录的 __pycache__
rmdir /s /q __pycache__ 2>nul
# 确认 .gitignore 已覆盖 __pycache__/
```

**验证**：
```bash
# 确认文件已删除
git status
# 确认项目仍可启动
py -3 -m uvicorn api.server:app --host 127.0.0.1 --port 8000
# 能正常启动 → 验证通过
```

### 步骤 1.2：修复 intl_coords.py 编码乱码

当前 `api/intl_coords.py` 存在 GBK/UTF-8 编码混乱，中文城市名显示为乱码。

```bash
# 1. 先检测当前编码
py -3 -X utf8 -c "
with open('api/intl_coords.py', 'rb') as f:
    raw = f.read()
# 尝试 UTF-8 解码
try:
    raw.decode('utf-8')
    print('UTF-8 OK')
except:
    print('NOT UTF-8, trying GBK')
    try:
        raw.decode('gbk')
        print('GBK OK - 文件是 GBK 编码')
    except:
        print('UNKNOWN encoding')
"
```

**修复操作**：

```bash
# 将文件从 GBK 转为 UTF-8
py -3 -X utf8 -c "
with open('api/intl_coords.py', 'rb') as f:
    raw = f.read()
text = raw.decode('gbk')  # 先用 GBK 正确解码
with open('api/intl_coords.py', 'w', encoding='utf-8') as f:
    f.write(text)
print('Converted to UTF-8')
"

# 验证中文是否正确显示
py -3 -X utf8 -c "
from api.intl_coords import INTL_COORDS
# 抽查几个城市名是否正确
for name in list(INTL_COORDS.keys())[:5]:
    print(name)
"
# 应该看到正确的中文城市名（东京、大阪等），而非乱码
```

### 步骤 1.3：迁移 intl_coords.py 到正确位置

该文件是旅行领域的坐标数据，不应放在 `api/` 层。

```bash
# 创建目标目录
mkdir domain\travel\geo 2>nul
# 创建 __init__.py
echo. > domain\travel\geo\__init__.py

# 移动文件
git mv api/intl_coords.py domain/travel/geo/intl_coords.py
```

**更新引用**（搜索所有引用处）：

```bash
# 查找所有引用
findstr /s /r /n "intl_coords" *.py
```

逐个更新引用：
```python
# 整改前（api/v1/geocode.py 等）
from api.intl_coords import lookup_intl_coords, INTL_COORDS

# 整改后
from domain.travel.geo.intl_coords import lookup_intl_coords, INTL_COORDS
```

**验证**：
```bash
# 确认无残留旧引用
findstr /s /r /n "from api.intl_coords" *.py
# 应该无输出

# 确认新引用可用
py -3 -X utf8 -c "from domain.travel.geo.intl_coords import lookup_intl_coords; print(lookup_intl_coords('东京塔'))"
```

### 步骤 1.4：补 .gitignore 和占位文件

```bash
# 创建 data/.gitkeep（让 .gitignore 的 !data/.gitkeep 规则生效）
echo. > data\.gitkeep

# 在 .gitignore 末尾追加 .dbg/
echo. >> .gitignore
echo # Debug artifacts>> .gitignore
echo .dbg/>> .gitignore
```

**验证**：
```bash
# 确认 data/.gitkeep 存在
dir data\.gitkeep
# 确认 .gitignore 包含 .dbg/
findstr ".dbg" .gitignore
```

### 步骤 1.5：提交第一波

```bash
git add -A
git commit -m "refactor(w1): 清理冗余文件、修复编码乱码、补占位

- 删除空 requirements.txt
- 删除空 api/routes/ 目录
- 修复 api/intl_coords.py GBK→UTF-8 编码
- 迁移 intl_coords.py 到 domain/travel/geo/
- 补 data/.gitkeep
- .gitignore 追加 .dbg/

验证: ruff check . && pytest"
```

---

## 4. 第二波：AGENTS.md 约束力修复（Day 2）

> **目标**：修复 AGENTS.md 中的失真描述，新增"已知技术债清单"和"AI 自验脚本"，让规范重新可信、可执行。
> **风险**：低（只改文档，不改代码）
> **预计工时**：0.5 天

### 步骤 2.1：修复 AGENTS.md 中的失真描述

对照实际代码，修正以下条目：

| 位置 | 原文 | 实际 | 修正为 |
|------|------|------|--------|
| §2.2 目录树 | `domain/travel/core.py # Agent 主类（~290 行）` | 441 行 | `Agent 主类（~440 行，待拆分）` |
| §2.2 目录树 | `application/dto/request/ # 18 个请求 DTO` | 7 个文件 | `7 个请求 DTO` |
| §2.2 目录树 | `application/exceptions/ # 自定义异常（8 个异常类）` | 9 个（含基类） | `9 个异常类（含基类）` |
| §2.2 目录树 | 未列出 `api/deps.py` | 不存在 | 从目录树移除 `deps.py` 行 |
| §2.2 目录树 | 未列出 `application/builtin_agents/` | 存在 | 补充到目录树 |
| §2.2 目录树 | 未列出 `application/trending/` | 存在 | 补充到目录树 |
| §2.2 目录树 | 未列出 `domain/safety/` | 存在 | 补充到目录树 |
| §2.2 目录树 | 未列出 `domain/shared/audit/`、`metrics/`、`runtime/` | 存在 | 补充到目录树 |
| §9.1 | `所有路由前缀 /api/v1/` | 同时挂载 `/api` 和 `/api/v1` | 注明"同时挂载 /api 和 /api/v1，向后兼容" |
| 配套文档 | `DEVELOPMENT_STANDARDS.md` | 已删除 | 更新引用为 `docs/api/ARCHITECTURE_IMPROVEMENT.md` |

### 步骤 2.2：新增「已知技术债清单」章节

在 AGENTS.md §2.3 依赖方向之后，新增 §2.4：

```markdown
### 2.4 已知技术债清单

> 以下违规为**存量技术债**，AI 开发时遵循"不扩大"原则：
> - 不得在存量违规文件中新增同类违规
> - 新增代码**必须**合规
> - 存量违规按 `docs/api/REFACTOR_EXECUTION_PLAN.md` 逐步消除

| 编号 | 描述 | 涉及文件 | 状态 | AI 行为 |
|------|------|----------|------|---------|
| TD-01 | 领域层直接依赖基础设施层 | 25 个 domain 文件（54 处） | 待重构 | 新增 domain 代码必须通过 `domain/shared/ports/` 接口 |
| TD-02 | 单文件超 400 行 | 9 个文件（最大 1293 行） | 待拆分 | 不得在超标文件中追加新逻辑 |
| TD-03 | 测试覆盖率 ~10% | domain 层 41 模块仅 4 个有测试 | 待补齐 | 新增公共接口必须同步补测试 |
| TD-04 | app.py 在根目录 | 根目录 | 待迁移 | 新增依赖注入逻辑放在 application/ |
| TD-05 | CI 跳过 test_prompting | .github/workflows/ci.yml | 待修复 | 不得新增 --ignore 跳过 |
```

### 步骤 2.3：新增「AI 自验脚本」章节

在 AGENTS.md §16 附录中，新增 §16.F：

```markdown
### F. AI 自验脚本

> AI 每次提交前**必须**运行以下脚本，确认无新增违规。

#### F.1 检查依赖方向

```bash
py -3 -X utf8 -c "
import os, re
violations = []
for r, d, files in os.walk('domain'):
    if '__pycache__' in r: continue
    for f in files:
        if not f.endswith('.py'): continue
        fp = os.path.join(r, f)
        for i, line in enumerate(open(fp, encoding='utf-8').read().splitlines(), 1):
            s = line.strip()
            if s.startswith('#'): continue
            if re.search(r'from infrastructure\.|import infrastructure\.', s):
                violations.append(f'{fp}:{i} {s}')
if violations:
    print(f'❌ 依赖违规 {len(violations)} 处:')
    for v in violations: print(f'  {v}')
else:
    print('✅ 依赖方向合规')
"
```

#### F.2 检查文件行数

```bash
py -3 -X utf8 -c "
import os
violations = []
for top in ['api', 'application', 'domain', 'infrastructure', 'config']:
    for r, d, files in os.walk(top):
        if '__pycache__' in r: continue
        for f in files:
            if f.endswith('.py'):
                fp = os.path.join(r, f)
                n = sum(1 for _ in open(fp, encoding='utf-8'))
                if n > 400: violations.append(f'{n:5d}  {fp}')
if violations:
    print(f'❌ 超标文件 {len(violations)} 个:')
    for v in violations: print(f'  {v}')
else:
    print('✅ 文件行数合规')
"
```
```

### 步骤 2.4：提交第二波

```bash
git add AGENTS.md
git commit -m "refactor(w2): 修复 AGENTS.md 失真描述，新增技术债清单和自验脚本

- 修正目录树中 DTO 数量、core.py 行数等失真描述
- 补充目录树遗漏的 builtin_agents/trending/safety/shared 子目录
- 新增 §2.4 已知技术债清单（5 项）
- 新增 §16.F AI 自验脚本（依赖检查 + 行数检查）
- 更新配套文档引用（DEVELOPMENT_SPECIFICATION.md 已删除）

验证: 文档审查"
```

---

## 5. 第三波：领域层依赖解耦（Day 3-7）

> **目标**：消灭 54 处 `domain → infrastructure` 依赖违规，建立抽象接口层。
> **风险**：中高（改动 25 个文件，需逐步进行）
> **预计工时**：3-5 天

### 5.1 解耦策略：分批进行，不一次性全改

54 处违规分布在 25 个文件，一次性全改风险太高。按依赖类型分批：

| 批次 | 接口 | 替代的 infrastructure 依赖 | 涉及文件数 | 预计违规数 |
|------|------|---------------------------|-----------|-----------|
| 3A | `IConnection` / `IDatabase` | `database.get_connection` | 10 | 18 |
| 3B | `ILLMGateway` | `llm.openai.OpenAILLM` | 10 | 12 |
| 3C | `IPasswordHasher` | `security.password.*` | 2 | 3 |
| 3D | `IToolRegistry` / `IToolExecutor` | `tools.registry/executor` | 5 | 8 |
| 3E | `IMCPRuntime` / `IMCPCatalog` | `mcp.runtime/catalog` | 3 | 5 |
| 3F | `ISkillProvider` | `skills.provider` | 2 | 3 |
| 3G | `ISessionRepository` | `persistence.session_repository` | 3 | 5 |

每批完成后立即运行验证 + pytest，确认无回归再进入下一批。

### 5.2 步骤 3A：建立数据库连接抽象

这是最大的一批（18 处违规），也是最基础的。

#### 第一步：创建抽象接口

```python
# domain/shared/ports/database.py
"""数据库连接抽象接口。

领域层通过此接口获取数据库连接，不直接依赖 infrastructure.persistence.database。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from sqlite3 import Connection


class IDatabase(ABC):
    """数据库连接提供者抽象接口。"""

    @abstractmethod
    def get_connection(self) -> Connection:
        """获取当前线程的数据库连接。"""
        ...

    @abstractmethod
    def reset_connection(self) -> None:
        """重置连接（用于测试隔离）。"""
        ...

    @abstractmethod
    def init_db(self) -> None:
        """初始化数据库（建表 + 迁移）。"""
        ...
```

同时创建 JSON 工具抽象（因为 `_json_dumps` / `_json_loads` 也被领域层引用）：

```python
# domain/shared/ports/json_utils.py
"""JSON 序列化工具抽象。

将 infrastructure.persistence.database 的私有函数 _json_dumps/_json_loads
提升为公共接口，供领域层使用。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IJsonSerializer(ABC):
    """JSON 序列化抽象接口。"""

    @abstractmethod
    def dumps(self, obj: Any) -> str:
        """序列化为 JSON 字符串（ensure_ascii=False）。"""
        ...

    @abstractmethod
    def loads(self, text: str, default: Any = None) -> Any:
        """反序列化 JSON 字符串，失败时返回 default。"""
        ...
```

#### 第二步：基础设施层实现接口

```python
# infrastructure/persistence/database.py（追加，不改动原有函数）

# ... 原有代码保持不变 ...

from domain.shared.ports.database import IDatabase
from domain.shared.ports.json_utils import IJsonSerializer


class SQLiteDatabase(IDatabase):
    """IDatabase 的 SQLite 实现（包装现有模块级函数）。"""

    def get_connection(self) -> sqlite3.Connection:
        return get_connection()

    def reset_connection(self) -> None:
        reset_connection()

    def init_db(self) -> None:
        init_db()


class SqliteJsonSerializer(IJsonSerializer):
    """IJsonSerializer 实现（包装现有 _json_dumps/_json_loads）。"""

    def dumps(self, obj) -> str:
        return _json_dumps(obj)

    def loads(self, text: str, default=None):
        return _json_loads(text, default=default)


# 模块级单例（供依赖注入容器使用）
db_instance = SQLiteDatabase()
json_serializer = SqliteJsonSerializer()
```

#### 第三步：更新依赖注入容器

```python
# app.py（或 application/container.py）中注入

from infrastructure.persistence.database import SQLiteDatabase, SqliteJsonSerializer

def build_orchestrator() -> AppContainer:
    # ... 原有逻辑 ...

    # 数据库抽象（注入领域层）
    db: IDatabase = SQLiteDatabase()
    json_ser: IJsonSerializer = SqliteJsonSerializer()

    # 传递给需要数据库的领域服务
    # （具体注入方式取决于各领域类的 __init__ 签名）
```

#### 第四步：逐文件改造领域层

以 `domain/memory/manager.py` 为例（当前有 2 处违规）：

```python
# ❌ 整改前
from infrastructure.persistence.database import get_connection  # 第 9 行

class DualLayerMemoryManager:
    def get_long_term_memories(self, user_id: str) -> list[LongTermMemory]:
        conn = get_connection()  # 直接调用
        # ...
        from infrastructure.persistence.database import _json_loads  # 第 51 行，方法内延迟导入
        source_ids=_json_loads(row["source_ids"], default=[])


# ✅ 整改后
from domain.shared.ports.database import IDatabase
from domain.shared.ports.json_utils import IJsonSerializer

class DualLayerMemoryManager:
    def __init__(self, db: IDatabase, json_ser: IJsonSerializer):
        self._db = db
        self._json = json_ser

    def get_long_term_memories(self, user_id: str) -> list[LongTermMemory]:
        conn = self._db.get_connection()  # 通过接口
        # ...
        source_ids=self._json.loads(row["source_ids"], default=[])  # 通过接口
```

**逐文件改造清单（3A 批次）：**

| 文件 | 当前违规 | 改造方式 |
|------|----------|----------|
| `domain/memory/manager.py` | `get_connection` + `_json_loads` | 注入 `IDatabase` + `IJsonSerializer` |
| `domain/memory/memory_distiller.py` | `get_connection` + `_json_dumps` + `_json_loads` | 同上 |
| `domain/memory/memory_extractor.py` | `get_connection` | 注入 `IDatabase` |
| `domain/user/auth/auth.py` | `get_connection` | 注入 `IDatabase` |
| `domain/user/auth/token.py` | `get_connection` | 注入 `IDatabase` |
| `domain/user/profile/manager.py` | `get_connection` + `_json_dumps` + `_json_loads` | 注入 `IDatabase` + `IJsonSerializer` |
| `domain/user/session/manager.py` | `get_connection` | 注入 `IDatabase` |
| `domain/user/session/task_state.py` | `get_connection` + `_json_dumps` + `_json_loads` | 注入 `IDatabase` + `IJsonSerializer` |
| `domain/agent/repository.py` | `get_connection` | 注入 `IDatabase` |
| `domain/feedback/repository.py` | `get_connection` | 注入 `IDatabase` |
| `domain/travel/album/repository.py` | `get_connection` | 注入 `IDatabase` |
| `domain/travel/album/service.py` | `get_connection`（2 处） | 注入 `IDatabase` |
| `domain/travel/itinerary/repository.py` | `get_connection` | 注入 `IDatabase` |
| `domain/travel/tools/travel_tools.py` | `get_connection`（3 处） | 注入 `IDatabase` |

> ⚠️ **注意**：每个文件改造后立即运行 `pytest`，确认无回归。

#### 第四步补充：更新所有调用方（实例化点）

改造领域类的 `__init__` 签名后，必须同步更新**所有实例化该类的位置**，否则会因参数缺失而报错。

> ⚠️ **关键**：部分领域类**不在 `app.py` 中实例化**，而是在其他领域类内部直接 `new`。必须搜索全部实例化点，不可遗漏。

**搜索命令**（对每个被改类运行）：

```bash
# 以 DualLayerMemoryManager 为例
findstr /s /r /n "DualLayerMemoryManager(" *.py
# 逐个替换为新的构造方式
```

**3A 批次调用方更新清单：**

| 被改类 | 实例化位置 | 调用方说明 |
|--------|-----------|-----------|
| `DualLayerMemoryManager` | `domain/travel/core.py:70` | `Agent.__init__` 内部 `self._dual_memory = DualLayerMemoryManager()` → 需改为 `DualLayerMemoryManager(db=self._db, json_ser=self._json)`，即 `Agent` 也需接收 `IDatabase` + `IJsonSerializer` |
| `DualLayerMemoryManager` | `api/v1/memory.py:18` | 路由中 `mgr = DualLayerMemoryManager()` → 需从 `app.state` 获取已注入的实例 |
| `DualLayerMemoryManager` | `tests/integration/test_memory.py`（8 处） | 测试中直接 `DualLayerMemoryManager()` → 改为 `DualLayerMemoryManager(db=mock_db, json_ser=mock_json)` |
| `MemoryExtractor` | `domain/travel/core.py:71` | `Agent.__init__` 内部 `self._memory_extractor = MemoryExtractor(llm)` → 需追加 `db` 参数 |
| `MemoryExtractor` | `tests/unit/test_memory_extractor_distiller.py:37` | 测试构造函数 → 追加 mock |
| `MemoryDistiller` | `domain/travel/core.py:72` | `Agent.__init__` 内部 → 同上 |
| `MemoryDistiller` | `application/scheduler.py:45` | `distiller = MemoryDistiller(llm=llm)` → 追加 `db` 参数 |
| `MemoryDistiller` | `tests/unit/test_memory_extractor_distiller.py`（2 处） | 测试构造函数 → 追加 mock |
| `UserStore`（`user/auth/auth.py`） | `app.py` 中通过 `ProfileManager` 等间接使用 | 搜索 `UserStore(` 确认全部实例化点 |
| 其余 Repository 类 | `app.py` 的 `build_orchestrator()` | 当前在 `app.py` 中实例化，直接追加 `db` 参数 |

> 💡 **`domain/travel/core.py` 的特殊处理**：`Agent.__init__`（第 49 行）当前接收 `llm`、`tool_registry` 等参数，但**不接收 `db`**。改造后需要：
> 1. 在 `Agent.__init__` 参数中新增 `db: IDatabase` 和 `json_ser: IJsonSerializer`
> 2. 将它们传递给第 70-72 行的 `DualLayerMemoryManager()`、`MemoryExtractor()`、`MemoryDistiller()`
> 3. 在 `app.py` 的 `_build_travel_agent_core()` 中传入 `db` 和 `json_ser`

```python
# domain/travel/core.py 整改示例
class Agent:
    def __init__(
        self,
        *,
        llm: OpenAILLM,                # 第三波 3B 批次后改为 ILLMGateway
        prompt_builder: PromptBuilder,
        session_store: SessionManager,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
        db: IDatabase,                 # ← 新增
        json_ser: IJsonSerializer,     # ← 新增
        mcp_catalog: MCPCatalog | None = None,
        # ... 其余参数不变 ...
    ) -> None:
        # ... 原有赋值不变 ...
        self._dual_memory = DualLayerMemoryManager(db=db, json_ser=json_ser)      # ← 改
        self._memory_extractor = MemoryExtractor(llm, db=db)                       # ← 改
        self._memory_distiller = MemoryDistiller(llm, db=db, json_ser=json_ser)   # ← 改
```

#### 第五步：验证

```bash
# 运行依赖检查脚本，确认 3A 批次的违规已消除
py -3 -X utf8 -c "
import os, re
v = []
for r, d, files in os.walk('domain'):
    if '__pycache__' in r: continue
    for f in files:
        if not f.endswith('.py'): continue
        fp = os.path.join(r, f)
        for i, line in enumerate(open(fp, encoding='utf-8').read().splitlines(), 1):
            s = line.strip()
            if s.startswith('#'): continue
            # 只检查 database 相关违规
            if re.search(r'from infrastructure\.persistence\.database|import infrastructure\.persistence\.database', s):
                v.append(f'{fp}:{i} {s}')
print(f'database 违规剩余: {len(v)} 处')
for x in v: print(f'  {x}')
"

# 运行测试
pytest

# 启动验证
py -3 -m uvicorn api.server:app --host 127.0.0.1 --port 8000
# 能启动 → 验证通过
```

### 5.3 步骤 3B-3G：其余接口解耦

按同样的模式，逐批建立接口 → 实现接口 → 注入 → 改造领域层 → 验证。

#### 接口定义清单

```python
# domain/shared/ports/llm_gateway.py
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from collections.abc import AsyncIterator


@dataclass
class LLMResponseDTO:
    """LLM 响应数据传输对象。"""
    content: str
    tool_calls: list[dict] | None = None
    finish_reason: str | None = None
    usage: dict | None = None


class ILLMGateway(ABC):
    """LLM 调用网关抽象。"""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> LLMResponseDTO:
        ...

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> AsyncIterator[LLMResponseDTO]:
        ...
```

```python
# domain/shared/ports/crypto.py
from __future__ import annotations
from abc import ABC, abstractmethod


class IPasswordHasher(ABC):
    """密码哈希抽象。"""

    @abstractmethod
    def hash(self, password: str) -> str: ...

    @abstractmethod
    def verify(self, password: str, stored: str) -> bool: ...

    @abstractmethod
    def needs_upgrade(self, stored: str) -> bool: ...
```

```python
# domain/shared/ports/tool_gateway.py
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class IToolRegistry(ABC):
    """工具注册表抽象。"""

    @abstractmethod
    def register(self, tool: Any) -> None: ...

    @abstractmethod
    def get(self, name: str) -> Any: ...

    @abstractmethod
    def list_specs(self) -> list[Any]: ...


class IToolExecutor(ABC):
    """工具执行器抽象。"""

    @abstractmethod
    async def execute(self, name: str, arguments: dict) -> Any: ...
```

```python
# domain/shared/ports/mcp_gateway.py
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class IMCPCatalog(ABC):
    """MCP 目录抽象。"""

    @abstractmethod
    def list_servers(self) -> list[Any]: ...

    @abstractmethod
    def get_server(self, server_id: str) -> Any | None: ...


class IMCPRuntime(ABC):
    """MCP 运行时抽象。"""

    @abstractmethod
    def build_specs(self) -> list[Any]: ...

    @abstractmethod
    def build_handlers(self) -> dict[str, Any]: ...
```

```python
# domain/shared/ports/skill_provider.py
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class ISkillProvider(ABC):
    """技能提供者抽象。"""

    @abstractmethod
    def list_skills(self) -> list[Any]: ...

    @abstractmethod
    def get_skill(self, name: str) -> Any | None: ...
```

#### 基础设施层实现方式

每个基础设施层现有类追加实现接口：

```python
# infrastructure/llm/openai.py
from domain.shared.ports.llm_gateway import ILLMGateway, LLMResponseDTO

class OpenAILLM(ILLMGateway):  # 追加继承接口
    # 原有方法保持不变，只需确保方法签名与接口一致
    async def chat(self, messages, tools=None, temperature=0.7) -> LLMResponseDTO:
        # 原有实现，返回值包装为 LLMResponseDTO
        ...
```

> ⚠️ **关键注意**：改造时**不改变现有方法的行为**，只做两件事：
> 1. 基础设施类追加 `implements` 声明
> 2. 领域类 `__init__` 参数从具体类改为接口类型
>
> 方法体内部逻辑不动，避免引入 bug。

### 5.4 验证：全部 54 处违规清零

```bash
# 最终验证：domain 层零 infrastructure 依赖
py -3 -X utf8 -c "
import os, re
violations = []
for r, d, files in os.walk('domain'):
    if '__pycache__' in r: continue
    for f in files:
        if not f.endswith('.py'): continue
        fp = os.path.join(r, f)
        for i, line in enumerate(open(fp, encoding='utf-8').read().splitlines(), 1):
            s = line.strip()
            if s.startswith('#'): continue
            if re.search(r'from infrastructure\.|import infrastructure\.', s):
                violations.append(f'{fp}:{i} {s}')
if violations:
    print(f'❌ 仍有 {len(violations)} 处违规:')
    for v in violations: print(f'  {v}')
else:
    print('✅ 领域层依赖方向完全合规（0 处违规）')
"
```

---

## 6. 第四波：测试覆盖率提升（Day 8-12）

> **目标**：单元测试覆盖率从 ~10% 提升至 ≥ 70%。
> **前置条件**：第三波解耦完成（领域层可 mock 注入）。
> **风险**：低（只加测试，不改生产代码）
> **预计工时**：5 天

### 6.1 修复 CI 跳过的测试

当前 CI 中 `--ignore-glob="*test_prompting*"` 跳过了一个测试文件，这是优先要修复的。

```bash
# 1. 直接运行被跳过的测试，看失败原因
pytest tests/unit/test_prompting.py -v

# 2. 根据失败原因修复（可能是接口变更、mock 不匹配等）
# 3. 修复后确认全量通过
pytest tests/unit/test_prompting.py -v

# 4. 从 CI 中移除 --ignore-glob
#    编辑 .github/workflows/ci.yml 第 27 行
#    将: pytest --ignore-glob="*test_prompting*" --cov=. --cov-report=xml
#    改为: pytest --cov=. --cov-report=xml
```

### 6.2 新增测试文件清单

按优先级排序，每个文件对应一个被测模块：

| 优先级 | 测试文件 | 被测模块 | 行数 | 测试要点 |
|--------|----------|----------|------|----------|
| 🔴 P0 | `tests/unit/test_domain/test_engine.py` | `reasoning/engine.py` | 1293 | Tier0/1/2 三层决策路径 |
| 🔴 P0 | `tests/unit/test_domain/test_orchestrator.py` | `agent/orchestrator.py` | 609 | 委派逻辑、智能体选择 |
| 🟠 P1 | `tests/unit/test_domain/test_travel_core.py` | `travel/core.py` | 441 | Agent 主循环 |
| 🟠 P1 | `tests/unit/test_domain/test_auth_service.py` | `user/auth/auth.py` | — | 注册、登录、密码验证 |
| 🟠 P1 | `tests/unit/test_domain/test_factory.py` | `agent/factory.py` | — | 智能体实例化 |
| 🟡 P2 | `tests/unit/test_domain/test_memory_manager.py` | `memory/manager.py` | — | 长期/短期记忆 CRUD |
| 🟡 P2 | `tests/unit/test_domain/test_memory_distiller.py` | `memory/memory_distiller.py` | — | 记忆蒸馏逻辑 |
| 🟡 P2 | `tests/unit/test_domain/test_travel_classifier.py` | `travel/intent/travel_classifier.py` | 661 | 意图分类 |
| 🟡 P2 | `tests/unit/test_domain/test_itinerary_parser.py` | `travel/itinerary/parser.py` | — | 行程解析 |
| 🟡 P2 | `tests/unit/test_domain/test_album_service.py` | `travel/album/service.py` | — | 相册服务 |

### 6.3 测试编写规范

遵循 AGENTS.md §8.3，使用 AAA 模式 + mock 注入：

```python
# tests/unit/test_domain/test_orchestrator.py
"""OrchestratorAgent 单元测试。"""
from __future__ import annotations

import pytest
from unittest.mock import Mock, AsyncMock

from domain.agent.orchestrator import OrchestratorAgent
from domain.agent.schema import AgentConfig
from domain.shared.ports.llm_gateway import ILLMGateway, LLMResponseDTO


class TestOrchestratorTier0:
    """Tier0 快路径测试：简单问题直接回复。"""

    @pytest.mark.asyncio
    async def test_simple_question_returns_directly(self):
        """简单问题应直接回复，不委派。"""
        # Arrange
        mock_llm = Mock(spec=ILLMGateway)
        mock_llm.chat = AsyncMock(return_value=LLMResponseDTO(content="你好！"))
        orchestrator = OrchestratorAgent(
            llm=mock_llm,
            factory=Mock(),
            builtin_configs=[],
            custom_repo=Mock(),
            default_agent="yunhe",
        )

        # Act
        result = await orchestrator.route("你好", session_id="s1")

        # Assert
        assert "你好" in result.reply
        mock_llm.chat.assert_awaited_once()


class TestOrchestratorTier1:
    """Tier1 function calling 委派测试。"""

    @pytest.mark.asyncio
    async def test_travel_question_delegates_to_travel_agent(self):
        """旅行类问题应委派给 travel agent。"""
        # Arrange
        mock_llm = Mock(spec=ILLMGateway)
        mock_llm.chat = AsyncMock(return_value=LLMResponseDTO(
            content="",
            tool_calls=[{"function": {"name": "delegate_to", "arguments": '{"agent_id": "travel", "message": "北京3日游"}'}}],
        ))
        mock_factory = Mock()
        mock_travel_agent = Mock()
        mock_travel_agent.run = AsyncMock(return_value=Mock(reply="为您规划北京3日游..."))
        mock_factory.create.return_value = mock_travel_agent

        orchestrator = OrchestratorAgent(
            llm=mock_llm,
            factory=mock_factory,
            builtin_configs=[AgentConfig(id="travel", name="旅行助手")],
            custom_repo=Mock(),
            default_agent="yunhe",
        )

        # Act
        result = await orchestrator.route("帮我规划北京3日游", session_id="s1")

        # Assert
        mock_factory.create.assert_called_with(agent_id="travel")
        assert "北京" in result.reply
```

### 6.4 覆盖率验证

```bash
# 运行覆盖率报告
pytest --cov=. --cov-report=term-missing

# 确认 domain 层覆盖率 ≥ 70%
# 重点关注 Missing 列，逐个补齐未覆盖的行
```

---

## 7. 第五波：超大文件拆分（Day 13-15）

> **目标**：9 个超标文件全部降至 400 行以下。
> **前置条件**：第三波解耦完成（可按接口边界拆分）+ 第四波测试完成（有安全网）。
> **风险**：中（改动核心逻辑，但有测试保护）
> **预计工时**：3 天

### 7.1 拆分优先级与方案

| 优先级 | 文件 | 行数 | 拆分方案 |
|--------|------|------|----------|
| 🔴 P0 | `domain/reasoning/engine.py` | 1293 | 按 Tier0/Tier1/Tier2 拆分 |
| 🟠 P1 | `infrastructure/persistence/database.py` | 662 | 迁移函数抽到 `migrations/` |
| 🟠 P1 | `domain/travel/intent/travel_classifier.py` | 661 | 按意图类别拆分 |
| 🟠 P1 | `infrastructure/mcp/runtime.py` | 651 | 按协议处理拆分 |
| 🟠 P1 | `domain/agent/orchestrator.py` | 609 | 按调度层拆分 |
| 🟡 P2 | `domain/travel/services/context_preparer.py` | 461 | 按上下文准备阶段拆分 |
| 🟡 P2 | `domain/travel/core.py` | 441 | 主循环 / 工具调用 / 消息处理拆分 |
| 🟡 P2 | `application/trending/manager.py` | 433 | 爬取 / 缓存 / 解析拆分 |
| 🟢 P3 | `tests/unit/test_memory_extractor_distiller.py` | 415 | 按被测模块拆分为两个文件 |

### 7.2 engine.py 拆分示例

```
domain/reasoning/
├── engine.py              # 整改后：Engine 入口 + 调度（< 200 行）
├── tier0_fast_path.py     # Tier0：快路径（简单问题直接回复）
├── tier1_function_call.py # Tier1：function calling 委派
├── tier2_delegation.py    # Tier2：委派执行
├── context_builder.py     # 上下文构建（消息历史、工具列表）
├── response_parser.py     # LLM 响应解析
└── __init__.py
```

拆分步骤：

```bash
# 1. 先确认 engine.py 的测试全绿（第四波已补齐）
pytest tests/unit/test_domain/test_engine.py -v

# 2. 逐步提取模块（每次提取一个，运行测试确认无回归）
# 2.1 提取 Tier0 逻辑到 tier0_fast_path.py → pytest
# 2.2 提取 Tier1 逻辑到 tier1_function_call.py → pytest
# 2.3 提取 Tier2 逻辑到 tier2_delegation.py → pytest
# 2.4 提取上下文构建到 context_builder.py → pytest
# 2.5 提取响应解析到 response_parser.py → pytest

# 3. 最终 engine.py 只保留入口和调度
py -3 -X utf8 -c "print(sum(1 for _ in open('domain/reasoning/engine.py',encoding='utf-8')), 'lines')"
# 确认 < 400 行
```

### 7.3 database.py 拆分方案

```
infrastructure/persistence/
├── database.py            # 整改后：连接管理 + init_db（< 200 行）
├── connection.py          # get_connection / reset_connection（从 database.py 提取）
├── json_utils.py          # _json_dumps / _json_loads（提升为公共）
├── schema.py              # _SCHEMA 建表 SQL 常量
└── migrations/
    ├── __init__.py         # _MIGRATIONS 注册 + _run_migrations
    ├── m001_m005.py        # 迁移 1-5
    └── m006_m010.py       # 迁移 6-10
```

> ⚠️ **注意**：`database.py` 的 `_json_dumps` / `_json_loads` 已在第三波被 `IJsonSerializer` 接口包装。拆分时只需移动物理位置，不改接口。

### 7.4 验证

```bash
# 全量文件行数检查
py -3 -X utf8 -c "
import os
violations = []
for top in ['api', 'application', 'domain', 'infrastructure', 'config', 'tests']:
    for r, d, files in os.walk(top):
        if '__pycache__' in r: continue
        for f in files:
            if f.endswith('.py'):
                n = sum(1 for _ in open(os.path.join(r, f), encoding='utf-8'))
                if n > 400: violations.append(f'{n:5d}  {os.path.join(r, f)}')
if violations:
    print(f'❌ 仍有 {len(violations)} 个超标文件:')
    for v in violations: print(f'  {v}')
else:
    print('✅ 所有文件 ≤ 400 行')
"

# 测试全量通过
pytest

# 启动验证
py -3 -m uvicorn api.server:app --host 127.0.0.1 --port 8000
```

---

## 8. 第六波：工程化补全（Day 16-18）

> **目标**：补全 CI 前端 job、容器化支持、多版本矩阵。
> **风险**：低（只加配置，不改代码）
> **预计工时**：2-3 天

### 8.1 CI 补全

```yaml
# .github/workflows/ci.yml（整改后）
name: CI
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  backend-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install ruff
      - run: ruff check .

  backend-test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]"
      - run: pytest --cov=. --cov-report=xml
      - uses: codecov/codecov-action@v4

  backend-typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e ".[dev]"
      - run: mypy api application domain infrastructure
    continue-on-error: true  # 初期非阻塞，逐步收紧

  backend-security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install bandit
      - run: bandit -r api application domain infrastructure

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json
      - run: cd frontend && npm ci
      - run: cd frontend && npm run lint
      - run: cd frontend && npm run check
      - run: cd frontend && npm run build
```

### 8.2 容器化

创建 `Dockerfile`（后端）、`frontend/Dockerfile`（前端）、`docker-compose.yml`。

具体内容参见 `docs/api/ARCHITECTURE_IMPROVEMENT.md` §9，此处不重复。

### 8.3 迁移 app.py

```bash
# 将 app.py 迁移到 application/container.py
git mv app.py application/container.py

# 更新 api/server.py 中的引用
# from app import build_orchestrator  →  from application.container import build_orchestrator
```

**验证**：
```bash
# 确认引用更新
findstr /s /r /n "from app import" *.py
# 应该无输出（或只有根目录的兼容入口）

# 启动验证
py -3 -m uvicorn api.server:app --host 127.0.0.1 --port 8000
```

---

## 9. 验收与回归

### 9.1 最终验收清单

完成全部六波后，逐项验收：

#### 架构与依赖

- [ ] `domain/` 下无任何 `from infrastructure.*` 语句（检测脚本违规数 = 0）
- [ ] `domain/shared/ports/` 下定义了 IDatabase、ILLMGateway、IPasswordHasher 等抽象接口
- [ ] 基础设施层实现类均声明实现对应接口
- [ ] 依赖注入在 `application/container.py` 中集中组装

#### 代码组织

- [ ] 无 `.py` 文件超过 400 行（特殊文件有文件头注释说明）
- [ ] 根目录无空 `requirements.txt`、无空 `api/routes/`
- [ ] `app.py` 已迁移至 `application/container.py`
- [ ] `api/intl_coords.py` 已迁移至 `domain/travel/geo/` 并修复编码

#### 测试

- [ ] `pytest` 全量通过，无 `--ignore` 跳过
- [ ] domain 层覆盖率 ≥ 70%
- [ ] `orchestrator.py`、`engine.py`、`core.py`、`auth.py` 均有对应测试文件

#### CI/CD

- [ ] CI 包含前端 lint + typecheck + build
- [ ] 后端测试支持 Python 3.11 + 3.12 矩阵
- [ ] CI 无 `--ignore-glob` 跳过
- [ ] mypy 接入 CI（可 `continue-on-error`）
- [ ] 存在 `Dockerfile` + `docker-compose.yml`

#### 配置与文档

- [ ] `.gitignore` 包含 `.dbg/`
- [ ] `data/.gitkeep` 存在
- [ ] AGENTS.md 无失效引用、无失真描述
- [ ] AGENTS.md 包含已知技术债清单和自验脚本

### 9.2 回归测试

```bash
# 全量检查
ruff check .
pytest --cov=. --cov-report=term-missing

# 依赖检查
py -3 -X utf8 -c "
import os, re
v = []
for r, d, files in os.walk('domain'):
    if '__pycache__' in r: continue
    for f in files:
        if not f.endswith('.py'): continue
        for i, line in enumerate(open(os.path.join(r, f), encoding='utf-8').read().splitlines(), 1):
            s = line.strip()
            if s.startswith('#'): continue
            if re.search(r'from infrastructure\.|import infrastructure\.', s):
                v.append(f'{os.path.join(r,f)}:{i}')
print(f'依赖违规: {len(v)} 处')
"

# 文件行数检查
py -3 -X utf8 -c "
import os
v = []
for top in ['api', 'application', 'domain', 'infrastructure', 'config', 'tests']:
    for r, d, files in os.walk(top):
        if '__pycache__' in r: continue
        for f in files:
            if f.endswith('.py'):
                n = sum(1 for _ in open(os.path.join(r, f), encoding='utf-8'))
                if n > 400: v.append(f'{n} {os.path.join(r,f)}')
print(f'超标文件: {len(v)} 个')
"

# 启动验证
py -3 -m uvicorn api.server:app --host 127.0.0.1 --port 8000
# 能启动、接口可访问 → 最终验收通过
```

### 9.3 对比基线

```bash
# 对比重构前基线
echo "=== 重构后 ==="
echo "依赖违规: 0 处（基线 54）"
echo "超标文件: 0 个（基线 9）"
echo "测试覆盖率: ≥70%（基线 ~10%）"
echo "CI: 前后端完整（基线仅后端）"
```

---

## 10. 回滚预案

### 10.1 单波回滚

每波是独立分支 + 独立 commit，出问题可单波回滚：

```bash
# 回滚某一波
git revert <commit-hash>

# 或回到某波之前
git reset --hard <commit-hash>
```

### 10.2 全量回滚

如果整体重构导致严重问题，回到重构前：

```bash
# 回到 main 分支重构前的状态
git checkout main
git reset --hard <重构前最后一个commit-hash>
```

### 10.3 紧急修复

如果重构后线上出 bug，优先用 hotfix 而非回滚：

```bash
git checkout -b hotfix/xxx main
# 修复 bug
git commit -m "fix: xxx"
git checkout main
git merge hotfix/xxx
```

---

## 11. AGENTS.md 修订清单

重构完成后，需要同步更新 AGENTS.md，使其与重构后的代码状态一致：

### 11.1 必须修订的条目

| 位置 | 修订内容 |
|------|----------|
| §2.2 目录树 | 补充 `domain/shared/ports/` 目录 |
| §2.2 目录树 | `app.py` 改为 `application/container.py` |
| §2.2 目录树 | 补充 `infrastructure/persistence/migrations/` |
| §2.2 目录树 | 补充 `domain/travel/geo/` |
| §2.2 目录树 | `domain/travel/core.py` 行数更新 |
| §2.2 目录树 | `domain/reasoning/` 补充 tier0/tier1/tier2 等拆分文件 |
| §2.4 已知技术债 | TD-01~05 标记为"已消除" |
| §8.1 测试覆盖率 | 更新当前状态为"≥ 70%" |
| §9.1 版本控制 | 注明 `/api` 和 `/api/v1` 双前缀向后兼容 |
| 配套文档 | 更新为 `docs/api/ARCHITECTURE_IMPROVEMENT.md` + 本文档 |

### 11.2 可选新增条目

| 位置 | 新增内容 |
|------|----------|
| §2.3 依赖方向 | 补充"领域层通过 `domain/shared/ports/` 接口依赖基础设施"的正例 |
| §14.2 工具命令 | 补充 `docker compose up` 一键启动 |
| §16 附录 | 补充"重构历史"小节，记录本次重构时间线和成果 |

---

## 附录：重构进度跟踪表

| 波次 | 内容 | 预计工时 | 状态 | 负责人 | 完成日期 |
|------|------|----------|------|--------|----------|
| 第一波 | 零风险清理 | 0.5 天 | ⬜ 待开始 | | |
| 第二波 | AGENTS.md 修复 | 0.5 天 | ⬜ 待开始 | | |
| 第三波 | 领域层解耦 | 3-5 天 | ⬜ 待开始 | | |
| 第四波 | 测试覆盖率 | 5 天 | ⬜ 待开始 | | |
| 第五波 | 文件拆分 | 3 天 | ⬜ 待开始 | | |
| 第六波 | 工程化补全 | 2-3 天 | ⬜ 待开始 | | |
| **合计** | | **14-17 天** | | | |

> 💡 **使用方式**：每完成一波，将 ⬜ 改为 ✅，填写负责人和完成日期。所有波次完成后，运行 §9 验收清单确认达标。

---

**文档版本**：v1.0
**编写日期**：2026-07-13
**维护者**：云合开发团队
**关联规范**：`AGENTS.md` v2.1
