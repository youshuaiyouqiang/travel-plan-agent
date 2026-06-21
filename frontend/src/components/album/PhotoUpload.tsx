import { useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Upload, X, Loader2 } from 'lucide-react'

interface Props {
  itineraryId: string
  dayIndex: number
  onUpload: (files: File[], description: string, dayIndex: number) => Promise<void>
  uploading: boolean
}

export function PhotoUpload({ itineraryId, dayIndex, onUpload, uploading }: Props) {
  const [dragOver, setDragOver] = useState(false)
  const [description, setDescription] = useState('')

  const handleFiles = useCallback(
    async (files: FileList | File[]) => {
      const validFiles = Array.from(files).filter((f) =>
        f.type.startsWith('image/'),
      )
      if (validFiles.length === 0) return
      await onUpload(validFiles, description, dayIndex)
      setDescription('')
    },
    [onUpload, description, dayIndex],
  )

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragOver(false)
      handleFiles(e.dataTransfer.files)
    },
    [handleFiles],
  )

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        setDragOver(true)
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      className={`
        relative rounded-2xl border-2 border-dashed transition-all duration-200
        ${dragOver ? 'border-indigo-400 bg-indigo-50/50' : 'border-slate-200 hover:border-slate-300'}
        ${uploading ? 'pointer-events-none opacity-60' : ''}
      `}
    >
      <input
        type="file"
        multiple
        accept="image/*"
        className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
        onChange={(e) => e.target.files && handleFiles(e.target.files)}
        disabled={uploading}
      />
      <div className="flex flex-col items-center justify-center py-8 px-4">
        {uploading ? (
          <Loader2 size={28} className="text-indigo-500 animate-spin mb-2" />
        ) : (
          <Upload size={28} className="text-slate-400 mb-2" />
        )}
        <p className="text-sm text-slate-500">
          {uploading ? '上传中...' : '拖拽照片到此处，或点击选择'}
        </p>
        <p className="text-xs text-slate-400 mt-1">支持 JPG、PNG、WebP，单张不超过 10MB</p>
      </div>
    </div>
  )
}
