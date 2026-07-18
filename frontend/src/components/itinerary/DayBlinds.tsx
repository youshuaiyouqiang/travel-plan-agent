import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { MapPin, Clock, CheckCircle2, ChevronRight, Camera, Utensils, Bus, Landmark, ShoppingBag, Music, Coffee, Moon, Sun } from 'lucide-react'
import { DayPlanData, ActivityData } from '../../features/travel/api'

interface Props {
  days: DayPlanData[]
  itineraryId: string
  selectedIndex: number
  onSelectDay: (index: number) => void
  onDelete: (activityId: number) => void
  onActivityClick: (activity: ActivityData) => void
}

const _CATEGORY_ICONS: Record<string, typeof Camera> = {
  eat: Utensils,
  food: Utensils,
  restaurant: Utensils,
  transport: Bus,
  bus: Bus,
  train: Bus,
  flight: Bus,
  attraction: Landmark,
  scenic: Landmark,
  museum: Landmark,
  shop: ShoppingBag,
  shopping: ShoppingBag,
  entertain: Music,
  show: Music,
  cafe: Coffee,
  coffee: Coffee,
  bar: Moon,
  nightlife: Moon,
  hotel: Moon,
  photo: Camera,
  default: MapPin,
}

const _CATEGORY_COLORS: Record<string, string> = {
  eat: 'from-orange-400 to-red-400',
  food: 'from-orange-400 to-red-400',
  restaurant: 'from-orange-400 to-red-400',
  transport: 'from-sky-400 to-blue-400',
  bus: 'from-sky-400 to-blue-400',
  train: 'from-sky-400 to-blue-400',
  attraction: 'from-violet-400 to-purple-400',
  scenic: 'from-violet-400 to-purple-400',
  museum: 'from-violet-400 to-purple-400',
  shop: 'from-pink-400 to-rose-400',
  shopping: 'from-pink-400 to-rose-400',
  entertain: 'from-amber-400 to-yellow-400',
  show: 'from-amber-400 to-yellow-400',
  cafe: 'from-amber-600 to-yellow-700',
  coffee: 'from-amber-600 to-yellow-700',
  hotel: 'from-indigo-400 to-blue-500',
  default: 'from-teal-400 to-emerald-400',
}

function _guessCategory(title: string): string {
  const t = title.toLowerCase()
  if (/吃|餐|饭|面|火锅|烧烤|小吃|美食|饮|茶|coffee|cafe|restaurant|eat|food/.test(t)) return 'eat'
  if (/车|地铁|公交|出租|飞机|高铁|火车|bus|train|taxi|flight|transport/.test(t)) return 'transport'
  if (/景点|公园|博物馆|寺|塔|古城|长城|故宫|attraction|scenic|museum|temple/.test(t)) return 'attraction'
  if (/买|购|商场|市场|shop|shopping|mall|market/.test(t)) return 'shop'
  if (/表演|演出|娱乐|show|entertain|bar|club/.test(t)) return 'entertain'
  if (/咖啡|茶馆|coffee|cafe/.test(t)) return 'cafe'
  if (/酒店|民宿|住宿|hotel|hostel|inn/.test(t)) return 'hotel'
  return 'default'
}

