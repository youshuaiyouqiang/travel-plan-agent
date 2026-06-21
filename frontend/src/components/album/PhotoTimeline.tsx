import { PhotoData, getAlbumImageUrl } from '../../utils/api'

interface Props {
  photos: PhotoData[]
  maxDay: number
  selectedDay: number | null
  onSelectDay: (day: number | null) => void
}

export function PhotoTimeline({ photos, maxDay, selectedDay, onSelectDay }: Props) {
  // 按天分组
  const dayMap = new Map<number, PhotoData[]>()
  for (const p of photos) {
    const day = p.day_index || 0
    if (!dayMap.has(day)) dayMap.set(day, [])
    dayMap.get(day)!.push(p)
  }

  const days = Array.from({ length: maxDay }, (_, i) => i + 1)

  return (
    <div className="flex gap-3 overflow-x-auto pb-2 scrollbar-thin">
      {/* 全部 */}
      <button
        onClick={() => onSelectDay(null)}
        className={`flex-shrink-0 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
          selectedDay === null
            ? 'bg-indigo-500 text-white shadow-md shadow-indigo-200'
            : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
        }`}
      >
        全部 ({photos.length})
      </button>

      {days.map((day) => {
        const dayPhotos = dayMap.get(day) || []
        const cover = dayPhotos.find((p) => p.is_cover) || dayPhotos[0]
        const isSelected = selectedDay === day

        return (
          <button
            key={day}
            onClick={() => onSelectDay(isSelected ? null : day)}
            className={`flex-shrink-0 flex items-center gap-2 px-3 py-2 rounded-xl text-sm transition-all ${
              isSelected
                ? 'bg-indigo-500 text-white shadow-md shadow-indigo-200'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            {cover && (
              <img
                src={getAlbumImageUrl(cover.thumbnail_path || cover.storage_path)}
                alt=""
                className="w-8 h-8 rounded-lg object-cover"
              />
            )}
            <div className="text-left">
              <div className="font-medium">第{day}天</div>
              <div className="text-[10px] opacity-70">{dayPhotos.length}张</div>
            </div>
          </button>
        )
      })}
    </div>
  )
}
