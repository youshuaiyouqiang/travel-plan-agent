import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { MapPin, Calendar, Wallet, Navigation, Lightbulb, Share2, Plane } from 'lucide-react'
import { getSharedItinerary, ItineraryData } from '../features/travel/api'
import { SharedMap } from '../components/itinerary/SharedMap'

export function SharedItinerary() {
  const { token } = useParams<{ token: string }>()
  const navigate = useNavigate()
  const [itinerary, setItinerary] = useState<ItineraryData | null>(null)
  const [viewCount, setViewCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [expandedDay, setExpandedDay] = useState(0)

  useEffect(() => {
    if (!token) return
    getSharedItinerary(token)
      .then((data) => {
        setItinerary(data.itinerary)
        setViewCount(data.share_info.view_count)
      })
      .catch((e) => setError(e instanceof Error ? e.message : '加载失败'))
      .finally(() => setLoading(false))
  }, [token])

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center bg-gradient-to-br from-sky-50 via-white to-indigo-50">
        <div className="text-center">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-sky-400 to-indigo-500 flex items-center justify-center mx-auto mb-4 shadow-lg shadow-sky-200/50">
            <Plane size={28} className="text-white" />
          </div>
          <p className="text-slate-400 text-sm">正在加载行程...</p>
        </div>
      </div>
    )
  }

  if (error || !itinerary) {
    return (
      <div className="h-screen flex items-center justify-center bg-gradient-to-br from-sky-50 via-white to-indigo-50">
        <div className="text-center">
          <div className="w-16 h-16 rounded-2xl bg-red-50 flex items-center justify-center mx-auto mb-4">
            <Share2 size={28} className="text-red-300" />
          </div>
          <p className="text-slate-500 mb-4">{error || '分享链接无效'}</p>
          <button
            onClick={() => navigate('/')}
            className="px-6 py-2.5 bg-gradient-to-r from-sky-500 to-indigo-500 text-white rounded-xl text-sm font-medium"
          >
            返回首页
          </button>
        </div>
      </div>
    )
  }

  const totalActivities = itinerary.days?.reduce((s, d) => s + d.activities.length, 0) || 0
  const totalBudget = itinerary.days?.reduce((s, d) => s + d.activities.reduce((a, act) => a + act.cost, 0), 0) || 0

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-sky-500 via-indigo-500 to-violet-600" />
        <div className="absolute inset-0 opacity-10" style={{
          backgroundImage: `radial-gradient(circle at 20% 50%, white 1px, transparent 1px), radial-gradient(circle at 80% 20%, white 1px, transparent 1px)`,
          backgroundSize: '60px 60px, 80px 80px',
        }} />
        <div className="absolute bottom-0 left-0 right-0 h-16 bg-gradient-to-t from-slate-50 to-transparent" />

        <div className="relative px-5 pt-6 pb-10">
          <div className="flex items-center gap-2 mb-3">
            <span className="px-2.5 py-1 rounded-full bg-white/15 backdrop-blur-md text-white/70 text-[10px] font-medium flex items-center gap-1">
              <Share2 size={10} />
              分享行程
            </span>
          </div>
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <h1 className="text-2xl font-bold text-white leading-tight mb-2">
              {itinerary.title}
            </h1>
            <div className="flex items-center gap-4 text-white/60 text-xs">
              <span className="flex items-center gap-1"><MapPin size={11} />{itinerary.destination}</span>
              {itinerary.start_date && (
                <span className="flex items-center gap-1"><Calendar size={11} />{itinerary.start_date} ~ {itinerary.end_date}</span>
              )}
            </div>
          </motion.div>
        </div>

        <motion.div
          className="relative px-5 -mt-2"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <div className="grid grid-cols-3 gap-2">
            <div className="bg-white/80 backdrop-blur-xl rounded-2xl p-3 shadow-sm border border-white/50 text-center">
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-sky-400 to-sky-500 flex items-center justify-center mx-auto mb-1.5">
                <Calendar size={13} className="text-white" />
              </div>
              <p className="text-lg font-bold text-slate-800">{itinerary.days?.length || 0}</p>
              <p className="text-[10px] text-slate-400">天数</p>
            </div>
            <div className="bg-white/80 backdrop-blur-xl rounded-2xl p-3 shadow-sm border border-white/50 text-center">
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-violet-400 to-violet-500 flex items-center justify-center mx-auto mb-1.5">
                <MapPin size={13} className="text-white" />
              </div>
              <p className="text-lg font-bold text-slate-800">{totalActivities}</p>
              <p className="text-[10px] text-slate-400">活动</p>
            </div>
            <div className="bg-white/80 backdrop-blur-xl rounded-2xl p-3 shadow-sm border border-white/50 text-center">
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-amber-400 to-amber-500 flex items-center justify-center mx-auto mb-1.5">
                <Wallet size={13} className="text-white" />
              </div>
              <p className="text-sm font-bold text-slate-800">{totalBudget > 0 ? `¥${totalBudget.toFixed(0)}` : itinerary.budget || '-'}</p>
              <p className="text-[10px] text-slate-400">预算</p>
            </div>
          </div>
        </motion.div>
      </div>

      {itinerary.days && itinerary.days.length > 0 && (
        <SharedMap days={itinerary.days} destination={itinerary.destination} />
      )}

      <div className="px-4 py-4 space-y-3">
        {itinerary.days?.map((day, di) => (
          <div key={di} className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
            <button
              onClick={() => setExpandedDay(expandedDay === di ? -1 : di)}
              className="w-full px-4 py-3 flex items-center justify-between"
            >
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-sky-400 to-indigo-500 flex items-center justify-center">
                  <span className="text-xs font-bold text-white">{di + 1}</span>
                </div>
                <div className="text-left">
                  <p className="text-sm font-semibold text-slate-700">Day {di + 1}</p>
                  {day.title && <p className="text-[10px] text-slate-400">{day.title}</p>}
                </div>
              </div>
              <span className="text-xs text-slate-300">{day.activities.length} 项</span>
            </button>

            {expandedDay === di && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                className="border-t border-slate-50"
              >
                <div className="p-4 space-y-3">
                  {day.activities.map((act, ai) => (
                    <div key={ai} className="flex gap-3">
                      <div className="flex flex-col items-center w-6 flex-shrink-0 pt-0.5">
                        <div className="w-2 h-2 rounded-full bg-sky-400" />
                        {ai < day.activities.length - 1 && (
                          <div className="w-0.5 flex-1 bg-slate-100 mt-1" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0 pb-2">
                        <div className="flex items-center gap-2">
                          {act.time_slot && (
                            <span className="text-[10px] text-slate-300">{act.time_slot}</span>
                          )}
                          <p className="text-sm font-medium text-slate-700">{act.title}</p>
                        </div>
                        {act.location && (
                          <p className="text-xs text-slate-400 mt-0.5 flex items-center gap-1">
                            <Navigation size={9} />{act.location}
                          </p>
                        )}
                        {act.description && (
                          <p className="text-xs text-slate-500 mt-1">{act.description}</p>
                        )}
                        {act.cost > 0 && (
                          <p className="text-xs text-amber-500 mt-1 flex items-center gap-1">
                            <Wallet size={9} />¥{act.cost}
                          </p>
                        )}
                        {act.tips && (
                          <div className="mt-1.5 flex items-start gap-1.5">
                            <Lightbulb size={10} className="text-emerald-400 flex-shrink-0 mt-0.5" />
                            <p className="text-[11px] text-emerald-600">{act.tips}</p>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}
          </div>
        ))}
      </div>

      <div className="text-center py-6 text-xs text-slate-300">
        已被查看 {viewCount} 次
      </div>
    </div>
  )
}
