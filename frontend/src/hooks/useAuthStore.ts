/**
 * 浏览器认证状态 store（仅 UI 展示态）。
 *
 * P0-1 修复要点：
 * - 不再持有 ``token`` 字段。长期认证凭据由后端以 HttpOnly cookie 下发，JS 不可读。
 * - 所有 API 请求通过 ``features/auth/client.ts`` 走 cookie + CSRF 流程，不再使用 Bearer。
 * - 持久化只保存 UI 展示字段（``userId`` / ``username`` / ``isAuthenticated``），
 *   这些字段不是认证令牌，不违反 AGENTS.md 的 Token 存储红线。
 * - 真实鉴权由后端 cookie 完成；若 cookie 过期，API 返回 401 时由调用方调用 ``logout``。
 */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface AuthState {
  userId: string | null
  username: string | null
  isAuthenticated: boolean
  login: (userId: string, username: string) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      userId: null,
      username: null,
      isAuthenticated: false,
      login: (userId, username) => {
        set({ userId, username, isAuthenticated: true })
      },
      logout: () => {
        set({ userId: null, username: null, isAuthenticated: false })
      },
    }),
    {
      name: 'yunhe-auth',
      partialize: (state) => ({
        userId: state.userId,
        username: state.username,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
)
