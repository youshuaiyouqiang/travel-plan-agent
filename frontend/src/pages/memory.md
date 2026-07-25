# frontend/src/pages/ — 模块记忆

## 职责定位
与 App.tsx 路由一一对应的完整页面（全部懒加载），承载具体业务场景。

## 关键文件
- `Login.tsx`：登录/注册页；成功后仅写 UI 态（authLogin），不持有 token；已登录自动跳 `/`。
- `Home.tsx`：主对话页（Nav + 对话 + SessionSidebar 三栏）——SSE 事件流处理、会话初始化、热点研判入口、Agent URL 参数激活、StrictMode 初始化守卫。
- `AgentCenter.tsx`：内置/我的/社区智能体列表（使用/编辑/删除/克隆）。
- `AgentEditor.tsx`：Agent 创建/编辑/查看；内置 Agent 编辑时另存为自定义副本；温度滑块、Skill/MCP 选择、公开设置。
- `SkillCenter.tsx`：Skill 列表与分类筛选，展示配置状态与所需环境变量。
- `MCPCenter.tsx`：MCP Server 列表（adapter_available、部分可用/未安装状态）。
- `MemoryPage.tsx`：记忆中心——长期/短期分类（偏好/事实/经验），删除与刷新。
- `FavoritesPage.tsx`：新闻收藏列表，取消收藏、跳原文。
- `NewsAdmin.tsx`：新闻来源审核后台——403 显示"无权访问"；审核需填理由（1-500 字）；展示审计记录。
- `ItineraryOverview.tsx`：行程概览（草稿/确认态）——统计卡、地图、日程、分享面板。
- `TravelArchive.tsx`：不可变存档视图——仅"基于此存档继续编辑"（复制为新草稿），原存档不变。
- `SharedItinerary.tsx`：免登录分享页——按 token 加载行程、访问次数与多日地图。

## 业务边界要点
- Home 研判热点不传新闻全文，靠后端 `session.news_id` 锚定。
- AgentEditor：内置 Agent 不可直接改，保存即创建自定义副本。
- 各页遵循业务红线：不展示 actual_cost/checked_in/相册；管理员授权由后端强制。
