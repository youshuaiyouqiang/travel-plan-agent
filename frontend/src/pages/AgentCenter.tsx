import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Edit2, Trash2, ArrowLeft, Copy } from 'lucide-react'
import { fetchAgents, deleteCustomAgent, cloneCustomAgent, AgentInfo } from '../features/agent/api'
import { useAuthStore } from '../hooks/useAuthStore'
import { isApiError } from '../features/auth/errors'

export function AgentCenter() {
  const navigate = useNavigate()
  const [agents, setAgents] = useState<{
    builtin: AgentInfo[]
    custom: AgentInfo[]
    public: AgentInfo[]
  }>({ builtin: [], custom: [], public: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const logout = useAuthStore((s) => s.logout)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchAgents()
      setAgents(data)
    } catch (err) {
      // 401 鉴权过期：调用 logout 让 PrivateRoute 把用户踢回 /login
      if (isApiError(err) && err.status === 401) {
        logout()
        setError('登录已过期，请重新登录')
        return
      }
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const handleUseAgent = (agentId: string) => {
    navigate(`/?agent=${encodeURIComponent(agentId)}`)
  }

  const handleDelete = async (agentId: string) => {
    if (!confirm('确定删除这个智能体？')) return
    try {
      await deleteCustomAgent(agentId)
      await load()
    } catch (err) {
      alert(err instanceof Error ? err.message : '删除失败')
    }
  }

  const handleClone = async (agentId: string) => {
    try {
      await cloneCustomAgent(agentId)
      alert('克隆成功！已添加到"我的智能体"（草稿状态）')
      await load()
    } catch (err) {
      alert(err instanceof Error ? err.message : '克隆失败')
    }
  }

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto p-6 text-slate-400">加载中...</div>
    )
  }

  if (error) {
    return (
      <div className="max-w-4xl mx-auto p-6 text-red-600">{error}</div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => navigate('/')}
          className="p-2 rounded-xl hover:bg-slate-100 transition-colors"
          title="返回"
        >
          <ArrowLeft size={20} className="text-slate-600" />
        </button>
        <h1 className="text-2xl font-bold text-slate-800">Agent 中心</h1>
      </div>

      {/* 内置智能体 */}
      <div className="mb-8">
        <h2 className="text-lg font-semibold mb-4 text-slate-700">内置智能体</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {agents.builtin.map(agent => (
            <div key={agent.id} className="border border-slate-200 rounded-lg p-4 bg-white hover:shadow-md transition-shadow">
              <div className="text-4xl mb-2">{agent.icon}</div>
              <h3 className="font-semibold text-slate-800">{agent.name}</h3>
              <p className="text-sm text-slate-500 mb-3 line-clamp-2">{agent.description}</p>
              <div className="flex gap-2">
                <button
                  onClick={() => handleUseAgent(agent.id)}
                  className="flex-1 bg-sky-500 text-white py-2 rounded-lg hover:bg-sky-600 transition-colors text-sm font-medium"
                >
                  使用
                </button>
                <button
                  onClick={() => navigate(`/agents/edit/${agent.id}`)}
                  className="px-3 py-2 border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors text-sm text-slate-600"
                >
                  编辑
                </button>
              </div>
            </div>
          ))}
          <button
            onClick={() => navigate('/agents/create')}
            className="border-2 border-dashed border-slate-300 rounded-lg p-4 flex flex-col items-center justify-center text-slate-400 hover:border-sky-400 hover:text-sky-500 transition-colors"
          >
            <Plus size={32} className="mb-2" />
            <span className="text-sky-500 font-medium text-sm">创建自定义智能体</span>
          </button>
        </div>
      </div>

      {/* 我的智能体 */}
      {agents.custom.length > 0 && (
        <div className="mb-8">
          <h2 className="text-lg font-semibold mb-4 text-slate-700">我的智能体</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {agents.custom.map(agent => (
              <div key={agent.id} className="border border-slate-200 rounded-lg p-4 bg-white hover:shadow-md transition-shadow">
                <div className="flex items-start justify-between mb-2">
                  <div className="text-4xl">{agent.icon}</div>
                  {agent.status === 'draft' && (
                    <span className="text-xs px-2 py-0.5 bg-amber-100 text-amber-700 rounded-full">草稿</span>
                  )}
                </div>
                <h3 className="font-semibold text-slate-800">{agent.name}</h3>
                <p className="text-sm text-slate-500 mb-3 line-clamp-2">{agent.description}</p>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleUseAgent(agent.id)}
                    className="flex-1 bg-sky-500 text-white py-2 rounded-lg hover:bg-sky-600 transition-colors text-sm font-medium"
                  >
                    使用
                  </button>
                  <button
                    onClick={() => navigate(`/agents/edit/${agent.id}`)}
                    className="p-2 border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors"
                    title="编辑"
                  >
                    <Edit2 size={16} className="text-slate-600" />
                  </button>
                  <button
                    onClick={() => handleDelete(agent.id)}
                    className="p-2 border border-slate-200 rounded-lg hover:bg-red-50 text-red-500 transition-colors"
                    title="删除"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 社区智能体 */}
      {agents.public.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-4 text-slate-700">社区智能体</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {agents.public.map(agent => (
              <div key={agent.id} className="border border-slate-200 rounded-lg p-4 bg-white hover:shadow-md transition-shadow">
                <div className="text-4xl mb-2">{agent.icon}</div>
                <h3 className="font-semibold text-slate-800">{agent.name}</h3>
                <p className="text-sm text-slate-500 mb-3 line-clamp-2">{agent.description}</p>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleUseAgent(agent.id)}
                    className="flex-1 bg-sky-500 text-white py-2 rounded-lg hover:bg-sky-600 transition-colors text-sm font-medium"
                  >
                    使用
                  </button>
                  <button
                    onClick={() => handleClone(agent.id)}
                    className="flex-1 bg-emerald-50 text-emerald-600 py-2 rounded-lg hover:bg-emerald-100 transition-colors text-sm font-medium flex items-center justify-center gap-1"
                    title="克隆到我的工作区"
                  >
                    <Copy size={14} />
                    克隆
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
