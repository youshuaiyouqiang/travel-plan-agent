import { useEffect, useState } from 'react'
import { useNavigate, useParams, useLocation } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { fetchSkills, fetchAgents, fetchMCPServers, createCustomAgent, updateCustomAgent, SkillInfo, MCPServerInfo } from '../utils/api'

export function AgentEditor() {
  const navigate = useNavigate()
  const { agentId } = useParams()
  const location = useLocation()
  const isEdit = location.pathname.startsWith('/agents/edit/')
  const isView = location.pathname.startsWith('/agents/view/')

  const [form, setForm] = useState({
    name: '',
    description: '',
    icon: '🤖',
    system_prompt: '',
    skills: [] as string[],
    mcp_servers: [] as string[],
    welcome_message: '',
    temperature: 0.7,
    is_public: false,
  })

  const [skills, setSkills] = useState<SkillInfo[]>([])
  const [mcpServers, setMcpServers] = useState<MCPServerInfo[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [initLoading, setInitLoading] = useState(true)
  const [originalSource, setOriginalSource] = useState<'builtin' | 'custom' | null>(null)

  useEffect(() => {
    let cancelled = false
    const init = async () => {
      try {
        const [skillsData, mcpData] = await Promise.all([
          fetchSkills(),
          fetchMCPServers(),
        ])
        if (cancelled) return
        setSkills(skillsData)
        setMcpServers(mcpData)
        if ((isEdit || isView) && agentId) {
          // 编辑/查看模式：加载智能体数据（包括内置智能体）
          const data = await fetchAgents()
          if (cancelled) return
          const all = [...data.builtin, ...data.custom, ...data.public]
          const existing = all.find(a => a.id === agentId)
          if (existing) {
            setOriginalSource(existing.source || 'custom')
            setForm({
              name: existing.name || '',
              description: existing.description || '',
              icon: existing.icon || '🤖',
              system_prompt: existing.system_prompt || '',
              skills: existing.skills || [],
              mcp_servers: existing.mcp_servers || [],
              welcome_message: existing.welcome_message || '',
              temperature: existing.temperature ?? 0.7,
              is_public: existing.is_public ?? false,
            })
          } else {
            setError('智能体不存在')
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : '加载失败')
        }
      } finally {
        if (!cancelled) setInitLoading(false)
      }
    }
    init()
    return () => { cancelled = true }
  }, [agentId, isEdit, isView])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      if (isEdit && agentId && originalSource === 'custom') {
        // 编辑自定义智能体：直接更新
        await updateCustomAgent(agentId, form)
      } else if (isEdit && agentId && originalSource === 'builtin') {
        // 编辑内置智能体：另存为新的自定义智能体
        if (!confirm('内置智能体不可直接修改，将基于当前配置创建一个新的自定义智能体副本，是否继续？')) {
          setLoading(false)
          return
        }
        await createCustomAgent({
          ...form,
          name: `${form.name}（自定义）`,
        })
      } else {
        // 创建新智能体
        await createCustomAgent(form)
      }
      navigate('/agents')
    } catch (err) {
      setError(err instanceof Error ? err.message : (isEdit ? '保存失败' : '创建失败'))
    } finally {
      setLoading(false)
    }
  }

  const toggleSkill = (skillName: string) => {
    setForm(prev => ({
      ...prev,
      skills: prev.skills.includes(skillName)
        ? prev.skills.filter(s => s !== skillName)
        : [...prev.skills, skillName],
    }))
  }

  const toggleMCP = (serverId: string) => {
    setForm(prev => ({
      ...prev,
      mcp_servers: prev.mcp_servers.includes(serverId)
        ? prev.mcp_servers.filter(s => s !== serverId)
        : [...prev.mcp_servers, serverId],
    }))
  }

  if (initLoading) {
    return <div className="max-w-2xl mx-auto p-6 text-slate-400">加载中...</div>
  }

  if (error && !form.name && !isEdit) {
    return <div className="max-w-2xl mx-auto p-6 text-red-600">{error}</div>
  }

  return (
    <div className="max-w-2xl mx-auto p-6">
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => navigate('/agents')}
          className="p-2 rounded-xl hover:bg-slate-100 transition-colors"
          title="返回"
        >
          <ArrowLeft size={20} className="text-slate-600" />
        </button>
        <h1 className="text-2xl font-bold text-slate-800">
          {isView ? '智能体详情' : isEdit ? '编辑智能体' : '创建智能体'}
        </h1>
        {isEdit && originalSource === 'builtin' && (
          <span className="ml-2 text-xs px-2 py-1 bg-amber-100 text-amber-700 rounded-full">
            内置 · 保存将创建副本
          </span>
        )}
      </div>

      {error && (
        <div className="mb-4 px-4 py-2 rounded-lg bg-red-50 text-red-600 text-sm">{error}</div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* 基本信息 */}
        <div>
          <label className="block text-sm font-medium mb-2 text-slate-700">图标</label>
          <input
            type="text"
            value={form.icon}
            onChange={e => setForm({ ...form, icon: e.target.value })}
            disabled={isView}
            className="w-20 px-3 py-2 border border-slate-300 rounded-lg disabled:bg-slate-50 disabled:text-slate-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2 text-slate-700">名称</label>
          <input
            type="text"
            value={form.name}
            onChange={e => setForm({ ...form, name: e.target.value })}
            disabled={isView}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg disabled:bg-slate-50 disabled:text-slate-500"
            required={!isView}
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2 text-slate-700">描述</label>
          <textarea
            value={form.description}
            onChange={e => setForm({ ...form, description: e.target.value })}
            disabled={isView}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg disabled:bg-slate-50 disabled:text-slate-500"
            rows={3}
            required={!isView}
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2 text-slate-700">系统提示词</label>
          <textarea
            value={form.system_prompt}
            onChange={e => setForm({ ...form, system_prompt: e.target.value })}
            disabled={isView}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg font-mono text-sm disabled:bg-slate-50 disabled:text-slate-500"
            rows={6}
            required={!isView}
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2 text-slate-700">温度 (0-1)</label>
          <input
            type="range"
            min="0"
            max="1"
            step="0.1"
            value={form.temperature}
            onChange={e => setForm({ ...form, temperature: parseFloat(e.target.value) })}
            disabled={isView}
            className="w-full disabled:opacity-50"
          />
          <span className="text-sm text-slate-500">{form.temperature}</span>
        </div>

        {/* Skill 选择器 */}
        <div>
          <label className="block text-sm font-medium mb-2 text-slate-700">
            {isView ? '已配置 Skill' : '选择 Skill'}
          </label>
          <div className="space-y-2">
            {skills.length === 0 && (
              <p className="text-sm text-slate-400">暂无可用 Skill</p>
            )}
            {skills.map(skill => {
              const isSelected = form.skills.includes(skill.name)
              if (isView && !isSelected) return null  // 查看模式只显示已选中的
              return (
                <div
                  key={skill.name}
                  className={`border rounded-lg p-3 transition-colors ${
                    isSelected ? 'border-sky-500 bg-sky-50' : 'border-slate-200 hover:border-slate-300'
                  } ${isView ? '' : 'cursor-pointer'}`}
                  onClick={() => { if (!isView) toggleSkill(skill.name) }}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-slate-800 flex items-center gap-1.5">
                        <span>{skill.icon}</span>
                        {skill.display_name}
                      </div>
                      <div className="text-sm text-slate-500 mt-0.5">{skill.description}</div>
                    </div>
                    <div className="text-sm flex-shrink-0 ml-2">
                      {skill.requires_env.length > 0 && (
                        <span className={skill.env_configured ? 'text-green-600' : 'text-orange-600'}>
                          {skill.env_configured ? '✓ 已配置' : '⚠ 未配置'}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* MCP 选择器 */}
        <div>
          <label className="block text-sm font-medium mb-2 text-slate-700">
            {isView ? '已配置 MCP 服务' : '选择 MCP 服务'}
          </label>
          <div className="space-y-2">
            {mcpServers.length === 0 && (
              <p className="text-sm text-slate-400">暂无可用 MCP 服务</p>
            )}
            {mcpServers.map(server => {
              const hasAdapter = server.tools.some(t => t.adapter_available)
              const isSelected = form.mcp_servers.includes(server.identifier)
              if (isView && !isSelected) return null  // 查看模式只显示已选中的
              return (
                <div
                  key={server.identifier}
                  className={`border rounded-lg p-3 transition-colors ${
                    isSelected
                      ? 'border-amber-500 bg-amber-50'
                      : hasAdapter
                        ? 'border-slate-200 hover:border-slate-300'
                        : 'border-slate-100 bg-slate-50 opacity-60'
                  } ${isView ? '' : (hasAdapter ? 'cursor-pointer' : 'cursor-not-allowed')}`}
                  onClick={() => {
                    if (!isView && hasAdapter) toggleMCP(server.identifier)
                  }}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-slate-800">{server.name}</div>
                      <div className="text-sm text-slate-500 mt-0.5">{server.description}</div>
                      <div className="flex flex-wrap gap-1 mt-1.5">
                        {server.tools.map(tool => (
                          <span
                            key={tool.proxy_name}
                            className={`text-xs px-1.5 py-0.5 rounded font-mono ${
                              tool.adapter_available
                                ? 'bg-green-50 text-green-700'
                                : 'bg-slate-100 text-slate-400'
                            }`}
                          >
                            {tool.name}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="text-sm flex-shrink-0 ml-2">
                      <span className={hasAdapter ? 'text-green-600' : 'text-orange-600'}>
                        {hasAdapter ? '可用' : '未安装'}
                      </span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* 公开设置 — 查看模式隐藏 */}
        {!isView && (
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="is_public"
              checked={form.is_public}
              onChange={e => setForm({ ...form, is_public: e.target.checked })}
              className="w-4 h-4"
            />
            <label htmlFor="is_public" className="text-sm text-slate-700">公开到社区</label>
          </div>
        )}

        {/* 操作按钮 */}
        {isView ? (
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => navigate('/agents')}
              className="flex-1 bg-slate-100 text-slate-700 py-3 rounded-lg font-medium hover:bg-slate-200 transition-colors"
            >
              返回
            </button>
            <button
              type="button"
              onClick={() => navigate(`/?agent=${agentId}`)}
              className="flex-1 bg-sky-500 text-white py-3 rounded-lg font-medium hover:bg-sky-600 transition-colors"
            >
              使用该智能体
            </button>
          </div>
        ) : (
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-sky-500 text-white py-3 rounded-lg font-medium hover:bg-sky-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? '处理中...' : (isEdit && originalSource === 'builtin' ? '另存为自定义智能体' : isEdit ? '保存' : '创建')}
          </button>
        )}
      </form>
    </div>
  )
}
