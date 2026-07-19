import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { MapPin, LogIn, UserPlus } from 'lucide-react'
import { register, login } from '../utils/api'
import { useAuthStore } from '../hooks/useAuthStore'

export function LoginPage() {
  const [isRegister, setIsRegister] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const authLogin = useAuthStore((s) => s.login)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const navigate = useNavigate()

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/', { replace: true })
    }
  }, [isAuthenticated, navigate])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (!username.trim() || !password.trim()) {
      setError('请输入用户名和密码')
      return
    }
    setLoading(true)
    try {
      const result = isRegister
        ? await register(username.trim(), password)
        : await login(username.trim(), password)
      // P0-1: 登录响应体不再返回 token；浏览器凭据由后端 HttpOnly cookie 下发，
      // 前端不持有任何长期认证令牌。authLogin 仅记录 UI 展示态。
      authLogin(result.user_id, result.username)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : '操作失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-sky-50 to-indigo-100">
      <div className="w-full max-w-md px-6">
        <div className="text-center mb-8">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-sky-400 to-blue-500 flex items-center justify-center shadow-lg mx-auto mb-4">
            <MapPin size={28} className="text-white" />
          </div>
          <h1
            className="text-2xl font-bold text-slate-800"
            style={{ fontFamily: 'var(--font-display)' }}
          >
            云合
          </h1>
          <p className="text-sm text-slate-500 mt-1">AI 规划 · 实时搜索 · 一键保存行程</p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="bg-white rounded-2xl shadow-xl shadow-slate-200/50 p-8 space-y-5"
        >
          <h2 className="text-lg font-semibold text-slate-700 text-center">
            {isRegister ? '创建账号' : '欢迎回来'}
          </h2>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-600 text-sm rounded-lg px-4 py-2.5">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-slate-600 mb-1.5">用户名</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="请输入用户名"
              className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 transition-all"
              autoComplete="username"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-600 mb-1.5">密码</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="请输入密码"
              className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 transition-all"
              autoComplete={isRegister ? 'new-password' : 'current-password'}
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-500 to-sky-500 text-white font-medium py-3 text-sm hover:from-indigo-600 hover:to-sky-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-md shadow-indigo-200"
          >
            {isRegister ? <UserPlus size={16} /> : <LogIn size={16} />}
            {loading ? '处理中...' : isRegister ? '注册' : '登录'}
          </button>

          <p className="text-center text-sm text-slate-500">
            {isRegister ? '已有账号？' : '没有账号？'}
            <button
              type="button"
              onClick={() => {
                setIsRegister(!isRegister)
                setError('')
              }}
              className="text-indigo-500 hover:text-indigo-600 font-medium ml-1"
            >
              {isRegister ? '去登录' : '去注册'}
            </button>
          </p>
        </form>
      </div>
    </div>
  )
}
