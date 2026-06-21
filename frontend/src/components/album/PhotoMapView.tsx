import { useEffect, useRef, useCallback } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { PhotoMapMarker, getAlbumImageUrl } from '../../utils/api'

interface Props {
  markers: PhotoMapMarker[]
  className?: string
  style?: React.CSSProperties
}

export function PhotoMapView({ markers, className = '', style }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const markersLayerRef = useRef<L.LayerGroup | null>(null)

  const initMap = useCallback(() => {
    if (!containerRef.current) return

    if (mapRef.current) {
      mapRef.current.remove()
      mapRef.current = null
    }

    const map = L.map(containerRef.current, {
      zoom: 12,
      zoomControl: true,
      attributionControl: false,
    })
    mapRef.current = map

    L.tileLayer('https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}', {
      subdomains: ['1', '2', '3', '4'],
      maxZoom: 18,
    }).addTo(map)

    const layerGroup = L.layerGroup().addTo(map)
    markersLayerRef.current = layerGroup

    const latlngs: L.LatLngExpression[] = []

    markers.forEach((m, i) => {
      const icon = L.divIcon({
        className: '',
        html: `<div style="
          background:#6366f1;
          color:#fff;
          width:32px;height:32px;
          border-radius:50% 50% 50% 0;
          transform:rotate(-45deg);
          display:flex;align-items:center;justify-content:center;
          box-shadow:0 2px 6px rgba(0,0,0,0.3);
          border:2px solid #fff;
        "><span style="transform:rotate(45deg);font-size:10px;font-weight:700;">D${m.day_index || i + 1}</span></div>`,
        iconSize: [32, 36],
        iconAnchor: [16, 36],
        popupAnchor: [0, -36],
      })

      const marker = L.marker([m.latitude, m.longitude], { icon })

      // 弹出窗口显示缩略图
      const thumbUrl = m.thumbnail_path ? getAlbumImageUrl(m.thumbnail_path) : ''
      const popupContent = thumbUrl
        ? `<div style="text-align:center;">
            <img src="${thumbUrl}" style="width:120px;height:90px;object-fit:cover;border-radius:8px;" />
            <p style="margin:4px 0 0;font-size:12px;color:#333;">${m.description}</p>
          </div>`
        : `<p style="font-size:12px;">${m.description}</p>`

      marker.bindPopup(popupContent, { maxWidth: 200 })
      marker.addTo(layerGroup)

      latlngs.push([m.latitude, m.longitude])
    })

    // 绘制轨迹线
    if (latlngs.length >= 2) {
      L.polyline(latlngs, {
        color: '#6366f1',
        weight: 3,
        opacity: 0.6,
        dashArray: '8, 8',
      }).addTo(layerGroup)
    }

    if (latlngs.length > 0) {
      map.fitBounds(L.latLngBounds(latlngs as L.LatLngExpression[]).pad(0.2))
    }
  }, [markers])

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
      style={{ width: '100%', height: '100%', minHeight: 300, ...style }}
    />
  )
}