function TimelineActivity({
  activity,
  index,
  isLast,
  onClick,
}: {
  activity: ActivityData
  index: number
  isLast: boolean
  onClick: (act: ActivityData) => void
}) {
  const category = _guessCategory(activity.title + ' ' + (activity.location || ''))
  const Icon = _CATEGORY_ICONS[category] || MapPin
  const gradient = _CATEGORY_COLORS[category] || _CATEGORY_COLORS.default
  const timeLabel = activity.time_slot || ''

  return (
    <motion.div
      initial={{ opacity: 0, x: -16 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{
        delay: index * 0.06,
        duration: 0.4,
        ease: [0.25, 0.46, 0.45, 0.94],
      }}
      className="flex gap-3"
    >
      {/* Timeline Left Rail */}
      <div className="flex flex-col items-center w-10 flex-shrink-0 pt-0.5">
        <div className={`w-8 h-8 rounded-xl bg-gradient-to-br ${gradient} flex items-center justify-center shadow-sm ${activity.checked_in ? 'ring-2 ring-emerald-300 ring-offset-1' : ''}`}>
          <Icon size={14} className="text-white" />
        </div>
        {!isLast && (
          <div className="w-0.5 flex-1 bg-gradient-to-b from-slate-200 to-slate-100 mt-1" />
        )}
      </div>

      {/* Activity Card */}
      <div
        onClick={() => onClick(activity)}
        className={`
          flex-1 mb-3 rounded-2xl cursor-pointer transition-all duration-200 active:scale-[0.98]
          bg-white shadow-sm border border-slate-100
          hover:shadow-md hover:border-slate-200
          ${activity.checked_in ? 'border-emerald-100 bg-emerald-50/30' : ''}
        `}
      >
        <div className="px-3.5 py-3">
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <h3 className={`text-sm font-semibold truncate ${activity.checked_in ? 'text-emerald-700' : 'text-slate-800'}`}>
                  {activity.title}
                </h3>
                {activity.checked_in && (
                  <CheckCircle2 size={14} className="text-emerald-500 flex-shrink-0" />
                )}
              </div>
              {activity.location && (
                <p className="text-xs text-slate-400 mt-0.5 flex items-center gap-1 truncate">
                  <MapPin size={10} className="flex-shrink-0" />
                  {activity.location}
                </p>
              )}
            </div>
            <ChevronRight size={14} className="text-slate-300 flex-shrink-0 mt-1" />
          </div>

          <div className="flex items-center gap-2.5 mt-2">
            {timeLabel && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-slate-50 text-[11px] text-slate-500 font-medium">
                <Clock size={10} />
                {timeLabel}
              </span>
            )}
            {activity.cost > 0 && (
              <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-amber-50 text-[11px] text-amber-600 font-medium">
                ¥{activity.cost}
              </span>
            )}
          </div>

          {activity.description && (
            <p className="text-xs text-slate-400 mt-1.5 line-clamp-2 leading-relaxed">
              {activity.description}
            </p>
          )}
        </div>
      </div>
    </motion.div>
  )
}

export function DayBlinds({
  days,
  itineraryId,
  selectedIndex,
  onSelectDay,
  onDelete,
  onActivityClick,
}: Props) {
  const [animKey, setAnimKey] = useState(0)

  useEffect(() => {
    setAnimKey((k) => k + 1)
  }, [selectedIndex])

  if (!days.length) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-400">
        暂无行程安排
      </div>
    )
  }

  const day = days[selectedIndex]
  const activities = day?.activities || []

  return (
    <div className="flex flex-col h-full">
      {/* Day Selector */}
      <div className="px-4 py-2.5 flex-shrink-0">
        <div className="flex items-center gap-1.5 overflow-x-auto scrollbar-none">
          {days.map((d, idx) => {
            const isActive = idx === selectedIndex
            const actCount = d.activities?.length || 0
            const checkedInCount = d.activities?.filter(a => a.checked_in).length || 0

            return (
              <button
                key={d.id}
                onClick={() => onSelectDay(idx)}
                className={`
                  flex-shrink-0 rounded-2xl px-4 py-2 transition-all duration-200
                  ${isActive
                    ? 'bg-gradient-to-br from-sky-500 to-indigo-500 text-white shadow-md shadow-sky-200/40'
                    : 'bg-white text-slate-600 border border-slate-150 hover:border-sky-200 hover:bg-sky-50/50'
                  }
                `}
              >
                <div className={`text-[10px] font-medium ${isActive ? 'text-white/70' : 'text-slate-400'}`}>
                  Day {idx + 1}
                </div>
                <div className="text-sm font-semibold truncate max-w-[72px] leading-tight">
                  {d.title || `第${idx + 1}天`}
                </div>
                {actCount > 0 && (
                  <div className={`text-[10px] mt-0.5 ${isActive ? 'text-white/60' : 'text-slate-400'}`}>
                    {checkedInCount > 0 && `${checkedInCount}/`}{actCount}活动
                  </div>
                )}
              </button>
            )
          })}
        </div>
      </div>

      {/* Day Summary */}
      {day.summary && (
        <div className="px-5 pb-2 flex-shrink-0">
          <p className="text-xs text-slate-400 leading-relaxed">{day.summary}</p>
        </div>
      )}

      {/* Activity Timeline */}
      <div className="flex-1 min-h-0 overflow-y-auto scrollbar-thin px-4 pb-6">
        <AnimatePresence mode="wait">
          <motion.div
            key={animKey}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
          >
            {activities.length > 0 ? (
              <div className="pt-1">
                {activities.map((act, i) => (
                  <TimelineActivity
                    key={act.id}
                    activity={act}
                    index={i}
                    isLast={i === activities.length - 1}
                    onClick={onActivityClick}
                  />
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-16 text-slate-300">
                <Sun size={36} className="mb-2" />
                <p className="text-sm">当天暂无活动安排</p>
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  )
}
