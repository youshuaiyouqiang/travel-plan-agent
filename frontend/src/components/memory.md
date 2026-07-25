# frontend/src/components/ — 模块记忆

## 职责定位
跨页面通用 UI 组件：应用骨架、对话窗口、输入、导航、智能体激活提示、热搜条。

## 关键文件
- `AppLayout.tsx`：应用骨架（左 NavSidebar + 主内容），非 Home 的鉴权页复用。
- `NavSidebar.tsx`：左侧主导航（Agent/Skill/MCP 中心、记忆、收藏、退出登录）。
- `SessionSidebar.tsx`：会话历史栏（新建/切换/删除、折叠、外部刷新触发）。
- `ChatWindow.tsx`：消息流渲染——多方案锚点 `<!--MULTI_PLAN:...-->` 解析、"满意生成概览"按钮、记忆标签、思考步骤、Agent 激活 banner、操作卡片、欢迎页与热搜条。
- `ChatInput.tsx`：输入框（Enter 发送、停止生成、清空、Agent 下拉切换）。
- `AgentRouteGuard.tsx`：路由守卫，`activeAgent === agent` 才放行，否则跳回 `/`。
- `AgentActivationBanner.tsx`：智能体切换提示条（结构化 AgentInfo，支持任意 builtin/custom）。
- `AgentActionCard.tsx`：流式 `actions` 事件的导航操作卡片（先 setActiveAgent 再跳转）。
- `TrendingBar.tsx`：热搜标签云——点击跳原文，悬停分享/收藏/AI 分析；收藏状态与 `/news/favorites` 同步。

## 子目录
- `itinerary/`：行程地图与日程可视化。
- `news/`：新闻热点卡片与证据卡片。
- `travel/`：旅行草稿编辑器。

## 业务边界要点
- 智能体激活是展示态：`activeAgent` 不随请求发送，路由由后端会话模式决定。
- 行程确认按钮幂等：已生成概览后禁用"满意"按钮防重复；切换方案需 confirm 撤销确认。
