import { useState } from 'react'
import { motion } from 'framer-motion'
import { Tag, Star, MapPin } from 'lucide-react'
import { PhotoData, getAlbumImageUrl } from '../../utils/api'

interface Props {
  photos: PhotoData[]
  tags: string[]
  selectedTag: string | null
  selectedDay: number | null
  onTagFilter: (tag: string | null) => void
  onPhotoClick: (index: number) => void
  onSetCover?: (photoId: number) => void
  onDelete?: (photoId: number) => void
}

export function PhotoGrid({
  photos,
  tags,
  selectedTag,
  selectedDay,
  onTagFilter,
  onPhotoClick,
  onSetCover,
  onDelete,
}: Props) {
  const filteredPhotos = selectedDay
    ? photos.filter((p) => p.day_index === selectedDay)
    : photos

  const displayPhotos = selectedTag
    ? filteredPhotos.filter((p) => p.tags?.includes(selectedTag))
    : filteredPhotos

  if (displayPhotos.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-slate-400 text-sm">
          {selectedDay ? `第${selectedDay}天暂无照片` : '暂无照片，快来上传吧'}
        </p>
      </div>
    )
  }

  return (
    <div>
      {/* 标签筛选 */}
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-4">
          <button
            onClick={() => onTagFilter(null)}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              !selectedTag
                ? 'bg-indigo-500 text-white'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            全部
          </button>
          {tags.map((tag) => (
            <button
              key={tag}
              onClick={() => onTagFilter(tag)}
              className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                selectedTag === tag
                  ? 'bg-indigo-500 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {tag}
            </button>
          ))}
        </div>
      )}

      {/* 照片网格 */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
        {displayPhotos.map((photo, index) => (
          <motion.div
            key={photo.id}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: index * 0.03 }}
            className="group relative aspect-square rounded-xl overflow-hidden cursor-pointer bg-slate-100"
            onClick={() => onPhotoClick(index)}
          >
            <img
              src={getAlbumImageUrl(photo.thumbnail_path || photo.storage_path)}
              alt={photo.description || photo.file_name}
              className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
              loading="lazy"
            />
            {/* 悬浮信息 */}
            <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-200">
              <div className="absolute bottom-0 left-0 right-0 p-2">
                <p className="text-white text-xs truncate">
                  {photo.ai_description || photo.description || photo.file_name}
                </p>
                <div className="flex items-center gap-2 mt-0.5">
                  {photo.day_index > 0 && (
                    <span className="text-white/70 text-[10px]">第{photo.day_index}天</span>
                  )}
                  {photo.is_cover && (
                    <Star size={10} className="text-amber-400 fill-amber-400" />
                  )}
                  {photo.latitude != null && (
                    <MapPin size={10} className="text-white/70" />
                  )}
                </div>
              </div>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  )
}
