import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, ChevronLeft, ChevronRight, MapPin, Calendar, Tag, Star } from 'lucide-react'
import { PhotoData, getAlbumImageUrl } from '../../utils/api'

interface Props {
  photos: PhotoData[]
  initialIndex?: number
  onClose: () => void
  onSetCover?: (photoId: number) => void
  onDelete?: (photoId: number) => void
}

export function PhotoPreview({ photos, initialIndex = 0, onClose, onSetCover, onDelete }: Props) {
  const [currentIndex, setCurrentIndex] = useState(initialIndex)
  const photo = photos[currentIndex]
  if (!photo) return null

  const goPrev = () => setCurrentIndex((i) => Math.max(0, i - 1))
  const goNext = () => setCurrentIndex((i) => Math.min(photos.length - 1, i + 1))

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center"
        onClick={onClose}
      >
        <motion.div
          initial={{ scale: 0.9, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.9, opacity: 0 }}
          className="relative max-w-4xl w-full mx-4"
          onClick={(e) => e.stopPropagation()}
        >
          {/* 关闭按钮 */}
          <button
            onClick={onClose}
            className="absolute -top-12 right-0 text-white/70 hover:text-white transition-colors"
          >
            <X size={28} />
          </button>

          {/* 图片 */}
          <div className="bg-slate-900 rounded-2xl overflow-hidden">
            <img
              src={getAlbumImageUrl(photo.storage_path)}
              alt={photo.description || photo.file_name}
              className="w-full max-h-[70vh] object-contain"
            />
          </div>

          {/* 信息栏 */}
          <div className="mt-3 flex items-start justify-between">
            <div className="text-white/90 space-y-1.5">
              <p className="text-sm font-medium">{photo.ai_description || photo.description || photo.file_name}</p>
              <div className="flex flex-wrap gap-3 text-xs text-white/60">
                {photo.day_index > 0 && (
                  <span className="flex items-center gap-1">
                    <Calendar size={12} /> 第{photo.day_index}天
                  </span>
                )}
                {photo.latitude != null && photo.longitude != null && (
                  <span className="flex items-center gap-1">
                    <MapPin size={12} /> {photo.latitude.toFixed(4)}, {photo.longitude.toFixed(4)}
                  </span>
                )}
              </div>
              {photo.tags && photo.tags.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-1">
                  {photo.tags.map((tag, i) => (
                    <span
                      key={i}
                      className="inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full bg-white/10 text-white/70 text-xs"
                    >
                      <Tag size={10} /> {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div className="flex gap-2">
              {onSetCover && !photo.is_cover && (
                <button
                  onClick={() => onSetCover(photo.id)}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-white/10 text-white/80 hover:bg-white/20 text-xs transition-colors"
                >
                  <Star size={12} /> 设为封面
                </button>
              )}
              {onDelete && (
                <button
                  onClick={() => { onDelete(photo.id); onClose() }}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-red-500/20 text-red-300 hover:bg-red-500/30 text-xs transition-colors"
                >
                  删除
                </button>
              )}
            </div>
          </div>

          {/* 左右切换 */}
          {currentIndex > 0 && (
            <button
              onClick={goPrev}
              className="absolute left-2 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-black/40 text-white flex items-center justify-center hover:bg-black/60 transition-colors"
            >
              <ChevronLeft size={20} />
            </button>
          )}
          {currentIndex < photos.length - 1 && (
            <button
              onClick={goNext}
              className="absolute right-2 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-black/40 text-white flex items-center justify-center hover:bg-black/60 transition-colors"
            >
              <ChevronRight size={20} />
            </button>
          )}

          {/* 计数器 */}
          <div className="absolute top-3 left-1/2 -translate-x-1/2 px-3 py-1 rounded-full bg-black/50 text-white/80 text-xs">
            {currentIndex + 1} / {photos.length}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
