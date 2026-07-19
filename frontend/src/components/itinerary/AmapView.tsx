import { useEffect, useRef, useCallback } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

interface MapPoint {
  lng: number
  lat: number
  label?: string
  color?: string
}

interface AmapViewProps {
  points: MapPoint[]
  center?: { lng: number; lat: number }
  zoom?: number
  showPath?: boolean
  onClickPoint?: (index: number) => void
  className?: string
  style?: React.CSSProperties
}

function createIcon(label: string, color: string): L.DivIcon {
  return L.divIcon({
    className: '',
    html: `<div style="
      background:${color};
      color:#fff;
      width:28px;height:28px;
      border-radius:50% 50% 50% 0;
      transform:rotate(-45deg);
      display:flex;align-items:center;justify-content:center;
      box-shadow:0 2px 6px rgba(0,0,0,0.3);
      border:2px solid #fff;
    "><span style="transform:rotate(45deg);font-size:11px;font-weight:700;line-height:1;max-width:20px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${label}</span></div>`,
    iconSize: [28, 32],
    iconAnchor: [14, 32],
    popupAnchor: [0, -32],
  })
}

export function AmapView({
  points,
  center,
  zoom = 13,
  showPath = false,
  onClickPoint,
  className = '',
  style,
}: AmapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const markersRef = useRef<L.Marker[]>([])
  const polylineRef = useRef<L.Polyline | null>(null)

  const initMap = useCallback(() => {
    if (!containerRef.current) return

    if (mapRef.current) {
      mapRef.current.remove()
      mapRef.current = null
    }

    const map = L.map(containerRef.current, {
      zoom,
      zoomControl: true,
      attributionControl: false,
    })
    mapRef.current = map

    L.tileLayer('https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}', {
      subdomains: ['1', '2', '3', '4'],
      maxZoom: 18,
    }).addTo(map)

    markersRef.current = []

    if (points.length === 0 && center) {
      map.setView([center.lat, center.lng], zoom)
    }

    points.forEach((p, i) => {
      const color = p.color || '#6366f1'
      const displayLabel = p.label || `${i + 1}`
      const shortLabel = displayLabel.length > 3 ? displayLabel.substring(0, 2) : displayLabel

      const marker = L.marker([p.lat, p.lng], {
        icon: createIcon(shortLabel, color),
        title: displayLabel,
      })

      if (onClickPoint) {
        marker.on('click', () => onClickPoint(i))
      }

      marker.bindTooltip(displayLabel, {
        direction: 'top',
        offset: [0, -32],
        className: 'map-tooltip',
      })

      marker.addTo(map)
      markersRef.current.push(marker)
    })

    if (polylineRef.current) {
      polylineRef.current.remove()
      polylineRef.current = null
    }

    if (showPath && points.length >= 2) {
      const latlngs = points.map((p) => L.latLng(p.lat, p.lng))
      const polyline = L.polyline(latlngs, {
        color: '#6366f1',
        weight: 4,
        opacity: 0.8,
        lineJoin: 'round',
        lineCap: 'round',
        dashArray: undefined,
      })
      polyline.addTo(map)
      polylineRef.current = polyline
    }

    if (markersRef.current.length > 0) {
      const group = L.featureGroup(markersRef.current)
      map.fitBounds(group.getBounds().pad(0.2))
    }
  }, [points, center, zoom, showPath, onClickPoint])

  useEffect(() => {
    initMap()
    return () => {
      if (mapRef.current) {
        mapRef.current.remove()
        mapRef.current = null
      }
    }
  }, [initMap])

  return (
    <div
      ref={containerRef}
      className={className}
      style={{ width: '100%', height: '100%', minHeight: 180, ...style }}
    />
  )
}
