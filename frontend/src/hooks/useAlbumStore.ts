import { create } from 'zustand'
import {
  listPhotos as apiListPhotos,
  uploadPhotos as apiUploadPhotos,
  deletePhoto as apiDeletePhoto,
  updatePhoto as apiUpdatePhoto,
  setPhotoCover as apiSetCover,
  getPhotoMapMarkers as apiGetMapMarkers,
  generateTravelogue as apiGenerateTravelogue,
  PhotoData,
  PhotoMapMarker,
} from '../utils/api'

interface AlbumState {
  photos: PhotoData[]
  tags: string[]
  cover: PhotoData | null
  mapMarkers: PhotoMapMarker[]
  travelogue: string
  loading: boolean
  uploading: boolean
  error: string
  loadPhotos: (itineraryId: string, dayIndex?: number, tag?: string) => Promise<void>
  uploadPhotos: (itineraryId: string, files: File[], description?: string, dayIndex?: number) => Promise<void>
  deletePhoto: (itineraryId: string, photoId: number) => Promise<void>
  updatePhoto: (itineraryId: string, photoId: number, data: { description?: string; day_index?: number; tags?: string[] }) => Promise<void>
  setCover: (itineraryId: string, photoId: number) => Promise<void>
  loadMapMarkers: (itineraryId: string) => Promise<void>
  generateTravelogue: (itineraryId: string) => Promise<void>
  reset: () => void
}

export const useAlbumStore = create<AlbumState>((set, get) => ({
  photos: [],
  tags: [],
  cover: null,
  mapMarkers: [],
  travelogue: '',
  loading: false,
  uploading: false,
  error: '',

  loadPhotos: async (itineraryId, dayIndex, tag) => {
    set({ loading: true, error: '' })
    try {
      const data = await apiListPhotos(itineraryId, dayIndex, tag)
      set({ photos: data.photos, tags: data.tags, cover: data.cover, loading: false })
    } catch (e) {
      set({ error: e instanceof Error ? e.message : '加载失败', loading: false })
    }
  },

  uploadPhotos: async (itineraryId, files, description, dayIndex) => {
    set({ uploading: true, error: '' })
    try {
      const result = await apiUploadPhotos(itineraryId, files, description, dayIndex)
      // 重新加载列表
      await get().loadPhotos(itineraryId)
      set({ uploading: false })
    } catch (e) {
      set({ error: e instanceof Error ? e.message : '上传失败', uploading: false })
    }
  },

  deletePhoto: async (itineraryId, photoId) => {
    try {
      await apiDeletePhoto(itineraryId, photoId)
      set((state) => ({
        photos: state.photos.filter((p) => p.id !== photoId),
        cover: state.cover?.id === photoId ? null : state.cover,
      }))
    } catch (e) {
      set({ error: e instanceof Error ? e.message : '删除失败' })
    }
  },

  updatePhoto: async (itineraryId, photoId, data) => {
    try {
      const updated = await apiUpdatePhoto(itineraryId, photoId, data)
      set((state) => ({
        photos: state.photos.map((p) => (p.id === photoId ? updated : p)),
      }))
    } catch (e) {
      set({ error: e instanceof Error ? e.message : '更新失败' })
    }
  },

  setCover: async (itineraryId, photoId) => {
    try {
      const updated = await apiSetCover(itineraryId, photoId)
      set((state) => ({
        cover: updated,
        photos: state.photos.map((p) => ({
          ...p,
          is_cover: p.id === photoId,
        })),
      }))
    } catch (e) {
      set({ error: e instanceof Error ? e.message : '设置封面失败' })
    }
  },

  loadMapMarkers: async (itineraryId) => {
    try {
      const data = await apiGetMapMarkers(itineraryId)
      set({ mapMarkers: data.markers })
    } catch (e) {
      set({ error: e instanceof Error ? e.message : '加载地图失败' })
    }
  },

  generateTravelogue: async (itineraryId) => {
    set({ loading: true, error: '' })
    try {
      const data = await apiGenerateTravelogue(itineraryId)
      set({ travelogue: data.content, loading: false })
    } catch (e) {
      set({ error: e instanceof Error ? e.message : '生成游记失败', loading: false })
    }
  },

  reset: () => {
    set({
      photos: [],
      tags: [],
      cover: null,
      mapMarkers: [],
      travelogue: '',
      loading: false,
      uploading: false,
      error: '',
    })
  },
}))
