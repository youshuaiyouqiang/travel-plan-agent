import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowLeft, Camera, Map, BookOpen, Loader2, Image as ImageIcon } from 'lucide-react'
import { useAlbumStore } from '../hooks/useAlbumStore'
import { useItineraryStore } from '../hooks/useItineraryStore'
import { PhotoGrid } from '../components/album/PhotoGrid'
import { PhotoUpload } from '../components/album/PhotoUpload'
import { PhotoPreview } from '../components/album/PhotoPreview'
import { PhotoTimeline } from '../components/album/PhotoTimeline'
import { PhotoMapView } from '../components/album/PhotoMapView'
import { getAlbumImageUrl, PhotoData } from '../utils/api'

type TabType = 'photos' | 'map' | 'travelogue'

/** 将游记中的 【photo:id】 标记替换为实际图片 */
function renderTravelogue(text: string, photos: PhotoData[]) {
  const photoMap = new globalThis.Map(photos.map((p) => [p.id, p]))
  // 按 【photo:数字】 拆分
  const parts = text.split(/【photo:(\d+)】/g)

  const elements: React.ReactNode[] = []
  for (let i = 0; i < parts.length; i++) {
    if (i % 2 === 0) {
      // 文本部分
      if (parts[i]) {
        // 按换行分段，保留段落结构
        const lines = parts[i].split('\n')
        lines.forEach((line, j) => {
          elements.push(<span key={`t-${i}-${j}`}>{line}</span>)
          if (j < lines.length - 1) elements.push(<br key={`br-${i}-${j}`} />)
        })
      }
    } else {
      // 照片 ID 部分
      const photoId = parseInt(parts[i], 10)
      const photo = photoMap.get(photoId)
      if (photo) {
        elements.push(
          <div key={`photo-${photoId}`} className="my-3">
            <img
              src={getAlbumImageUrl(photo.storage_path)}
              alt={photo.ai_description || photo.description || ''}
              className="rounded-xl max-w-full max-h-80 object-cover shadow-sm"
            />
            {photo.ai_description && (
              <p className="text-xs text-slate-400 mt-1.5 text-center">{photo.ai_description}</p>
            )}
          </div>
        )
      }
    }
  }
  return elements
}

