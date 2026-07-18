import { useEffect, useState } from 'react'
import { geocodeAddress } from '../../features/travel/api'
import { Loader2 } from 'lucide-react'
import { AmapView } from './AmapView'

interface MiniMapProps {
  location: string
  title: string
  destination?: string
}

export function MiniMap({ location, title, destination }: MiniMapProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [geo, setGeo] = useState<{ lng: number; lat: number } | null>(null)

  useEffect(() => {
    if (!location) return
    setLoading(true)
    setError('')
    geocodeAddress(location, destination)
      .then((result) => {
        if (result?.lng != null && result?.lat != null) {
          setGeo({ lng: result.lng, lat: result.lat })
        } else {
          setError('地址解析失败')
        }
      })
      .catch(() => setError('地址解析失败'))
      .finally(() => setLoading(false))
  }, [location, title, destination])

  return (
    <div className="relative rounded-xl overflow-hidden border border-slate-100">
      <div className="relative w-full" style={{ height: 180 }}>
        {loading && (
          <div className="absolute inset-0 bg-white/60 flex items-center justify-center z-10">
            <Loader2 size={16} className="text-sky-500 animate-spin" />
          </div>
        )}
        {!loading && geo && (
          <AmapView
            points={[{ lng: geo.lng, lat: geo.lat, label: title }]}
            zoom={14}
          />
        )}
        {!loading && error && (
          <div className="w-full h-full flex items-center justify-center bg-slate-50 text-xs text-slate-400">
            {error}
          </div>
        )}
        {!loading && !geo && !error && (
          <div className="w-full h-full flex items-center justify-center bg-slate-50 text-xs text-slate-400">
            暂无地图数据
          </div>
        )}
      </div>
    </div>
  )
}
