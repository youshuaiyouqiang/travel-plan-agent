import { useCallback } from 'react'
import useEmblaCarousel from 'embla-carousel-react'
import { motion } from 'framer-motion'
import { ChevronLeft, ChevronRight, Calendar } from 'lucide-react'
import { DayPlanData, ActivityData } from '../../features/travel/api'
import { ActivityCard } from './ActivityCard'

interface Props {
  days: DayPlanData[]
  selectedIndex: number
  onSelectDay: (index: number) => void
  onCheckIn: (activityId: number, checkedIn: boolean) => void
  onDelete: (activityId: number) => void
  onActivityClick: (activity: ActivityData) => void
}

const SLAT_COUNT = 8

export function DayCarousel({
  days,
  selectedIndex,
  onSelectDay,
  onCheckIn,
  onDelete,
  onActivityClick,
}: Props) {
  const [emblaRef, emblaApi] = useEmblaCarousel({
    loop: false,
    align: 'start',
    startIndex: selectedIndex,
  })

  const scrollPrev = useCallback(() => {
    emblaApi?.scrollPrev()
  }, [emblaApi])

  const scrollNext = useCallback(() => {
    emblaApi?.scrollNext()
  }, [emblaApi])

  const handleSelect = useCallback(
    (index: number) => {
      onSelectDay(index)
      emblaApi?.scrollTo(index)
    },
    [emblaApi, onSelectDay],
  )

  if (!days.length) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-400">
        暂无行程安排
      </div>
    )
  }

  const slatVariants = {
    hidden: () => ({
      scaleY: 0,
      opacity: 0,
    }),
    visible: (i: number) => ({
      scaleY: 1,
      opacity: 1,
      transition: {
        delay: i * 0.04,
        duration: 0.35,
        ease: [0.25, 0.46, 0.45, 0.94] as [number, number, number, number],
      },
    }),
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-4 py-3 overflow-x-auto scrollbar-none">
        {days.map((day, idx) => (
          <motion.button
            key={day.id}
            onClick={() => handleSelect(idx)}
            className={`
              flex-shrink-0 px-4 py-2 rounded-xl text-sm font-medium transition-all relative overflow-hidden
              ${
                idx === selectedIndex
                  ? 'bg-sky-500 text-white shadow-md shadow-sky-200'
                  : 'bg-white text-slate-600 border border-slate-200 hover:border-sky-300'
              }
            `}
            initial="hidden"
            animate="visible"
          >
            <div className="relative z-10">
              <div className="text-xs opacity-70">Day {idx + 1}</div>
              <div className="truncate max-w-[80px]">{day.title || `第${idx + 1}天`}</div>
            </div>
            {idx === selectedIndex && (
              <div className="absolute inset-0 pointer-events-none">
                {Array.from({ length: SLAT_COUNT }).map((_, i) => (
                  <motion.div
                    key={i}
                    custom={i}
                    variants={slatVariants}
                    initial="hidden"
                    animate="visible"
                    className="absolute left-0 right-0 bg-sky-500"
                    style={{
                      top: `${(i / SLAT_COUNT) * 100}%`,
                      height: `${100 / SLAT_COUNT}%`,
                      transformOrigin: 'left center',
                    }}
                  />
                ))}
              </div>
            )}
          </motion.button>
        ))}
      </div>

      <div className="relative flex-1 min-h-0">
        <button
          onClick={scrollPrev}
          className="absolute left-1 top-1/2 -translate-y-1/2 z-10 w-8 h-8 rounded-full bg-white/80 shadow-md flex items-center justify-center text-slate-400 hover:text-sky-500 transition-colors"
          style={{ display: selectedIndex > 0 ? 'flex' : 'none' }}
        >
          <ChevronLeft size={18} />
        </button>
        <button
          onClick={scrollNext}
          className="absolute right-1 top-1/2 -translate-y-1/2 z-10 w-8 h-8 rounded-full bg-white/80 shadow-md flex items-center justify-center text-slate-400 hover:text-sky-500 transition-colors"
          style={{ display: selectedIndex < days.length - 1 ? 'flex' : 'none' }}
        >
          <ChevronRight size={18} />
        </button>

        <div className="overflow-hidden h-full" ref={emblaRef}>
          <div className="flex h-full">
            {days.map((day, idx) => (
              <div key={day.id} className="flex-none w-full h-full">
                <div className="px-4 pb-4 h-full overflow-y-auto scrollbar-thin">
                  <div className="flex items-center gap-2 mb-3">
                    <Calendar size={16} className="text-sky-500" />
                    <span className="text-sm font-medium text-slate-700">
                      {day.date || `第${idx + 1}天`}
                    </span>
                    {day.summary && (
                      <span className="text-xs text-slate-400">· {day.summary}</span>
                    )}
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    {day.activities.map((act, actIdx) => (
                      <motion.div
                        key={act.id}
                        initial="hidden"
                        animate="visible"
                        custom={actIdx}
                        variants={{
                          hidden: () => ({
                            opacity: 0,
                            y: 20,
                          }),
                          visible: (i: number) => ({
                            opacity: 1,
                            y: 0,
                            transition: {
                              delay: i * 0.08,
                              duration: 0.4,
                              ease: [0.25, 0.46, 0.45, 0.94] as [number, number, number, number],
                            },
                          }),
                        }}
                      >
                        <ActivityCard
                          activity={act}
                          onCheckIn={onCheckIn}
                          onDelete={onDelete}
                          onClick={onActivityClick}
                        />
                      </motion.div>
                    ))}
                  </div>

                  {day.activities.length === 0 && (
                    <div className="flex items-center justify-center h-40 text-slate-400 text-sm">
                      当天暂无活动安排
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
