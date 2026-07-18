import { useEffect, useState, useMemo } from 'react'
import { ActivityData, geocodeAddress } from '../../features/travel/api'
import { MapPin, ChevronDown, ChevronUp, Loader2 } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { AmapView } from './AmapView'

interface MapMarker {
  activity: ActivityData
  lng: number
  lat: number
  formatted: string
}

interface ItineraryMapProps {
  days: {
    day_index: number
    date: string
    title: string
    activities: ActivityData[]
  }[]
  selectedDayIndex: number
  onActivityClick?: (activity: ActivityData) => void
  destination?: string
}

export function ItineraryMap({ days, selectedDayIndex, onActivityClick, destination }: ItineraryMapProps) {
  const [collapsed, setCollapsed] = useState(false)
  const [loading, setLoading] = useState(false)
  const [markers, setMarkers] = useState<MapMarker[]>([])
  const [destinationGeo, setDestinationGeo] = useState<{ lng: number; lat: number } | null>(null)
  const [geocodeError, setGeocodeError] = useState('')

  const currentDay = days[selectedDayIndex]
  const activities = useMemo(() => currentDay?.activities || [], [currentDay])

  useEffect(() => {
    const addrs = activities.map((a) => a.location || a.title).filter(Boolean)
    const uniqueAddrs = [...new Set(addrs)]

    if (uniqueAddrs.length === 0) {
      setMarkers([])
      if (destination) {
        geocodeAddress(destination, destination).then((geo) => {
          if (geo?.lng != null && geo?.lat != null) {
            setDestinationGeo({ lng: geo.lng, lat: geo.lat })
          } else {
            setGeocodeError('目的地解析失败')
          }
        })
      }
      return
    }

    setLoading(true)
    setGeocodeError('')

    Promise.all(uniqueAddrs.map((addr) => geocodeAddress(addr, destination)))
      .then((results) => {
        const geoMap = new Map<string, { lng: number; lat: number; formatted: string }>()
        results.forEach((r, i) => {
          if (r) geoMap.set(uniqueAddrs[i], { lng: r.lng!, lat: r.lat!, formatted: r.formatted })
        })

        const mapMarkers: MapMarker[] = []
        activities.forEach((act) => {
          const addr = act.location || act.title
          if (!addr) return
          const geo = geoMap.get(addr)
          if (geo) {
            mapMarkers.push({ activity: act, lng: geo.lng, lat: geo.lat, formatted: geo.formatted })
          }
        })
        setMarkers(mapMarkers)
        if (mapMarkers.length === 0) setGeocodeError('地址解析失败')
      })
      .catch(() => {
        setGeocodeError('地址解析失败')
        setMarkers([])
      })
      .finally(() => setLoading(false))
  }, [activities, destination])

  const mapPoints = markers.length > 0
    ? markers.map((m, i) => ({ lng: m.lng, lat: m.lat, label: `${i + 1}` }))
    : destinationGeo
      ? [{ lng: destinationGeo.lng, lat: destinationGeo.lat, label: destination }]
      : []

  const markerCount = markers.length
  const activityCount = activities.length

  const handleClickPoint = (index: number) => {
    if (markers[index]) {
      onActivityClick?.(markers[index].activity)
    }
  }

  return (
    <div className="px-5 mt-2">
      <div className="bg-white/80 backdrop-blur-xl rounded-2xl shadow-sm border border-white/50 overflow-hidden">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-slate-50/50 transition-colors"
        >
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-400 to-violet-500 flex items-center justify-center">
              <MapPin size={13} className="text-white" />
            </div>
            <span className="text-xs font-medium text-slate-600">
              Day {selectedDayIndex + 1} 地图
            </span>
            {loading && <Loader2 size={12} className="text-sky-500 animate-spin" />}
            {!loading && markerCount > 0 && (
              <span className="text-[10px] text-slate-400">
                {markerCount}/{activityCount} 个地点已定位
              </span>
            )}
            {!loading && markerCount === 0 && activityCount > 0 && geocodeError && (
              <span className="text-[10px] text-red-400">{geocodeError}</span>
            )}
          </div>
          {collapsed ? (
            <ChevronDown size={14} className="text-slate-400" />
          ) : (
            <ChevronUp size={14} className="text-slate-400" />
          )}
        </button>

        <AnimatePresence>
          {!collapsed && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.25, ease: 'easeInOut' }}
              className="overflow-hidden"
            >
              <div className="relative w-full" style={{ height: 220 }}>
                {loading && (
                  <div className="absolute inset-0 bg-slate-50 flex items-center justify-center z-10">
                    <Loader2 size={20} className="text-sky-500 animate-spin" />
                  </div>
                )}
                {!loading && mapPoints.length > 0 && (
                  <AmapView
                    points={mapPoints}
                    center={destinationGeo || undefined}
                    zoom={13}
                    showPath={markers.length >= 2}
                    onClickPoint={handleClickPoint}
                  />
                )}
                {!loading && mapPoints.length === 0 && geocodeError && (
                  <div className="w-full h-full flex items-center justify-center bg-slate-50 text-slate-400 text-xs">
                    {geocodeError}
                  </div>
                )}
                {!loading && mapPoints.length === 0 && !geocodeError && (
                  <div className="w-full h-full flex items-center justify-center bg-slate-50 text-slate-400 text-xs">
                    暂无地图数据
                  </div>
                )}
              </div>
              {markers.length > 0 && (
                <div className="flex flex-wrap gap-1 px-3 py-2 bg-white/70 backdrop-blur-sm border-t border-slate-100">
                  {markers.map((m, i) => (
                    <button
                      key={i}
                      onClick={() => onActivityClick?.(m.activity)}
                      className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-600 hover:bg-indigo-100 transition-colors truncate max-w-[120px]"
                    >
                      {i + 1}. {m.activity.title}
                    </button>
                  ))}
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
