import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom'
import { LoginPage } from './pages/Login'
import { Home } from './pages/Home'
import { ItineraryOverview } from './pages/ItineraryOverview'
import { MemoryPage } from './pages/MemoryPage'
import { ComparePage } from './pages/ComparePage'
import { SharedItinerary } from './pages/SharedItinerary'
import { AlbumPage } from './pages/AlbumPage'
import { AgentCenter } from './pages/AgentCenter'
import { AgentEditor } from './pages/AgentEditor'
import { SkillCenter } from './pages/SkillCenter'
import { MCPCenter } from './pages/MCPCenter'
import { FavoritesPage } from './pages/FavoritesPage'
import { NewsAdmin } from './pages/NewsAdmin'
import { useAuthStore } from './hooks/useAuthStore'
import { AgentRouteGuard } from './components/AgentRouteGuard'
import { AppLayout } from './components/AppLayout'

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
        <Route
          path="/agent/travel/album/:id"
          element={
            <PrivateRoute>
              <AgentRouteGuard agent="travel">
                <AppLayout>
                  <AlbumPage />
                </AppLayout>
              </AgentRouteGuard>
            </PrivateRoute>
          }
        />
        <Route
          path="/agent/travel/compare"
          element={
            <PrivateRoute>
              <AgentRouteGuard agent="travel">
                <AppLayout>
                  <ComparePage />
                </AppLayout>
              </AgentRouteGuard>
            </PrivateRoute>
          }
        />

        {/* 旧路由兼容重定向 */}
        <Route path="/itinerary/:id" element={<ItineraryRedirect />} />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
