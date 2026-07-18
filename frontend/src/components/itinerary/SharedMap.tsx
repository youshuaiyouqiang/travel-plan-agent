import { useEffect, useState, useMemo } from 'react'
import { DayPlanData, geocodeAddress } from '../../features/travel/api'
import { Loader2 } from 'lucide-react'
import { AmapView } from './AmapView'

const DAY_COLORS_CSS = ['#38bdf8', '#a78bfa', '#34d399', '#fb923c', '#f472b6', '#facc15']

interface GeoPoint {
  lng: number
  lat: number
  dayIndex: number
  title: string
}

interface SharedMapProps {
  days: DayPlanData[]
  destination?: string
}

export function SharedMap({ days, destination }: SharedMapProps) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [points, setPoints] = useState<GeoPoint[]>([])
  const [destinationGeo, setDestinationGeo] = useState<{ lng: number; lat: number } | null>(null)

  const allActivities = useMemo(() => {
    const acts: { dayIndex: number; title: string; location: string }[] = []
    days.forEach((day, di) => {
      day.activities.forEach((act) => {
        acts.push({ dayIndex: di, title: act.title, location: act.location })
      })
    })
    return acts
  }, [days])

  useEffect(() => {
    const addrs = allActivities.map((a) => a.location || a.title).filter(Boolean)
    if (addrs.length === 0) {
      if (destination) {
        geocodeAddress(destination, destination).then((geo) => {
          if (geo?.lng != null && geo?.lat != null) {
            setDestinationGeo({ lng: geo.lng, lat: geo.lat })
          }
          setLoading(false)
        }).catch(() => setLoading(false))
      } else {
        setLoading(false)
      }
      return
    }

    const uniqueAddrs = [...new Set(addrs)]
    Promise.all(uniqueAddrs.map((addr) => geocodeAddress(addr, destination)))
      .then((results) => {
        const geoMap = new Map<string, { lng: number; lat: number }>()
        results.forEach((r, i) => {
          if (r?.lng != null && r?.lat != null) {
            geoMap.set(uniqueAddrs[i], { lng: r.lng, lat: r.lat })
          }
        })

        const geoPoints: GeoPoint[] = []
        allActivities.forEach((a) => {
          const addr = a.location || a.title
          if (!addr) return
          const geo = geoMap.get(addr)
          if (geo) {
            geoPoints.push({ lng: geo.lng, lat: geo.lat, dayIndex: a.dayIndex, title: a.title })
          }
        })
        setPoints(geoPoints)
        if (geoPoints.length === 0 && !destination) setError('地址解析失败')
      })
      .catch(() => setError('地址解析失败'))
      .finally(() => setLoading(false))
  }, [allActivities, destination])

  const mapPoints = points.length > 0
    ? points.map((p, i) => ({
        lng: p.lng,
        lat: p.lat,
        label: `D${p.dayIndex + 1}-${i + 1}`,
        color: DAY_COLORS_CSS[p.dayIndex % DAY_COLORS_CSS.length],
      }))
    : destinationGeo
      ? [{ lng: destinationGeo.lng, lat: destinationGeo.lat, label: destination || '' }]
      : []

  return (
    <div className="px-4 mb-3">
      <div className="relative rounded-2xl overflow-hidden border border-slate-100 shadow-sm">
        <div className="relative w-full" style={{ height: 260 }}>
          {loading && (
            <div className="absolute inset-0 bg-white/60 flex items-center justify-center z-10">
              <Loader2 size={18} className="text-sky-500 animate-spin" />
            </div>
          )}
          {!loading && mapPoints.length > 0 && (
            <AmapView
              points={mapPoints}
              center={destinationGeo || undefined}
              zoom={12}
              showPath={points.length >= 2}
            />
          )}
          {!loading && mapPoints.length === 0 && error && (
            <div className="w-full h-full flex items-center justify-center bg-slate-50 text-xs text-slate-400">
              {error}
            </div>
          )}
          {!loading && mapPoints.length === 0 && !error && (
            <div className="w-full h-full flex items-center justify-center bg-slate-50 text-xs text-slate-400">
              暂无地图数据
            </div>
          )}
        </div>
        {!loading && !error && days.length > 1 && (
          <div className="absolute bottom-2 left-2 flex gap-1 bg-white/80 backdrop-blur-sm rounded-lg px-2 py-1">
            {days.map((_, i) => (
              <span
                key={i}
                className="text-[10px] font-medium px-1.5 py-0.5 rounded"
                style={{ background: DAY_COLORS_CSS[i % DAY_COLORS_CSS.length] + '20', color: DAY_COLORS_CSS[i % DAY_COLORS_CSS.length] }}
              >
                D{i + 1}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
