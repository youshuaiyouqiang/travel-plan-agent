/**
 * Task 3 — 旅行存档视图（不可变）。
 *
 * 业务红线（来源：plans/2026-07-17-travel-planning.md Task 3）：
 * - 已确认存档不可修改；继续编辑必须基于此存档创建新草稿。
 * - 不展示打卡、实际花费、相册等已下线能力。
 */
import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Lock, Sparkles, MapPin, Calendar } from 'lucide-react'
import { getTravelArchive, startDraftFromArchive, type TravelArchiveData } from '../features/travel/api'

export function TravelArchive() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [archive, setArchive] = useState<TravelArchiveData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    if (!id) return
    setLoading(true)
    setError('')
    getTravelArchive(id)
      .then(setArchive)
      .catch((e) => setError(e instanceof Error ? e.message : '存档不存在或无权访问'))
      .finally(() => setLoading(false))
  }, [id])

  const handleContinueEditing = async () => {
    if (!archive) return
    setCreating(true)
    try {
      const draft = await startDraftFromArchive(archive.id)
      // 跳转到草稿编辑器；当前复用 itinerary 路由占位，待草稿独立路由落地后切换。
      navigate(`/agent/travel/itinerary/${draft.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : '基于存档创建草稿失败')
    } finally {
      setCreating(false)
    }
  }

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center bg-slate-50">
        <p className="text-slate-400 text-sm">正在加载存档...</p>
      </div>
    )
  }

  if (error || !archive) {
    return (
      <div className="h-screen flex items-center justify-center bg-slate-50">
        <div className="text-center">
          <MapPin size={28} className="text-red-300 mx-auto mb-3" />
          <p className="text-slate-500 mb-4 text-sm">{error || '存档不存在'}</p>
          <button
            type="button"
            onClick={() => navigate('/')}
            className="px-5 py-2 rounded-lg bg-sky-500 text-white text-xs font-medium hover:bg-sky-600"
          >
            返回首页
          </button>
        </div>
      </div>
    )
  }

  const days = archive.plan.days ?? []

  return (
    <div className="h-screen flex flex-col bg-slate-50">
      <header className="flex-shrink-0 bg-gradient-to-br from-emerald-500 via-teal-500 to-sky-500 text-white">
        <div className="px-5 pt-4 pb-8">
          <div className="flex items-center gap-3 mb-4">
            <button
              type="button"
              onClick={() => navigate('/')}
              aria-label="返回"
              className="w-9 h-9 rounded-xl bg-white/15 backdrop-blur-md flex items-center justify-center text-white/80 hover:bg-white/25"
            >
              <ArrowLeft size={18} />
            </button>
            <div className="flex-1" />
            <span className="flex items-center gap-1 px-3 py-1 rounded-full bg-white/15 backdrop-blur-md text-white/80 text-[11px] font-medium">
              <Lock size={11} />
              不可变存档
            </span>
          </div>
          <h1 className="text-xl font-bold leading-tight mb-1.5">
            {archive.plan.title || '旅行存档'}
          </h1>
          <div className="flex items-center gap-3 text-white/70 text-xs">
            {archive.plan.destination && (
              <span className="flex items-center gap-1">
                <MapPin size={11} />
                {archive.plan.destination}
              </span>
            )}
            <span className="flex items-center gap-1">
              <Calendar size={11} />
              确认于 {archive.confirmed_at.slice(0, 10)}
            </span>
          </div>
        </div>
      </header>

      <div className="flex-1 min-h-0 overflow-y-auto px-5 py-4 space-y-3">
        {days.length === 0 && (
          <div className="text-center text-slate-400 text-sm py-12">存档为空</div>
        )}
        {days.map((day) => (
          <section
            key={day.day_index}
            className="bg-white rounded-2xl border border-slate-100 overflow-hidden"
          >
            <div className="px-4 py-3 border-b border-slate-100">
              <p className="text-sm font-semibold text-slate-700">
                Day {day.day_index}
                {day.title ? ` · ${day.title}` : ''}
              </p>
              {day.date && <p className="text-[10px] text-slate-400 mt-0.5">{day.date}</p>}
            </div>
            <ul className="divide-y divide-slate-50">
              {day.activities.map((activity) => (
                <li key={activity.id} className="px-4 py-3">
                  <p className="text-sm font-medium text-slate-800">{activity.title}</p>
                  <div className="flex items-center gap-3 mt-1 text-[11px] text-slate-400">
                    {activity.time_slot && <span>{activity.time_slot}</span>}
                    {activity.location && <span>{activity.location}</span>}
                  </div>
                  {activity.note && (
                    <p className="mt-1 text-xs text-slate-500">{activity.note}</p>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      <footer className="flex-shrink-0 px-5 py-4 bg-white border-t border-slate-100">
        <button
          type="button"
          onClick={handleContinueEditing}
          disabled={creating}
          className="w-full flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl bg-gradient-to-r from-sky-500 to-indigo-500 text-white text-sm font-medium hover:shadow-lg hover:shadow-sky-200/50 disabled:opacity-60 disabled:cursor-not-allowed"
        >
          <Sparkles size={14} />
          {creating ? '正在创建新草稿...' : '基于此存档继续编辑'}
        </button>
        <p className="text-[10px] text-slate-400 text-center mt-1.5">
          将复制存档内容到新草稿；原存档保持不变
        </p>
      </footer>
    </div>
  )
}
