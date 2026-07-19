import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowLeft, MapPin, Calendar, Plane, Share2, X, Copy, Check, Eye } from 'lucide-react'
import { useItineraryStore } from '../hooks/useItineraryStore'
import { DayBlinds } from '../components/itinerary/DayBlinds'
import { ActivityDetail } from '../components/itinerary/ActivityDetail'
import { ItineraryMap } from '../components/itinerary/ItineraryMap'
import { createShareLink } from '../features/travel/api'

const PUBLIC_URL = import.meta.env.VITE_PUBLIC_URL || ''

function getShareBaseUrl(): string {
  if (PUBLIC_URL) return PUBLIC_URL
  return window.location.origin
}

/**
 * 旅行行程概览页（Task 3 简化版）。
 *
 * 业务红线（来源：plans/2026-07-17-travel-planning.md Task 3）：
 * - 移除花费统计、打卡进度、实际花费、相册等已下线能力。
 * - 保留行程基本信息（天数 / 活动数 / 预算 / 分享）。
 * - 不展示 actual_cost / checked_in 字段。
 */
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
    setSelectedDay,
    setDetailActivity,
  } = useItineraryStore()

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
              onClick={handleShare}
              className="w-9 h-9 rounded-xl bg-white/15 backdrop-blur-md flex items-center justify-center text-white/80 hover:bg-white/25 transition-colors"
              title="分享行程"
            >
              <Share2 size={17} />
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
          <div className="grid grid-cols-3 gap-2">
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
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-amber-400 to-amber-500 flex items-center justify-center mb-1.5">
                <span className="text-white text-[11px] font-bold">¥</span>
              </div>
              <p className="text-sm font-bold text-slate-800 leading-none truncate">
                {itinerary.budget || '¥0'}
              </p>
              <p className="text-[10px] text-slate-400 mt-0.5">预算</p>
            </div>
          </div>
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
            selectedIndex={selectedDayIndex}
            onSelectDay={setSelectedDay}
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
        destination={itinerary.destination}
      />

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
