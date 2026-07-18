import { create } from 'zustand'
import {
  getItinerary,
  deleteActivity as apiDeleteActivity,
  ItineraryData,
  ActivityData,
} from '../utils/api'

interface ItineraryState {
  itinerary: ItineraryData | null
  loading: boolean
  error: string | ''
  selectedDayIndex: number
  detailActivity: ActivityData | null
  loadItinerary: (id: string) => Promise<void>
  removeActivity: (activityId: number) => Promise<void>
  setSelectedDay: (index: number) => void
  setDetailActivity: (activity: ActivityData | null) => void
  reset: () => void
}

export const useItineraryStore = create<ItineraryState>((set, get) => ({
  itinerary: null,
  loading: false,
  error: '',
  selectedDayIndex: 0,
  detailActivity: null,

  loadItinerary: async (id: string) => {
    set({ loading: true, error: '' })
    try {
      const data = await getItinerary(id)
      set({ itinerary: data, loading: false, selectedDayIndex: 0 })
    } catch (e) {
      set({ error: e instanceof Error ? e.message : '加载失败', loading: false })
    }
  },

  removeActivity: async (activityId: number) => {
    const { itinerary } = get()
    if (!itinerary) return
    try {
      await apiDeleteActivity(itinerary.id, activityId)
      set((state) => {
        if (!state.itinerary?.days) return state
        const newDays = state.itinerary.days.map((day) => ({
          ...day,
          activities: day.activities.filter((act) => act.id !== activityId),
        }))
        return { itinerary: { ...state.itinerary, days: newDays } }
      })
    } catch (e) {
      set({ error: e instanceof Error ? e.message : '删除失败' })
    }
  },

  setSelectedDay: (index: number) => set({ selectedDayIndex: index }),

  setDetailActivity: (activity: ActivityData | null) => set({ detailActivity: activity }),

  reset: () =>
    set({
      itinerary: null,
      loading: false,
      error: '',
      selectedDayIndex: 0,
      detailActivity: null,
    }),
}))
