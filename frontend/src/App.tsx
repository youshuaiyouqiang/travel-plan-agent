import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { LoginPage } from './pages/Login'
import { Home } from './pages/Home'
import { ItineraryOverview } from './pages/ItineraryOverview'
import { MemoryPage } from './pages/MemoryPage'
import { ComparePage } from './pages/ComparePage'
import { SharedItinerary } from './pages/SharedItinerary'
import { AlbumPage } from './pages/AlbumPage'
import { useAuthStore } from './hooks/useAuthStore'

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <PrivateRoute>
              <Home />
            </PrivateRoute>
          }
        />
        <Route
          path="/itinerary/:id"
          element={
            <PrivateRoute>
              <ItineraryOverview />
            </PrivateRoute>
          }
        />
        <Route
          path="/memories"
          element={
            <PrivateRoute>
              <MemoryPage />
            </PrivateRoute>
          }
        />
        <Route
          path="/compare"
          element={
            <PrivateRoute>
              <ComparePage />
            </PrivateRoute>
          }
        />
        <Route
          path="/album/:id"
          element={
            <PrivateRoute>
              <AlbumPage />
            </PrivateRoute>
          }
        />
        <Route path="/shared/:token" element={<SharedItinerary />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
