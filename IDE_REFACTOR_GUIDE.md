# IDE批量重构指南 - 处理剩余import路径

> **目标**: 使用PyCharm/VSCode的"重构"功能批量更新所有domain层import路径
> **预计时间**: 10-30分钟
> **风险**: 零风险(IDE保证正确性)

---

## 一、PyCharm重构操作指南(推荐)

### 1.1 准备工作

**执行前必做**:
1. ✅ Git提交当前状态(Phase 2文件迁移完成)
2. ✅ PyCharm清理缓存: File → Invalidate Caches → Invalidate and Restart
3. ✅ 确保PyCharm已识别新domain目录结构

**验证PyCharm识别新结构**:
- Project面板应显示domain/agent/travel_core.py等新路径
- 如PyCharm未识别,右键项目根目录 → Reload from Disk

---

### 1.2 重构操作步骤(逐个执行)

#### 步骤1: 重命名文件(改名问题)

很多文件在迁移时改名了,需要先重命名:

**操作示例**:
```
# 重命名 core/memory.py → manager.py
1. 在PyCharm中找到 core/memory.py (如还存在则删除,如不存在则跳过)
2. 找到 domain/memory/memory.py
3. 右键 domain/memory/memory.py → Refactor → Rename
4. 输入新名: manager.py
5. PyCharm自动更新所有 import from core.memory → domain.memory.manager
```

**需重命名的文件列表**:
```
domain/memory/memory.py → manager.py
domain/user/session/session.py → manager.py
domain/user/auth/auth.py → manager.py (如存在)
domain/reasoning/reasoning.py → engine.py
```

#### 步骤2: 移动文件(更新import路径)

对每个旧路径执行"安全删除"重构:

**操作示例**:
```
# 安全删除旧路径 core.memory (引用自动更新到domain.memory.manager)
1. 在PyCharm中找到旧的 core/memory.py (如还存在)
2. 右键 core/memory.py → Refactor → Safe Delete
3. PyCharm检查所有引用,显示"Usages to be deleted"
4. 确认所有引用都已迁移到domain/memory/manager.py
5. 点击"Do Refactor" → PyCharm自动更新所有import
```

**需安全删除的旧路径列表**:
```
core/memory.py (引用已迁移到domain/memory/manager.py)
core/memory_extractor.py (引用已迁移到domain/memory/extractor.py)
core/memory_distiller.py (引用已迁移到domain/memory/distiller.py)
core/reasoning.py (引用已迁移到domain/reasoning/engine.py)
core/prompting.py (引用已迁移到domain/reasoning/prompting.py)
core/prompt_context.py (引用已迁移到domain/reasoning/context.py)
core/contxt_manager.py (引用已迁移到domain/reasoning/context_manager.py)
core/session.py (引用已迁移到domain/user/session/manager.py)
core/task_state.py (引用已迁移到domain/user/session/task_state.py)
core/auth.py (引用已迁移到domain/user/auth/manager.py)
core/token.py (引用已迁移到domain/user/auth/token.py)
core/intent/ (引用已迁移到domain/travel/intent/)
core/itinerary/ (引用已迁移到domain/travel/itinerary/)
core/album/ (引用已迁移到domain/travel/album/)
core/emotion/ (引用已迁移到domain/user/emotion/)
core/profile/ (引用已迁移到domain/user/profile/)
```

#### 步骤3: 批量更新import语句

使用PyCharm的"Find and Replace"批量替换:

**操作示例**:
```
# 批量替换 import语句
1. PyCharm菜单: Edit → Find → Replace in Files
2. 搜索模式: "from core.memory import"
3. 替换模式: "from domain.memory.manager import"
4. Scope: Project Files (整个项目)
5. 点击"Replace All"
```

**批量替换模式列表**:
```
# 搜索 → 替换
from core\.memory import → from domain.memory.manager import
from core\.memory_extractor import → from domain.memory.extractor import
from core\.memory_distiller import → from domain.memory.distiller import
from core\.reasoning import → from domain.reasoning.engine import
from core\.prompting import → from domain.reasoning.prompting import
from core\.prompt_context import → from domain.reasoning.context import
from core\.contxt_manager import → from domain.reasoning.context_manager import
from core\.session import → from domain.user.session.manager import
from core\.task_state import → from domain.user.session.task_state import
from core\.auth import → from domain.user.auth.manager import
from core\.token import → from domain.user.auth.token import
from core\.intent\. → from domain.travel.intent.
from core\.itinerary\. → from domain.travel.itinerary.
from core\.album\. → from domain.travel.album.
from core\.emotion\. → from domain.user.emotion.
from core\.profile\. → from domain.user.profile.
from core\.audit\. → from domain.shared.audit.
from core\.metrics\. → from domain.shared.metrics.
from core\.runtime_facts import → from domain.shared.runtime.facts import
from core\.trace import → from domain.shared.runtime.trace import
from core\.logging_config import → from domain.shared.runtime.logging import
from core\.types import → from domain.shared.types import
```

