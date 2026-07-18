import { motion, AnimatePresence } from 'framer-motion'
import { X, MapPin, Clock, Lightbulb, DollarSign, Navigation } from 'lucide-react'
import { ActivityData } from '../../features/travel/api'
import { MiniMap } from './MiniMap'

interface Props {
  activity: ActivityData | null
  onClose: () => void
  destination?: string
}

function InfoRow({ icon: Icon, label, value, iconBg, iconColor }: {
  icon: typeof MapPin
  label: string
  value: string
  iconBg: string
  iconColor: string
}) {
  return (
    <div className="flex items-start gap-3">
      <div className={`w-9 h-9 rounded-xl ${iconBg} flex items-center justify-center flex-shrink-0`}>
        <Icon size={16} className={iconColor} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-[11px] text-slate-400 mb-0.5 font-medium uppercase tracking-wide">{label}</p>
        <p className="text-sm text-slate-700 leading-relaxed">{value}</p>
      </div>
    </div>
  )
}

/**
 * 活动详情抽屉（Task 3 简化版）。
 *
 * 业务红线：移除打卡按钮、实际花费展示与花费输入 UI；仅展示预算费用、
 * 时间、地点、详情与小贴士。详情入口由 ItineraryOverview 触发。
 */
export function ActivityDetail({ activity, onClose, destination }: Props) {
  if (!activity) return null

  return (
    <AnimatePresence>
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
          <div className="flex justify-center pt-3 pb-1 flex-shrink-0">
            <div className="w-10 h-1 rounded-full bg-slate-200" />
          </div>

          <div className="px-5 pb-4 flex-shrink-0">
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <h2 className="text-lg font-bold text-slate-800 leading-tight">
                  {activity.title}
                </h2>
                {activity.location && (
                  <p className="text-xs text-slate-400 mt-1 flex items-center gap-1">
                    <MapPin size={11} />
                    {activity.location}
                  </p>
                )}
              </div>
              <button
                onClick={onClose}
                className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center text-slate-400 hover:bg-slate-200 transition-colors flex-shrink-0"
              >
                <X size={16} />
              </button>
            </div>
          </div>

          <div className="flex-1 min-h-0 overflow-y-auto px-5 pb-4 space-y-4">
            {activity.time_slot && (
              <InfoRow
                icon={Clock}
                label="时间"
                value={activity.time_slot}
                iconBg="bg-violet-50"
                iconColor="text-violet-500"
              />
            )}

            {activity.location && (
              <InfoRow
                icon={Navigation}
                label="地点"
                value={activity.location}
                iconBg="bg-sky-50"
                iconColor="text-sky-500"
              />
            )}

            {activity.location && (
              <MiniMap location={activity.location} title={activity.title} destination={destination} />
            )}

            {activity.cost > 0 && (
              <InfoRow
                icon={DollarSign}
                label="预算费用"
                value={`¥${activity.cost}`}
                iconBg="bg-amber-50"
                iconColor="text-amber-500"
              />
            )}

            {activity.description && (
              <div className="bg-slate-50/80 rounded-2xl p-4">
                <p className="text-xs text-slate-400 font-medium mb-1.5 uppercase tracking-wide">详情</p>
                <p className="text-sm text-slate-600 leading-relaxed whitespace-pre-line">
                  {activity.description}
                </p>
              </div>
            )}

            {activity.tips && (
              <div className="bg-emerald-50/60 rounded-2xl p-4 border border-emerald-100/50">
                <div className="flex items-center gap-2 mb-1.5">
                  <Lightbulb size={13} className="text-emerald-500" />
                  <p className="text-xs text-emerald-600 font-medium">小贴士</p>
                </div>
                <p className="text-sm text-emerald-700 leading-relaxed">{activity.tips}</p>
              </div>
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
