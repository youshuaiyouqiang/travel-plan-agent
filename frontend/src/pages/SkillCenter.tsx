import { useEffect, useState } from 'react'
import { Wrench } from 'lucide-react'
import { fetchSkills, SkillInfo } from '../features/skill/api'

export function SkillCenter() {
  const [skills, setSkills] = useState<SkillInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeCategory, setActiveCategory] = useState<string>('all')

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const data = await fetchSkills()
        if (!cancelled) setSkills(data)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : '加载失败')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  const categories = ['all', ...new Set(skills.map(s => s.category || 'general'))]
  const filtered = activeCategory === 'all' ? skills : skills.filter(s => (s.category || 'general') === activeCategory)

  if (loading) return <div className="max-w-4xl mx-auto p-6 text-slate-400">加载中...</div>
  if (error) return <div className="max-w-4xl mx-auto p-6 text-red-600">{error}</div>

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="flex items-center gap-3 mb-6">
        <Wrench size={24} className="text-emerald-600" />
        <h1 className="text-2xl font-bold text-slate-800">Skill 中心</h1>
      </div>

      {/* 分类筛选 */}
      <div className="flex gap-2 mb-6 flex-wrap">
        {categories.map(cat => (
          <button
            key={cat}
            onClick={() => setActiveCategory(cat)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              activeCategory === cat
                ? 'bg-emerald-100 text-emerald-700'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            {cat === 'all' ? '全部' : cat}
          </button>
        ))}
      </div>

      {/* Skill 卡片列表 */}
      <div className="grid gap-4 md:grid-cols-2">
        {filtered.length === 0 && (
          <p className="text-slate-400 col-span-2 text-center py-8">暂无可用 Skill</p>
        )}
        {filtered.map(skill => (
          <div
            key={skill.name}
            className="border border-slate-200 rounded-xl p-4 hover:border-emerald-300 hover:shadow-sm transition-all"
          >
            <div className="flex items-start justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="text-xl">{skill.icon}</span>
                <span className="font-semibold text-slate-800">{skill.display_name}</span>
              </div>
              <span className={`text-xs px-2 py-0.5 rounded-full ${
                skill.env_configured
                  ? 'bg-green-100 text-green-700'
                  : 'bg-orange-100 text-orange-700'
              }`}>
                {skill.env_configured ? '已配置' : '未配置'}
              </span>
            </div>
            <p className="text-sm text-slate-500 mb-3">{skill.description}</p>
            {skill.tools && skill.tools.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {skill.tools.map(tool => (
                  <span key={tool} className="text-xs px-2 py-0.5 bg-slate-100 text-slate-600 rounded">
                    {tool}
                  </span>
                ))}
              </div>
            )}
            {skill.requires_env && skill.requires_env.length > 0 && (
              <div className="mt-2 text-xs text-slate-400">
                需要环境变量: {skill.requires_env.join(', ')}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
