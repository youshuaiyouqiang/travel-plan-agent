import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowLeft, MapPin, Calendar, Wallet, CheckCircle2, Plane, Share2, BarChart3, TrendingDown, TrendingUp, Minus, X, Copy, Check, Eye, Camera } from 'lucide-react'
import { useItineraryStore } from '../hooks/useItineraryStore'
import { DayBlinds } from '../components/itinerary/DayBlinds'
import { ActivityDetail } from '../components/itinerary/ActivityDetail'
import { ItineraryMap } from '../components/itinerary/ItineraryMap'
import { getExpenseSummary, createShareLink, ExpenseSummary } from '../utils/api'

const PUBLIC_URL = import.meta.env.VITE_PUBLIC_URL || ''

function getShareBaseUrl(): string {
  if (PUBLIC_URL) return PUBLIC_URL
  return window.location.origin
}

export function ItineraryOverview() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const {
    itinerary,
    loading,
    error,
    selectedDayIndex,
    detailActivity,
    loadItinerary,
    checkIn,
    updateCost,
    removeActivity,
    setSelectedDay,
    setDetailActivity,
  } = useItineraryStore()

  const [showExpense, setShowExpense] = useState(false)
  const [expenseData, setExpenseData] = useState<ExpenseSummary | null>(null)
  const [showShare, setShowShare] = useState(false)
  const [shareToken, setShareToken] = useState('')
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (id) {
      loadItinerary(id)
    }
  }, [id, loadItinerary])

  const totalActivities = itinerary?.days?.reduce(
    (sum, d) => sum + d.activities.length,
    0,
  ) || 0

  const checkedCount = itinerary?.days?.reduce(
    (sum, d) => sum + d.activities.filter((a) => a.checked_in).length,
    0,
  ) || 0

  const progressPct = totalActivities > 0 ? Math.round((checkedCount / totalActivities) * 100) : 0

  const totalBudget = itinerary?.days?.reduce(
    (sum, d) => sum + d.activities.reduce((s, a) => s + a.cost, 0),
    0,
  ) || 0

  const totalActual = itinerary?.days?.reduce(
    (sum, d) => sum + d.activities.reduce((s, a) => s + a.actual_cost, 0),
    0,
  ) || 0

  const handleOpenExpense = async () => {
    if (!id) return
    try {
      const data = await getExpenseSummary(id)
      setExpenseData(data)
    } catch {
      setExpenseData(null)
    }
    setShowExpense(true)
  }

  const handleShare = async () => {
    if (!id) return
    try {
      const result = await createShareLink(id)
      setShareToken(result.token)
    } catch {
      return
    }
    setShowShare(true)
  }

  const handleCopyLink = () => {
    const url = `${getShareBaseUrl()}/shared/${shareToken}`
    navigator.clipboard.writeText(url).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center bg-gradient-to-br from-sky-50 via-white to-indigo-50">
        <motion.div
          className="text-center"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-sky-400 to-indigo-500 flex items-center justify-center mx-auto mb-4 shadow-lg shadow-sky-200/50">
            <Plane size={28} className="text-white" />
          </div>
          <p className="text-slate-400 text-sm">正在加载行程...</p>
          <div className="flex items-center justify-center gap-1.5 mt-3">
            <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-bounce" style={{ animationDelay: '0ms' }} />
            <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-bounce" style={{ animationDelay: '150ms' }} />
            <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-bounce" style={{ animationDelay: '300ms' }} />
          </div>
        </motion.div>
      </div>
    )
  }

  if (error || !itinerary) {
    return (
      <div className="h-screen flex items-center justify-center bg-gradient-to-br from-sky-50 via-white to-indigo-50">
        <motion.div
          className="text-center"
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
        >
          <div className="w-16 h-16 rounded-2xl bg-red-50 flex items-center justify-center mx-auto mb-4">
            <MapPin size={28} className="text-red-300" />
          </div>
          <p className="text-slate-500 mb-4">{error || '行程不存在'}</p>
          <button
            onClick={() => navigate('/')}
            className="px-6 py-2.5 bg-gradient-to-r from-sky-500 to-indigo-500 text-white rounded-xl text-sm font-medium hover:shadow-lg hover:shadow-sky-200/50 transition-all active:scale-95"
          >
            返回首页
          </button>
        </motion.div>
      </div>
    )
  }

  return (
    <div className="h-screen flex flex-col bg-slate-50">
      <div className="relative overflow-hidden flex-shrink-0">
        <div className="absolute inset-0 bg-gradient-to-br from-sky-500 via-indigo-500 to-violet-600" />
        <div className="absolute inset-0 opacity-10" style={{
          backgroundImage: `radial-gradient(circle at 20% 50%, white 1px, transparent 1px), radial-gradient(circle at 80% 20%, white 1px, transparent 1px), radial-gradient(circle at 50% 80%, white 1px, transparent 1px)`,
          backgroundSize: '60px 60px, 80px 80px, 70px 70px',
        }} />
        <div className="absolute bottom-0 left-0 right-0 h-16 bg-gradient-to-t from-slate-50 to-transparent" />

        <div className="relative px-5 pt-4 pb-8">
          <div className="flex items-center gap-3 mb-4">
            <button
              onClick={() => navigate('/')}
              className="w-9 h-9 rounded-xl bg-white/15 backdrop-blur-md flex items-center justify-center text-white/80 hover:bg-white/25 transition-colors"
            >
              <ArrowLeft size={18} />
            </button>
            <div className="flex-1" />
            <button
              onClick={handleOpenExpense}
              className="w-9 h-9 rounded-xl bg-white/15 backdrop-blur-md flex items-center justify-center text-white/80 hover:bg-white/25 transition-colors"
              title="花费统计"
            >
              <BarChart3 size={17} />
            </button>
            <button
              onClick={handleShare}
              className="w-9 h-9 rounded-xl bg-white/15 backdrop-blur-md flex items-center justify-center text-white/80 hover:bg-white/25 transition-colors"
              title="分享行程"
            >
              <Share2 size={17} />
            </button>
            <button
              onClick={() => navigate(`/album/${id}`)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/15 backdrop-blur-md text-white/80 hover:bg-white/25 transition-colors text-xs font-medium"
              title="旅行相册"
            >
              <Camera size={14} />
              相册
            </button>
            {itinerary.status && (
              <span className="px-3 py-1 rounded-full bg-white/15 backdrop-blur-md text-white/80 text-xs font-medium">
                {itinerary.status === 'draft' ? '草稿' : itinerary.status === 'confirmed' ? '已确认' : '已完成'}
              </span>
            )}
          </div>

          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
          >
            <h1 className="text-xl font-bold text-white leading-tight mb-1.5">
              {itinerary.title}
            </h1>
            <div className="flex items-center gap-3 text-white/60 text-xs">
              <span className="flex items-center gap-1">
                <MapPin size={11} />
                {itinerary.destination}
              </span>
              {(itinerary.start_date || itinerary.end_date) && (
                <span className="flex items-center gap-1">
                  <Calendar size={11} />
                  {itinerary.start_date} ~ {itinerary.end_date}
                </span>
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
          <div className="grid grid-cols-4 gap-2">
            <div className="bg-white/80 backdrop-blur-xl rounded-2xl p-3 shadow-sm border border-white/50">
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-sky-400 to-sky-500 flex items-center justify-center mb-1.5">
                <Calendar size={13} className="text-white" />
              </div>
              <p className="text-lg font-bold text-slate-800 leading-none">{itinerary.days?.length || 0}</p>
              <p className="text-[10px] text-slate-400 mt-0.5">天数</p>
            </div>
            <div className="bg-white/80 backdrop-blur-xl rounded-2xl p-3 shadow-sm border border-white/50">
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-violet-400 to-violet-500 flex items-center justify-center mb-1.5">
                <MapPin size={13} className="text-white" />
              </div>
              <p className="text-lg font-bold text-slate-800 leading-none">{totalActivities}</p>
              <p className="text-[10px] text-slate-400 mt-0.5">活动</p>
            </div>
            <div className="bg-white/80 backdrop-blur-xl rounded-2xl p-3 shadow-sm border border-white/50">
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-emerald-400 to-emerald-500 flex items-center justify-center mb-1.5">
                <CheckCircle2 size={13} className="text-white" />
              </div>
              <p className="text-lg font-bold text-slate-800 leading-none">{progressPct}%</p>
              <p className="text-[10px] text-slate-400 mt-0.5">打卡</p>
            </div>
            <div className="bg-white/80 backdrop-blur-xl rounded-2xl p-3 shadow-sm border border-white/50">
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-amber-400 to-amber-500 flex items-center justify-center mb-1.5">
                <Wallet size={13} className="text-white" />
              </div>
              {totalActual > 0 ? (
                <>
                  <p className="text-sm font-bold text-slate-800 leading-none">¥{totalActual.toFixed(0)}</p>
                  <p className="text-[10px] text-slate-400 mt-0.5">已花</p>
                </>
              ) : (
                <>
                  <p className="text-sm font-bold text-slate-800 leading-none truncate">{itinerary.budget || '¥0'}</p>
                  <p className="text-[10px] text-slate-400 mt-0.5">预算</p>
                </>
              )}
            </div>
          </div>

          {totalActivities > 0 && (
            <div className="mt-3 bg-white/80 backdrop-blur-xl rounded-xl p-3 shadow-sm border border-white/50">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs text-slate-500 font-medium">行程进度</span>
                <span className="text-xs text-slate-400">{checkedCount} / {totalActivities}</span>
              </div>
              <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                <motion.div
                  className="h-full rounded-full bg-gradient-to-r from-emerald-400 via-teal-400 to-sky-400"
                  initial={{ width: 0 }}
                  animate={{ width: `${progressPct}%` }}
                  transition={{ delay: 0.6, duration: 1, ease: 'easeOut' }}
                />
              </div>
              {totalActual > 0 && totalBudget > 0 && (
                <div className="mt-2 flex items-center justify-between">
                  <span className="text-[10px] text-slate-400">花费 ¥{totalActual.toFixed(0)} / ¥{totalBudget.toFixed(0)}</span>
                  <span className={`text-[10px] font-medium flex items-center gap-0.5 ${
                    totalActual <= totalBudget ? 'text-emerald-500' : 'text-red-500'
                  }`}>
                    {totalActual <= totalBudget ? <TrendingDown size={10} /> : <TrendingUp size={10} />}
                    {totalActual <= totalBudget
                      ? `节省 ¥${(totalBudget - totalActual).toFixed(0)}`
                      : `超支 ¥${(totalActual - totalBudget).toFixed(0)}`}
                  </span>
                </div>
              )}
            </div>
          )}
        </motion.div>
      </div>

      {itinerary.days && itinerary.days.length > 0 && (
        <ItineraryMap
          days={itinerary.days}
          selectedDayIndex={selectedDayIndex}
          onActivityClick={setDetailActivity}
          destination={itinerary.destination}
        />
      )}

      <div className="flex-1 min-h-0 mt-2">
        {itinerary.days && itinerary.days.length > 0 ? (
          <DayBlinds
            days={itinerary.days}
            itineraryId={itinerary.id}
            selectedIndex={selectedDayIndex}
            onSelectDay={setSelectedDay}
            onCheckIn={checkIn}
            onDelete={removeActivity}
            onActivityClick={setDetailActivity}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-slate-400 text-sm">
            暂无行程安排
          </div>
        )}
      </div>

      <ActivityDetail
        activity={detailActivity}
        onClose={() => setDetailActivity(null)}
        onCheckIn={checkIn}
        onUpdateCost={updateCost}
        destination={itinerary.destination}
      />

      <AnimatePresence>
        {showExpense && (
          <ExpensePanel
            data={expenseData}
            totalBudget={totalBudget}
            totalActual={totalActual}
            onClose={() => setShowExpense(false)}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {showShare && (
          <SharePanel
            token={shareToken}
            copied={copied}
            onCopy={handleCopyLink}
            onClose={() => { setShowShare(false); setCopied(false) }}
          />
        )}
      </AnimatePresence>
    </div>
  )
}

function ExpensePanel({ data, totalBudget, totalActual, onClose }: {
  data: ExpenseSummary | null
  totalBudget: number
  totalActual: number
  onClose: () => void
}) {
  const budget = data?.budget_total || totalBudget
  const actual = data?.actual_total || totalActual
  const remaining = data?.remaining ?? (budget - actual)
  const pct = budget > 0 ? Math.min((actual / budget) * 100, 100) : 0

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-end justify-center"
      onClick={onClose}
    >
      <motion.div
        initial={{ y: '100%' }}
        animate={{ y: 0 }}
        exit={{ y: '100%' }}
        transition={{ type: 'spring', damping: 28, stiffness: 300 }}
        className="bg-white w-full max-w-lg rounded-t-3xl max-h-[85vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-center pt-3 pb-1">
          <div className="w-10 h-1 rounded-full bg-slate-200" />
        </div>

        <div className="px-5 pb-4 flex items-center justify-between">
          <h2 className="text-lg font-bold text-slate-800">花费统计</h2>
          <button onClick={onClose} className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center text-slate-400 hover:bg-slate-200">
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto px-5 pb-6 space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-amber-50 rounded-2xl p-3 text-center">
              <p className="text-[10px] text-amber-500 font-medium mb-1">总预算</p>
              <p className="text-lg font-bold text-amber-600">¥{budget.toFixed(0)}</p>
            </div>
            <div className="bg-emerald-50 rounded-2xl p-3 text-center">
              <p className="text-[10px] text-emerald-500 font-medium mb-1">已花费</p>
              <p className="text-lg font-bold text-emerald-600">¥{actual.toFixed(0)}</p>
            </div>
            <div className={`rounded-2xl p-3 text-center ${remaining >= 0 ? 'bg-sky-50' : 'bg-red-50'}`}>
              <p className={`text-[10px] font-medium mb-1 ${remaining >= 0 ? 'text-sky-500' : 'text-red-500'}`}>
                {remaining >= 0 ? '剩余' : '超支'}
              </p>
              <p className={`text-lg font-bold ${remaining >= 0 ? 'text-sky-600' : 'text-red-600'}`}>
                ¥{Math.abs(remaining).toFixed(0)}
              </p>
            </div>
          </div>

          <div className="bg-slate-50 rounded-2xl p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-slate-500 font-medium">预算使用</span>
              <span className="text-xs text-slate-400">{pct.toFixed(0)}%</span>
            </div>
            <div className="h-3 bg-slate-200 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  pct <= 70 ? 'bg-gradient-to-r from-emerald-400 to-emerald-500' :
                  pct <= 90 ? 'bg-gradient-to-r from-amber-400 to-amber-500' :
                  'bg-gradient-to-r from-red-400 to-red-500'
                }`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>

          {data?.days.map((day) => (
            <div key={day.day_index} className="bg-white border border-slate-100 rounded-2xl p-4">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <p className="text-sm font-semibold text-slate-700">Day {day.day_index + 1}</p>
                  <p className="text-[10px] text-slate-400">{day.title}</p>
                </div>
                <div className="text-right">
                  <p className="text-xs text-slate-400">预算 ¥{day.budget.toFixed(0)}</p>
                  <p className={`text-sm font-bold ${day.actual <= day.budget ? 'text-emerald-600' : 'text-red-500'}`}>
                    实际 ¥{day.actual.toFixed(0)}
                  </p>
                </div>
              </div>
              <div className="space-y-2">
                {day.activities.map((act) => (
                  <div key={act.id} className="flex items-center justify-between py-1.5 border-t border-slate-50">
                    <div className="flex items-center gap-2">
                      <span className={`w-1.5 h-1.5 rounded-full ${act.checked_in ? 'bg-emerald-400' : 'bg-slate-200'}`} />
                      <span className="text-xs text-slate-600">{act.title}</span>
                    </div>
                    <div className="flex items-center gap-3 text-xs">
                      <span className="text-slate-400">¥{act.budget.toFixed(0)}</span>
                      {act.actual > 0 ? (
                        <span className={`font-medium ${act.actual <= act.budget ? 'text-emerald-600' : 'text-red-500'}`}>
                          ¥{act.actual.toFixed(0)}
                        </span>
                      ) : (
                        <span className="text-slate-300">-</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </motion.div>
    </motion.div>
  )
}

function SharePanel({ token, copied, onCopy, onClose }: {
  token: string
  copied: boolean
  onCopy: () => void
  onClose: () => void
}) {
  const shareUrl = `${getShareBaseUrl()}/shared/${token}`

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-end justify-center"
      onClick={onClose}
    >
      <motion.div
        initial={{ y: '100%' }}
        animate={{ y: 0 }}
        exit={{ y: '100%' }}
        transition={{ type: 'spring', damping: 28, stiffness: 300 }}
        className="bg-white w-full max-w-lg rounded-t-3xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-center pt-3 pb-1">
          <div className="w-10 h-1 rounded-full bg-slate-200" />
        </div>

        <div className="px-5 pb-4 flex items-center justify-between">
          <h2 className="text-lg font-bold text-slate-800">分享行程</h2>
          <button onClick={onClose} className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center text-slate-400 hover:bg-slate-200">
            <X size={16} />
          </button>
        </div>

        <div className="px-5 pb-8 space-y-4">
          <div className="bg-gradient-to-br from-sky-50 to-indigo-50 rounded-2xl p-5 text-center">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-sky-400 to-indigo-500 flex items-center justify-center mx-auto mb-3 shadow-lg shadow-sky-200/50">
              <Share2 size={24} className="text-white" />
            </div>
            <p className="text-sm text-slate-600 mb-1">分享链接已生成</p>
            <p className="text-xs text-slate-400">朋友无需登录即可查看行程</p>
          </div>

          <div className="bg-slate-50 rounded-xl p-3">
            <p className="text-[10px] text-slate-400 font-medium mb-1.5">分享链接</p>
            <div className="flex items-center gap-2">
              <input
                readOnly
                value={shareUrl}
                className="flex-1 bg-white border border-slate-200 rounded-lg px-3 py-2 text-xs text-slate-600 select-all"
              />
              <button
                onClick={onCopy}
                className={`px-4 py-2 rounded-lg text-xs font-medium transition-all ${
                  copied
                    ? 'bg-emerald-500 text-white'
                    : 'bg-sky-500 text-white hover:bg-sky-600'
                }`}
              >
                {copied ? (
                  <span className="flex items-center gap-1"><Check size={12} />已复制</span>
                ) : (
                  <span className="flex items-center gap-1"><Copy size={12} />复制</span>
                )}
              </button>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs text-slate-400">
            <Eye size={12} />
            <span>链接访问次数将被记录</span>
          </div>
        </div>
      </motion.div>
    </motion.div>
  )
}
