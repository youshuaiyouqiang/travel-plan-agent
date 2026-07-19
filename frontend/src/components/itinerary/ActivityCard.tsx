import { useState, useCallback, useRef } from 'react'
import { motion, useAnimation } from 'framer-motion'
import { MapPin, Clock, CheckCircle2, Trash2, ChevronRight } from 'lucide-react'
import { ActivityData } from '../../features/travel/api'

interface Props {
  activity: ActivityData
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

const SLAT_COUNT = 6

export function ActivityCard({ activity, onCheckIn, onDelete, onClick }: Props) {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [isCheckingIn, setIsCheckingIn] = useState(false)
  const controls = useAnimation()
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isLongPress = useRef(false)

  const handleLongPress = useCallback(() => {
    if (activity.checked_in) return
    isLongPress.current = true
    setIsCheckingIn(true)
    onCheckIn(activity.id, true)
    setTimeout(() => setIsCheckingIn(false), 800)
  }, [activity.id, activity.checked_in, onCheckIn])

  const handlePointerDown = useCallback(() => {
    isLongPress.current = false
    longPressTimer.current = setTimeout(() => {
      handleLongPress()
    }, 500)
  }, [handleLongPress])

  const handlePointerUp = useCallback(() => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current)
      longPressTimer.current = null
    }
  }, [])

  const handlePointerCancel = useCallback(() => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current)
      longPressTimer.current = null
    }
  }, [])

  const confirmDelete = useCallback(() => {
    onDelete(activity.id)
    setShowDeleteConfirm(false)
  }, [activity.id, onDelete])

  const cancelDelete = useCallback(() => {
    setShowDeleteConfirm(false)
  }, [])

  const gradient = _getGradient(activity.activity_index)

  const slatVariants = {
    hidden: () => ({
      rotateX: -90,
      opacity: 0,
    }),
    visible: (i: number) => ({
      rotateX: 0,
      opacity: 1,
      transition: {
        delay: i * 0.06,
        duration: 0.4,
        ease: [0.25, 0.46, 0.45, 0.94] as [number, number, number, number],
      },
    }),
  }

  return (
    <motion.div
      onPointerDown={handlePointerDown}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerCancel}
      drag="y"
      dragConstraints={{ top: 0, bottom: 0 }}
      dragElastic={0.15}
      onDragEnd={(_e, info) => {
        if (info.offset.y < -60) {
          setShowDeleteConfirm(true)
        }
        controls.start({ y: 0 })
      }}
      animate={controls}
      className="relative select-none"
      style={{ perspective: '800px' }}
    >
      <div
        onClick={() => {
          if (!isLongPress.current) {
            onClick(activity)
          }
          isLongPress.current = false
        }}
        className={`
          relative overflow-hidden rounded-2xl cursor-pointer
          transition-all duration-200 active:scale-[0.98]
          ${activity.checked_in ? 'ring-2 ring-emerald-400 ring-offset-2' : ''}
        `}
      >
        <div className={`h-36 bg-gradient-to-br ${gradient} relative`}>
          {activity.image_url ? (
            <img
              src={activity.image_url}
              alt={activity.title}
              className="w-full h-full object-cover opacity-80"
              loading="lazy"
            />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center">
              <MapPin size={48} className="text-white/30" />
            </div>
          )}

          <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent" />

          {activity.checked_in && (
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              className="absolute top-3 right-3 z-10"
            >
              <CheckCircle2 size={28} className="text-emerald-400 drop-shadow-lg" fill="white" />
            </motion.div>
          )}

          {isCheckingIn && (
            <motion.div
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0, opacity: 0 }}
              className="absolute inset-0 bg-emerald-500/40 flex items-center justify-center z-10"
            >
              <CheckCircle2 size={48} className="text-white drop-shadow-lg" />
            </motion.div>
          )}

          <div className="absolute bottom-0 left-0 right-0 p-3">
            <h3 className="text-white font-semibold text-base leading-tight truncate">
              {activity.title}
            </h3>
            {activity.location && (
              <p className="text-white/80 text-xs mt-0.5 truncate flex items-center gap-1">
                <MapPin size={10} />
                {activity.location}
              </p>
            )}
          </div>
        </div>

        <div className="bg-white px-3 py-2.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs text-slate-500">
              {activity.time_slot && (
                <span className="flex items-center gap-1">
                  <Clock size={12} />
                  {activity.time_slot}
                </span>
              )}
              {activity.cost > 0 && (
                <span className="text-amber-600 font-medium">
                  ¥{activity.cost}
                </span>
              )}
            </div>
            <ChevronRight size={14} className="text-slate-300" />
          </div>
          {activity.description && (
            <p className="text-xs text-slate-400 mt-1 line-clamp-1">
              {activity.description}
            </p>
          )}
        </div>

        <div className="absolute inset-0 pointer-events-none" style={{ perspective: '800px' }}>
          {Array.from({ length: SLAT_COUNT }).map((_, i) => (
            <motion.div
              key={i}
              custom={i}
              variants={slatVariants}
              initial="hidden"
              animate="visible"
              className="absolute left-0 right-0"
              style={{
                top: `${(i / SLAT_COUNT) * 100}%`,
                height: `${100 / SLAT_COUNT}%`,
                transformOrigin: 'top center',
                background: `linear-gradient(180deg, rgba(255,255,255,0.12) 0%, rgba(255,255,255,0.03) 50%, rgba(0,0,0,0.06) 100%)`,
                borderBottom: i < SLAT_COUNT - 1 ? '1px solid rgba(255,255,255,0.08)' : 'none',
              }}
            />
          ))}
        </div>
      </div>

      {showDeleteConfirm && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="absolute inset-0 bg-black/50 backdrop-blur-sm rounded-2xl flex flex-col items-center justify-center gap-3 z-10"
        >
          <Trash2 size={24} className="text-red-400" />
          <p className="text-white text-sm font-medium">删除此活动？</p>
          <div className="flex gap-3">
            <button
              onClick={(e) => { e.stopPropagation(); cancelDelete() }}
              className="px-4 py-1.5 rounded-lg bg-white/20 text-white text-sm hover:bg-white/30 transition-colors"
            >
              取消
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); confirmDelete() }}
              className="px-4 py-1.5 rounded-lg bg-red-500 text-white text-sm hover:bg-red-600 transition-colors"
            >
              删除
            </button>
          </div>
        </motion.div>
      )}
    </motion.div>
  )
}
