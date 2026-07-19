import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { MapPin, Clock, ChevronRight, CheckCircle2 } from 'lucide-react'
import { DayPlanData, ActivityData } from '../../features/travel/api'

interface Props {
  day: DayPlanData
  dayIndex: number
  onActivityClick: (activity: ActivityData) => void
}

const _GRADIENTS = [
  'from-sky-400 to-blue-500',
  'from-emerald-400 to-teal-500',
  'from-violet-400 to-purple-500',
  'from-amber-400 to-orange-500',
  'from-rose-400 to-pink-500',
  'from-cyan-400 to-sky-500',
]

function _getGradient(index: number): string {
  return _GRADIENTS[index % _GRADIENTS.length]
}

export function DayBlind({
  day,
  dayIndex,
  onActivityClick,
}: Props) {
  const [isHovered, setIsHovered] = useState(false)
  const activities = day.activities || []
  const gradient = _getGradient(dayIndex)

  return (
    <motion.div
      className="relative"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        delay: dayIndex * 0.12,
        duration: 0.4,
        ease: [0.25, 0.46, 0.45, 0.94] as [number, number, number, number],
      }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <div className="rounded-2xl overflow-hidden shadow-sm hover:shadow-lg transition-shadow duration-300">
        <div className={`bg-gradient-to-r ${gradient} px-4 py-2.5 flex items-center gap-2`}>
          <div className="w-6 h-6 rounded-md bg-white/20 flex items-center justify-center flex-shrink-0">
            <span className="text-white text-xs font-bold">D{dayIndex + 1}</span>
          </div>
          <span className="text-white font-semibold text-sm truncate">
            {day.title || `第${dayIndex + 1}天`}
          </span>
          {day.date && (
            <span className="text-white/70 text-xs ml-1">{day.date}</span>
          )}
          {day.summary && (
            <span className="text-white/60 text-xs ml-auto truncate max-w-[140px]">
              {day.summary}
            </span>
          )}
          <span className="text-white/50 text-xs ml-auto flex-shrink-0">
            {activities.length}个活动
          </span>
        </div>

        <div
          className="bg-white relative"
          style={{ perspective: '1200px' }}
        >
          <AnimatePresence mode="wait">
            {!isHovered ? (
              <motion.div
                key="collapsed"
                className="relative overflow-hidden"
                initial={false}
                animate={{ height: 'auto' }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.3 }}
              >
                {activities.map((act, i) => (
                  <motion.div
                    key={act.id}
                    className="flex items-center gap-3 px-4 border-b border-slate-50 last:border-b-0"
                    style={{ transformOrigin: 'top center' }}
                    initial={{ rotateX: -90, opacity: 0 }}
                    animate={{ rotateX: 0, opacity: 1 }}
                    transition={{
                      delay: dayIndex * 0.12 + i * 0.06,
                      duration: 0.4,
                      ease: [0.25, 0.46, 0.45, 0.94] as [number, number, number, number],
                    }}
                  >
                    <div className={`w-1 h-8 rounded-full bg-gradient-to-b ${_getGradient(i)} flex-shrink-0`} />
                    <span className="text-xs text-slate-400 w-4 flex-shrink-0">{i + 1}</span>
                    <span className="text-sm text-slate-700 truncate flex-1">{act.title}</span>
                    {act.time_slot && (
                      <span className="text-xs text-slate-400 flex-shrink-0">{act.time_slot}</span>
                    )}
                    {act.checked_in && (
                      <CheckCircle2 size={12} className="text-emerald-500 flex-shrink-0" />
                    )}
                  </motion.div>
                ))}
                {activities.length === 0 && (
                  <div className="text-center py-4 text-slate-400 text-xs">暂无活动</div>
                )}

                <div className="absolute inset-0 pointer-events-none">
                  {activities.map((_, i) => (
                    <div
                      key={i}
                      className="absolute left-0 right-0"
                      style={{
                        top: `${(i / activities.length) * 100}%`,
                        height: `${100 / activities.length}%`,
                        background: `linear-gradient(180deg, 
                          rgba(255,255,255,0.2) 0%, 
                          rgba(255,255,255,0.05) 40%, 
                          rgba(0,0,0,0.03) 60%, 
                          rgba(0,0,0,0.08) 100%)`,
                        borderBottom: i < activities.length - 1 ? '1px solid rgba(0,0,0,0.06)' : 'none',
                      }}
                    />
                  ))}
                </div>
              </motion.div>
            ) : (
              <motion.div
                key="expanded"
                className="relative overflow-hidden"
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.35, ease: 'easeOut' }}
              >
                {activities.map((act, i) => (
                  <motion.div
                    key={act.id}
                    className="flex items-center gap-3 px-4 py-3 border-b border-slate-100 last:border-b-0 cursor-pointer hover:bg-sky-50/50 transition-colors"
                    style={{ transformOrigin: 'top center' }}
                    initial={{ rotateX: -80, opacity: 0 }}
                    animate={{ rotateX: 0, opacity: 1 }}
                    transition={{
                      delay: i * 0.05,
                      duration: 0.35,
                      ease: [0.25, 0.46, 0.45, 0.94] as [number, number, number, number],
                    }}
                    onClick={() => onActivityClick(act)}
                  >
                    <div className={`w-8 h-8 rounded-lg bg-gradient-to-br ${_getGradient(i)} flex items-center justify-center flex-shrink-0`}>
                      <span className="text-white text-xs font-bold">{i + 1}</span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-sm font-medium text-slate-800 truncate">{act.title}</span>
                        {act.checked_in && (
                          <CheckCircle2 size={12} className="text-emerald-500 flex-shrink-0" />
                        )}
                      </div>
                      <div className="flex items-center gap-2 mt-0.5">
                        {act.location && (
                          <span className="text-xs text-slate-400 flex items-center gap-0.5 truncate">
                            <MapPin size={9} />
                            {act.location}
                          </span>
                        )}
                        {act.time_slot && (
                          <span className="text-xs text-slate-400 flex items-center gap-0.5 flex-shrink-0">
                            <Clock size={9} />
                            {act.time_slot}
                          </span>
                        )}
                        {act.cost > 0 && (
                          <span className="text-xs text-amber-600 font-medium flex-shrink-0">¥{act.cost}</span>
                        )}
                      </div>
                      {act.description && (
                        <p className="text-xs text-slate-400 mt-0.5 line-clamp-1">{act.description}</p>
                      )}
                    </div>
                    <ChevronRight size={14} className="text-slate-300 flex-shrink-0" />
                  </motion.div>
                ))}
                {activities.length === 0 && (
                  <div className="text-center py-6 text-slate-400 text-sm">暂无活动安排</div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </motion.div>
  )
}