---

### 1.3 重构验证

**每完成一批重构后验证**:
1. PyCharm菜单: Code → Inspect Code
2. 检查是否有"Unresolved reference"错误
3. 如有错误,手动检查对应的import路径

**最终验证**:
1. PyCharm菜单: Build → Rebuild Project
2. 检查是否有编译错误
3. 运行简单测试: pytest tests/test_memory.py -v

---

## 二、VSCode重构操作指南(备选)

### 2.1 准备工作

**执行前必做**:
1. ✅ Git提交当前状态
2. ✅ VSCode清理缓存: Ctrl+Shift+P → "Developer: Reload Window"
3. ✅ 安装Python扩展(ms-python.python)

---

### 2.2 重构操作步骤

#### 步骤1: 使用Python扩展的"Move Symbol"

**操作示例**:
```
# 移动符号(自动更新import)
1. 打开 domain/memory/memory.py
2. 点击类名 MemoryManager
3. 按 F12 (Go to Definition) 确认符号位置
4. 右键 → "Move Symbol to New File"
5. 输入新文件名: domain/memory/manager.py
6. VSCode自动更新所有import
```

#### 步骤2: 批量查找替换

**操作示例**:
```
# 批量替换 import语句
1. VSCode菜单: Edit → Find in Files
2. 搜索: "from core.memory import"
3. 替换: "from domain.memory.manager import"
4. Scope: workspace (整个工作区)
5. 点击"Replace All"
```

---

## 三、重构后验证清单

### 3.1 代码检查

**PyCharm**:
- Code → Inspect Code → 检查"Unresolved reference"
- Build → Rebuild Project → 检查编译错误

**VSCode**:
- Ctrl+Shift+P → "Python: Run Linting"
- 检查是否有import错误

### 3.2 功能验证

**简单测试**:
```bash
# 运行domain层关键测试
pytest tests/test_memory.py -v
pytest tests/test_reasoning.py -v
pytest tests/test_session.py -v

# 如测试通过,说明import路径正确
```

**启动后端验证**:
```bash
python app.py
# 如启动成功,说明关键import已修复
```

---

## 四、重构常见问题

### 4.1 PyCharm未识别新目录

**解决方案**:
```
1. File → Invalidate Caches → Invalidate and Restart
2. 右键项目根目录 → Reload from Disk
3. 确保domain目录已被PyCharm识别为Python包
```

### 4.2 找不到旧路径文件

**解决方案**:
```
1. 旧路径文件已被移动到domain,PyCharm可能找不到
2. 直接使用批量替换(Edit → Find → Replace in Files)
3. 搜索旧路径,替换新路径
```

### 4.3 import路径改名问题

**解决方案**:
```
1. 先重命名domain文件(如memory.py → manager.py)
2. PyCharm自动更新 import from domain.memory → domain.memory.manager
3. 然后批量替换旧路径
```

---

## 五、重构效率对比

| 方法 | 预计时间 | 风险 | 效率 |
|------|---------|------|------|
| **PyCharm重构** | 10-30分钟 | 零风险 | ⭐⭐⭐⭐⭐ |
| VSCode重构 | 20-40分钟 | 低风险 | ⭐⭐⭐⭐ |
| 批量正则替换 | 30分钟 | 中风险 | ⭐⭐⭐ |
| 手动逐文件修改 | 2-3小时 | 低风险 | ⭐ |

---

## 六、推荐执行顺序

### 优先级顺序:

1. **重命名domain文件** (改名问题)
   - domain/memory/memory.py → manager.py
   - domain/user/session/session.py → manager.py
   - domain/reasoning/reasoning.py → engine.py

2. **批量替换import语句** (最高效)
   - 使用PyCharm: Edit → Find → Replace in Files
   - 按照上述模式列表逐个替换

3. **验证重构结果**
   - Code → Inspect Code
   - 运行关键测试
   - 启动后端验证

---

## 七、重构完成标志

### ✅ 重构完成标准:

- ✅ 所有import路径已更新(无"Unresolved reference")
- ✅ PyCharm编译成功(Build → Rebuild Project)
- ✅ 关键测试通过(pytest tests/test_memory.py)
- ✅ 后端启动成功(python app.py)

---

**生成时间**: 2026-06-30 22:27
**状态**: IDE重构指南已创建,等待用户手动执行 ⚠️