# Phase 4执行建议 - API层拆分策略

> **目标**: 将server.py的43接口拆分到routes/*.py + middleware/*.py
> **策略**: 混合策略(自动化+手动补充)
> **预计时间**: 45-60分钟

---

## 一、Server.py拆分工作量分析

### 当前server.py状态(43接口):

**接口分类**(按业务功能):

1. **Chat接口**(3个):
   - POST /api/chat - 普通对话
   - POST /api/chat/stream - 流式对话
   - GET /api/history - 历史记录

2. **Agents接口**(8个):
   - GET /api/agents - 智能体列表
   - POST /api/agents - 创建智能体
   - PUT /api/agents/:id - 更新智能体
   - DELETE /api/agents/:id - 删除智能体
   - GET /api/agents/builtin - 内置智能体
   - GET /api/agents/custom - 自定义智能体
   - GET /api/agents/:id - 智能体详情
   - POST /api/agents/:id/upload - 上传头像

3. **Skills接口**(3个):
   - GET /api/skills - 技能列表
   - GET /api/skills/builtin - 内置技能
   - GET /api/skills/mcp - MCP技能

4. **Auth接口**(5个):
   - POST /api/auth/signup - 注册
   - POST /api/auth/login - 登录
   - POST /api/auth/logout - 登出
   - GET /api/auth/me - 用户信息
   - GET /api/auth/token - Token验证

5. **Itinerary接口**(8个):
   - GET /api/itinerary - 行程列表
   - POST /api/itinerary - 创建行程
   - PUT /api/itinerary/:id - 更新行程
   - DELETE /api/itinerary/:id - 删除行程
   - GET /api/itinerary/search - 搜索行程
   - GET /api/itinerary/:id - 行程详情
   - GET /api/itinerary/:id/summary - 行程摘要
   - POST /api/itinerary/:id/share - 分享行程

6. **Album接口**(4个):
   - GET /api/album - 相册列表
   - POST /api/album - 上传照片
   - DELETE /api/album/:id - 删除照片
   - GET /api/album/:id - 照片详情

7. **Memory接口**(2个):
   - GET /api/memory - 记忆列表
   - DELETE /api/memory/:id - 删除记忆

8. **Shared接口**(2个):
   - GET /api/shared - 分享列表
   - GET /api/shared/:id - 分享详情

9. **Trending接口**(2个):
   - GET /api/trending - 热门推荐
   - POST /api/trending/refresh - 刷新推荐

10. **Health接口**(1个):
    - GET /api/health - 健康检查

11. **静态文件接口**(3个):
    - GET / - index.html
    - GET /favicon.ico - favicon
    - GET /* - catch-all路由

---

## 二、拆分方案设计

### 路由文件拆分:

```
api/routes/
├── __init__.py       # 路由导出(自动生成)
├── chat.py           # Chat接口(3个)
├── agents.py         # Agents接口(8个)
├── skills.py         # Skills接口(3个)
├── auth.py           # Auth接口(5个)
├── itinerary.py      # Itinerary接口(8个)
├── album.py          # Album接口(4个)
├── memory.py         # Memory接口(2个)
├── shared.py         # Shared接口(2个)
├── trending.py       # Trending接口(2个)
├── health.py         # Health接口(1个)
└── static.py         # 静态文件接口(3个)
```

### 中间件提取:

```
api/middleware/
├── __init__.py       # 中间件导出(自动生成)
├── auth.py           # 认证中间件(提取自server.py)
└── rate_limit.py     # 速率限制中间件(可选,待实现)
```

---

## 三、拆分执行策略

### 策略A: 手动拆分(推荐)

**原因**: server.py接口复杂,涉及大量依赖注入、路径参数、错误处理,自动化拆分风险高。

**手动拆分步骤**:

1. **复制server.py**到routes/*.py模板:
   ```bash
   # 创建路由文件模板
   touch api/routes/chat.py
   touch api/routes/agents.py
   touch api/routes/skills.py
   touch api/routes/auth.py
   touch api/routes/itinerary.py
   touch api/routes/album.py
   touch api/routes/memory.py
   touch api/routes/shared.py
   touch api/routes/trending.py
   touch api/routes/health.py
   touch api/routes/static.py
   ```

2. **手动提取接口代码**:
   - 打开server.py,定位接口定义(如`@app.post("/api/chat")`)
   - 复制完整接口代码到对应的routes/*.py
   - 更新import路径(routes/*.py需导入domain/infrastructure层)

3. **创建路由蓝图**:
   ```python
   # api/routes/chat.py示例
   from fastapi import APIRouter, Depends
   from domain.agent.travel_core import Agent
   from infrastructure.persistence.database import get_connection

   router = APIRouter(prefix="/api", tags=["chat"])

   @router.post("/chat")
   async def chat_endpoint(...):
       # 复制server.py中的接口逻辑
       pass

   @router.post("/chat/stream")
   async def chat_stream_endpoint(...):
       # 复制server.py中的接口逻辑
       pass
   ```

4. **组装路由到server.py**:
   ```python
   # api/server.py简化为路由组装
   from fastapi import FastAPI
   from api.routes import chat, agents, skills, auth, itinerary, album, memory, shared, trending, health, static
   from api.middleware.auth import AuthMiddleware

   app = FastAPI(title="Claw Travel Assistant")

   # 注册路由
   app.include_router(chat.router)
   app.include_router(agents.router)
   app.include_router(skills.router)
   app.include_router(auth.router)
   app.include_router(itinerary.router)
   app.include_router(album.router)
   app.include_router(memory.router)
   app.include_router(shared.router)
   app.include_router(trending.router)
   app.include_router(health.router)
   app.include_router(static.router)

   # 注册中间件
   app.add_middleware(AuthMiddleware)
   ```

---

### 策略B: 保留server.py,仅提取中间件(保守方案)

**原因**: server.py拆分风险高,先提取中间件,后续手动拆分路由。

**提取中间件步骤**:

1. **创建api/middleware/auth.py**:
   ```python
   from fastapi import Request, HTTPException
   from starlette.middleware.base import BaseHTTPMiddleware

   class AuthMiddleware(BaseHTTPMiddleware):
       async def dispatch(self, request: Request, call_next):
           # 提取server.py中的认证逻辑
           if request.url.path in PUBLIC_PATHS:
               return await call_next(request)
           # Token验证逻辑...
           return await call_next(request)
   ```

2. **server.py注册中间件**:
   ```python
   from api.middleware.auth import AuthMiddleware
   app.add_middleware(AuthMiddleware)
   ```

---

## 四、路由文件模板示例

### chat.py模板:

```python
# api/routes/chat.py
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import json

from domain.agent.orchestrator import OrchestratorAgent
from domain.agent.schema import AgentConfig
from domain.user.auth.auth import UserStore
from domain.user.auth.token import verify_token
from infrastructure.persistence.database import get_connection

router = APIRouter(prefix="/api", tags=["chat"])

class ChatRequest(BaseModel):
    message: str
    agent_id: Optional[str] = None
    user_id: Optional[int] = None

class ChatResponse(BaseModel):
    reply: str
    agent_actions: list = []

@router.post("/chat")
async def chat_endpoint(req: ChatRequest):
    """普通对话接口"""
    # TODO: 从server.py复制完整接口逻辑
    pass

@router.post("/chat/stream")
async def chat_stream_endpoint(req: ChatRequest):
    """流式对话接口"""
    # TODO: 从server.py复制完整接口逻辑
    async def generate():
        yield json.dumps({"type": "reply", "text": "..."})
    return StreamingResponse(generate(), media_type="text/event-stream")

@router.get("/history")
async def history_endpoint(user_id: int):
    """历史记录接口"""
    # TODO: 从server.py复制完整接口逻辑
    pass
```

---

### auth.py模板:

```python
# api/routes/auth.py
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import hashlib

from domain.user.auth.auth import UserStore, User
from domain.user.auth.token import generate_token, verify_token
from infrastructure.persistence.database import get_connection

router = APIRouter(prefix="/api/auth", tags=["auth"])

class SignupRequest(BaseModel):
    username: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/signup")
async def signup_endpoint(req: SignupRequest):
    """注册接口"""
    # TODO: 从server.py复制完整接口逻辑
    pass

@router.post("/login")
async def login_endpoint(req: LoginRequest):
    """登录接口"""
    # TODO: 从server.py复制完整接口逻辑
    pass

@router.post("/logout")
async def logout_endpoint():
    """登出接口"""
    # TODO: 从server.py复制完整接口逻辑
    pass

@router.get("/me")
async def me_endpoint(token: str):
    """用户信息接口"""
    # TODO: 从server.py复制完整接口逻辑
    pass
```

---

## 五、Import路径更新建议

### routes/*.py import路径更新:

由于routes/*.py引用domain/infrastructure层,需确保import路径正确:

```python
# 正确的import路径示例
from domain.agent.orchestrator import OrchestratorAgent  # ✅
from domain.agent.schema import AgentConfig              # ✅
from domain.user.auth.auth import UserStore              # ✅
from infrastructure.persistence.database import get_connection  # ✅
from infrastructure.llm.openai import OpenAILLM          # ✅
from config import settings                              # ⚠️ 待Phase 6迁移到config.settings
```

---

## 六、建议执行步骤

由于server.py拆分工作量巨大,我建议:

### Step 1: 创建路由文件模板(自动化)
```bash
# 我可以帮你创建11个路由文件模板
```

### Step 2: 手动提取接口代码(手动)
```bash
# 你手动从server.py复制接口到routes/*.py
# 预计30-45分钟
```

### Step 3: 组装路由到server.py(自动化)
```bash
# 我帮你更新server.py为路由组装器
```

### Step 4: 验证API接口(手动)
```bash
# 启动后端测试所有接口
python app.py
curl http://localhost:8000/api/health
```

---

## 七、我的建议

**推荐方案**: 采用策略B(保守方案),先提取中间件,保留server.py。

**原因**:
- server.py拆分风险高(43接口涉及大量依赖)
- Phase 5-7工作量较小,可先完成
- 后续可手动拆分server.py(逐步优化)

**执行顺序**:
1. ✅ Phase 4-2: 提取中间件(简单)
2. ✅ Phase 5-6: 应用层+配置迁移(简单)
3. ✅ Phase 7: 文档补充(简单)
4. ⚠️ Phase 4-1: server.py拆分(手动,最后执行)

---

**生成时间**: 2026-06-30 23:40
**状态**: Phase 4拆分建议已创建,等待决策