export function AlbumPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const {
    photos,
    tags,
    cover,
    mapMarkers,
    travelogue,
    loading,
    uploading,
    error,
    loadPhotos,
    uploadPhotos,
    deletePhoto,
    setCover,
    loadMapMarkers,
    generateTravelogue,
  } = useAlbumStore()

  const { itinerary, loadItinerary } = useItineraryStore()

  const [activeTab, setActiveTab] = useState<TabType>('photos')
  const [selectedDay, setSelectedDay] = useState<number | null>(null)
  const [selectedTag, setSelectedTag] = useState<string | null>(null)
  const [previewIndex, setPreviewIndex] = useState<number | null>(null)

  useEffect(() => {
    if (id) {
      loadPhotos(id)
      loadItinerary(id)
    }
  }, [id, loadPhotos, loadItinerary])

  useEffect(() => {
    if (activeTab === 'map' && id) {
      loadMapMarkers(id)
    }
  }, [activeTab, id, loadMapMarkers])

  const maxDay = itinerary?.days?.length || 0

  const handleUpload = async (files: File[], description: string, dayIndex: number) => {
    if (!id) return
    await uploadPhotos(id, files, description, dayIndex)
  }

  const handlePhotoClick = (index: number) => {
    const filteredPhotos = selectedDay
      ? photos.filter((p) => p.day_index === selectedDay)
      : photos
    const displayPhotos = selectedTag
      ? filteredPhotos.filter((p) => p.tags?.includes(selectedTag))
      : filteredPhotos
    // 找到在 displayPhotos 中的实际索引
    setPreviewIndex(index)
  }

  const handleSetCover = async (photoId: number) => {
    if (!id) return
    await setCover(id, photoId)
  }

  const handleDelete = async (photoId: number) => {
    if (!id) return
    await deletePhoto(id, photoId)
  }

  const handleGenerateTravelogue = async () => {
    if (!id) return
    await generateTravelogue(id)
  }

  const tabs: { key: TabType; label: string; icon: React.ReactNode }[] = [
    { key: 'photos', label: '照片', icon: <Camera size={16} /> },
    { key: 'map', label: '地图轨迹', icon: <Map size={16} /> },
    { key: 'travelogue', label: '游记', icon: <BookOpen size={16} /> },
  ]

  return (
    <div className="h-screen flex flex-col bg-gradient-to-br from-sky-50 via-white to-indigo-50">
      {/* 顶部导航 */}
      <div className="flex items-center justify-between px-4 py-3 bg-white/80 backdrop-blur-lg border-b border-slate-100">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate(`/agent/travel/itinerary/${id}`)}
            className="p-2 rounded-xl hover:bg-slate-100 transition-colors"
          >
            <ArrowLeft size={20} className="text-slate-600" />
          </button>
          <div>
            <h1 className="text-lg font-bold text-slate-800">
              {itinerary?.title || '旅行相册'}
            </h1>
            <p className="text-xs text-slate-400">{photos.length} 张照片</p>
          </div>
        </div>

        {/* 封面预览 */}
        {cover && (
          <div className="flex items-center gap-2">
            <img
              src={getAlbumImageUrl(cover.thumbnail_path || cover.storage_path)}
              alt="封面"
              className="w-10 h-10 rounded-lg object-cover ring-2 ring-indigo-200"
            />
            <span className="text-xs text-slate-400">封面</span>
          </div>
        )}
      </div>

      {/* Tab 切换 */}
      <div className="flex gap-1 px-4 py-2 bg-white/60 backdrop-blur">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
              activeTab === tab.key
                ? 'bg-indigo-500 text-white shadow-md shadow-indigo-200'
                : 'text-slate-600 hover:bg-slate-100'
            }`}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* 内容区 */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {error && (
          <div className="mb-4 p-3 rounded-xl bg-red-50 text-red-600 text-sm">{error}</div>
        )}

        {activeTab === 'photos' && (
          <div className="space-y-4">
            {/* 时间线选择 */}
            {maxDay > 0 && (
              <PhotoTimeline
                photos={photos}
                maxDay={maxDay}
                selectedDay={selectedDay}
                onSelectDay={setSelectedDay}
              />
            )}

            {/* 上传区域 */}
            <PhotoUpload
              itineraryId={id || ''}
              dayIndex={selectedDay || 0}
              onUpload={handleUpload}
              uploading={uploading}
            />

            {/* 照片网格 */}
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="animate-spin text-indigo-500" size={24} />
              </div>
            ) : (
              <PhotoGrid
                photos={photos}
                tags={tags}
                selectedTag={selectedTag}
                selectedDay={selectedDay}
                onTagFilter={setSelectedTag}
                onPhotoClick={handlePhotoClick}
                onSetCover={handleSetCover}
                onDelete={handleDelete}
              />
            )}
          </div>
        )}

        {activeTab === 'map' && (
          <div className="space-y-4">
            {mapMarkers.length === 0 ? (
              <div className="text-center py-12">
                <Map size={48} className="mx-auto text-slate-300 mb-3" />
                <p className="text-slate-400 text-sm">
                  暂无带位置信息的照片
                </p>
                <p className="text-slate-300 text-xs mt-1">
                  上传包含 GPS 信息的照片即可在地图上查看轨迹
                </p>
              </div>
            ) : (
              <>
                <div className="rounded-2xl overflow-hidden shadow-lg" style={{ height: 400 }}>
                  <PhotoMapView markers={mapMarkers} />
                </div>
                <p className="text-center text-xs text-slate-400">
                  共 {mapMarkers.length} 个位置标记，点击标记可查看照片
                </p>
              </>
            )}
          </div>
        )}

        {activeTab === 'travelogue' && (
          <div className="space-y-4">
            {!travelogue ? (
              <div className="text-center py-12">
                <BookOpen size={48} className="mx-auto text-slate-300 mb-3" />
                <p className="text-slate-400 text-sm mb-4">
                  根据行程和照片自动生成图文游记
                </p>
                <button
                  onClick={handleGenerateTravelogue}
                  disabled={loading}
                  className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-indigo-500 to-purple-500 text-white font-medium shadow-lg shadow-indigo-200 hover:shadow-xl transition-all disabled:opacity-50"
                >
                  {loading ? (
                    <Loader2 size={18} className="animate-spin" />
                  ) : (
                    <BookOpen size={18} />
                  )}
                  {loading ? '生成中...' : '生成游记'}
                </button>
              </div>
            ) : (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="prose prose-slate max-w-none"
              >
                <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100">
                  <div className="text-slate-700 leading-relaxed travelogue-content">
                    {renderTravelogue(travelogue, photos)}
                  </div>
                </div>
                <div className="flex justify-center mt-4">
                  <button
                    onClick={handleGenerateTravelogue}
                    disabled={loading}
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-100 text-slate-600 text-sm hover:bg-slate-200 transition-colors disabled:opacity-50"
                  >
                    {loading ? <Loader2 size={14} className="animate-spin" /> : null}
                    重新生成
                  </button>
                </div>
              </motion.div>
            )}
          </div>
        )}
      </div>

      {/* 照片预览弹窗 */}
      {previewIndex !== null && (
        <PhotoPreview
          photos={selectedDay ? photos.filter((p) => p.day_index === selectedDay) : photos}
          initialIndex={previewIndex}
          onClose={() => setPreviewIndex(null)}
          onSetCover={handleSetCover}
          onDelete={handleDelete}
        />
      )}
    </div>
  )
}
