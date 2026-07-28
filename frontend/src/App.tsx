import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom'
import { useAuthStore } from './hooks/useAuthStore'
import { AgentRouteGuard } from './components/AgentRouteGuard'
import { AppLayout } from './components/AppLayout'

// P2-3：路由级动态加载，拆分打包体积，避免首屏加载全部页面 chunk。
const LoginPage = lazy(() =>
  import('./pages/Login').then((m) => ({ default: m.LoginPage })),
)
const Home = lazy(() => import('./pages/Home').then((m) => ({ default: m.Home })))
const ItineraryOverview = lazy(() =>
  import('./pages/ItineraryOverview').then((m) => ({ default: m.ItineraryOverview })),
)
const MemoryPage = lazy(() =>
  import('./pages/MemoryPage').then((m) => ({ default: m.MemoryPage })),
)
const SharedItinerary = lazy(() =>
  import('./pages/SharedItinerary').then((m) => ({ default: m.SharedItinerary })),
)
const TravelArchive = lazy(() =>
  import('./pages/TravelArchive').then((m) => ({ default: m.TravelArchive })),
)
const AgentCenter = lazy(() =>
  import('./pages/AgentCenter').then((m) => ({ default: m.AgentCenter })),
)
const AgentEditor = lazy(() =>
  import('./pages/AgentEditor').then((m) => ({ default: m.AgentEditor })),
)
const SkillCenter = lazy(() =>
  import('./pages/SkillCenter').then((m) => ({ default: m.SkillCenter })),
)
const MCPCenter = lazy(() => import('./pages/MCPCenter').then((m) => ({ default: m.MCPCenter })))
const FavoritesPage = lazy(() =>
  import('./pages/FavoritesPage').then((m) => ({ default: m.FavoritesPage })),
)
const NewsAdmin = lazy(() => import('./pages/NewsAdmin').then((m) => ({ default: m.NewsAdmin })))
const StockPage = lazy(() => import('./features/stock').then((m) => ({ default: m.StockPage })))

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />
}

/** 旧路由 /itinerary/:id 兼容重定向到新路径 */
function ItineraryRedirect() {
  const { id } = useParams()
  return <Navigate to={`/agent/travel/itinerary/${id}`} replace />
}

function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<div className="h-screen w-screen bg-slate-50" />}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/shared/:token" element={<SharedItinerary />} />

          {/* 主对话界面 */}
          <Route
            path="/"
            element={
              <PrivateRoute>
                <Home />
              </PrivateRoute>
            }
          />

          {/* Agent 中心 */}
          <Route
            path="/agents"
            element={
              <PrivateRoute>
                <AppLayout>
                  <AgentCenter />
                </AppLayout>
              </PrivateRoute>
            }
          />

          {/* Agent 创建/编辑 */}
          <Route
            path="/agents/create"
            element={
              <PrivateRoute>
                <AppLayout>
                  <AgentEditor />
                </AppLayout>
              </PrivateRoute>
            }
          />
          <Route
            path="/agents/edit/:agentId"
            element={
              <PrivateRoute>
                <AppLayout>
                  <AgentEditor />
                </AppLayout>
              </PrivateRoute>
            }
          />
          <Route
            path="/agents/view/:agentId"
            element={
              <PrivateRoute>
                <AppLayout>
                  <AgentEditor />
                </AppLayout>
              </PrivateRoute>
            }
          />

          {/* 记忆页 — 保留现有路由，不归入 travel 守卫（记忆是跨智能体的） */}
          <Route
            path="/memories"
            element={
              <PrivateRoute>
                <AppLayout>
                  <MemoryPage />
                </AppLayout>
              </PrivateRoute>
            }
          />

          {/* 我的收藏 */}
          <Route
            path="/favorites"
            element={
              <PrivateRoute>
                <FavoritesPage />
              </PrivateRoute>
            }
          />

          {/* 新闻来源审核后台 — 路由对所有人开放，授权边界由后端 403 强制 */}
          <Route
            path="/admin/news"
            element={
              <PrivateRoute>
                <NewsAdmin />
              </PrivateRoute>
            }
          />

          {/* 股市复盘（Task 7） */}
          <Route
            path="/stock"
            element={
              <PrivateRoute>
                <StockPage />
              </PrivateRoute>
            }
          />
          <Route
            path="/stock/reports/:reportId"
            element={
              <PrivateRoute>
                <StockPage />
              </PrivateRoute>
            }
          />

          {/* Skill 中心 */}
          <Route
            path="/skills"
            element={
              <PrivateRoute>
                <AppLayout>
                  <SkillCenter />
                </AppLayout>
              </PrivateRoute>
            }
          />

          {/* MCP 中心 */}
          <Route
            path="/mcps"
            element={
              <PrivateRoute>
                <AppLayout>
                  <MCPCenter />
                </AppLayout>
              </PrivateRoute>
            }
          />

          {/* 旅行智能体专业页面（需 travel 激活） */}
          <Route
            path="/agent/travel/itinerary/:id"
            element={
              <PrivateRoute>
                <AgentRouteGuard agent="travel">
                  <AppLayout>
                    <ItineraryOverview />
                  </AppLayout>
                </AgentRouteGuard>
              </PrivateRoute>
            }
          />
          {/* 旅行存档视图（不可变）：从草稿确认后跳转，或从历史存档进入 */}
          <Route
            path="/agent/travel/archive/:id"
            element={
              <PrivateRoute>
                <AgentRouteGuard agent="travel">
                  <AppLayout>
                    <TravelArchive />
                  </AppLayout>
                </AgentRouteGuard>
              </PrivateRoute>
            }
          />

          {/* 旧路由兼容重定向 */}
          <Route path="/itinerary/:id" element={<ItineraryRedirect />} />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}

export default App
