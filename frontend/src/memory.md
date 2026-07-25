# frontend/src/ — 模块记忆

## 职责定位
React 应用启动层：入口、全局路由、全局样式与环境类型声明。

## 关键文件
- `main.tsx`：React 18 `createRoot` 入口，StrictMode，渲染 `<App/>`。
- `App.tsx`：全局路由表（react-router v7），所有页面 `lazy` 懒加载；定义 `PrivateRoute`（未登录跳 /login）、`AgentRouteGuard`（需 travel 激活）、`ItineraryRedirect`（旧路径兼容重定向）。
- `index.css`：Tailwind 指令 + CSS 变量、leaflet 样式、滚动条与动画关键帧。
- `vite-env.d.ts`：声明 `VITE_PUBLIC_URL` / `VITE_AMAP_KEY` 环境变量类型。

## 目录结构约定
- `features/{域}/api.ts`：数据契约与 API 调用（必须走 features/auth/client.ts）。
- `hooks/*Store.ts`：zustand 状态。
- `components/` + `pages/`：视图。
- `lib/` `utils/`：工具函数。

## 业务边界要点
- 公开路由仅 `/login` 与 `/shared/:token`；其余全部 PrivateRoute。
- `/agent/travel/*` 额外需 `AgentRouteGuard(agent="travel")`。
- `/admin/news` 路由对所有人可见，授权由后端 403 强制（前端只展示"无权访问"）。
