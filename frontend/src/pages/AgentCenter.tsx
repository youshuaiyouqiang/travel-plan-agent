import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Edit2, Trash2, ArrowLeft } from 'lucide-react'
import { fetchAgents, deleteCustomAgent, AgentInfo } from '../utils/api'

export function AgentCenter() {
  const navigate = useNavigate()
  const [agents, setAgents] = useState<{
    builtin: AgentInfo[]
    custom: AgentInfo[]
    public: AgentInfo[]
  }>({ builtin: [], custom: [], public: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchAgents()
      setAgents(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const handleUseAgent = (agentId: string) => {
    // 跳转到对话页，通过 query 参数指定智能体
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
              <button
                onClick={() => handleUseAgent(agent.id)}
                className="w-full bg-sky-500 text-white py-2 rounded-lg hover:bg-sky-600 transition-colors text-sm font-medium"
              >
                使用
              </button>
            </div>
          ))}
          <div className="border-2 border-dashed border-slate-300 rounded-lg p-4 flex flex-col items-center justify-center text-slate-400 hover:border-sky-400 hover:text-sky-500 transition-colors">
            <Plus size={32} className="mb-2" />
            <button
              onClick={() => navigate('/agents/create')}
              className="text-sky-500 font-medium text-sm"
            >
              创建自定义智能体
            </button>
          </div>
        </div>
      </div>

      {/* 我的智能体 */}
      {agents.custom.length > 0 && (
        <div className="mb-8">
          <h2 className="text-lg font-semibold mb-4 text-slate-700">我的智能体</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {agents.custom.map(agent => (
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
                <button
                  onClick={() => handleUseAgent(agent.id)}
                  className="w-full bg-sky-500 text-white py-2 rounded-lg hover:bg-sky-600 transition-colors text-sm font-medium"
                >
                  使用
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
