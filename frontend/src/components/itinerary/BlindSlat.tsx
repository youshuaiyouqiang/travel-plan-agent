import { motion } from 'framer-motion'
import { MapPin, Clock, ChevronRight, CheckCircle2, DollarSign } from 'lucide-react'
import { ActivityData } from '../../features/travel/api'

interface Props {
  activity: ActivityData
  index: number
  onCheckIn: (activityId: number, checkedIn: boolean) => void
  onDelete: (activityId: number) => void
  onClick: (activity: ActivityData) => void
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

export function BlindSlat({ activity, index, onCheckIn, onDelete, onClick }: Props) {
  const gradient = _getGradient(index)

  return (
    <motion.div
      className="relative"
      style={{ perspective: '1200px' }}
      initial={{ rotateX: -90, opacity: 0 }}
      animate={{ rotateX: 0, opacity: 1 }}
      transition={{
        delay: index * 0.08,
        duration: 0.5,
        ease: [0.25, 0.46, 0.45, 0.94] as [number, number, number, number],
      }}
    >
      <div
        onClick={() => onClick(activity)}
        className={`
          flex items-stretch rounded-2xl overflow-hidden cursor-pointer
          transition-all duration-200 active:scale-[0.98]
          shadow-sm hover:shadow-md
          ${activity.checked_in ? 'ring-2 ring-emerald-400 ring-offset-1' : ''}
        `}
        style={{ transformOrigin: 'top center' }}
      >
        <div className={`w-2 flex-shrink-0 bg-gradient-to-b ${gradient}`} />

        <div className="flex-1 flex items-center gap-3 bg-white px-4 py-3 min-w-0">
          <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${gradient} flex items-center justify-center flex-shrink-0`}>
            <span className="text-white font-bold text-sm">{index + 1}</span>
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-slate-800 truncate">
                {activity.title}
              </h3>
              {activity.checked_in && (
                <CheckCircle2 size={14} className="text-emerald-500 flex-shrink-0" />
              )}
            </div>
            <div className="flex items-center gap-2 mt-0.5">
              {activity.location && (
                <span className="text-xs text-slate-400 flex items-center gap-0.5 truncate">
                  <MapPin size={10} />
                  {activity.location}
                </span>
              )}
              {activity.time_slot && (
                <span className="text-xs text-slate-400 flex items-center gap-0.5 flex-shrink-0">
                  <Clock size={10} />
                  {activity.time_slot}
                </span>
              )}
              {activity.cost > 0 && (
                <span className="text-xs text-amber-600 font-medium flex-shrink-0">
                  ¥{activity.cost}
                </span>
              )}
            </div>
          </div>

          <ChevronRight size={16} className="text-slate-300 flex-shrink-0" />
        </div>
      </div>

      <motion.div
        className="absolute inset-0 pointer-events-none rounded-2xl"
        style={{
          background: `linear-gradient(180deg, 
            rgba(255,255,255,0.15) 0%, 
            rgba(255,255,255,0.05) 40%, 
            rgba(0,0,0,0.04) 60%, 
            rgba(0,0,0,0.08) 100%)`,
          borderBottom: '1px solid rgba(0,0,0,0.06)',
        }}
        initial={{ scaleY: 0 }}
        animate={{ scaleY: 1 }}
        transition={{
          delay: index * 0.08 + 0.3,
          duration: 0.3,
        }}
      />
    </motion.div>
  )
}
