import { useEffect, useRef } from 'react'
import * as L from 'leaflet'
import type { Coordinates, CoolSpot } from './types'

interface MapViewProps {
  location: Coordinates | null
  spots: CoolSpot[]
  selectedSpot: CoolSpot | null
  onSelectSpot: (spot: CoolSpot) => void
}

const TOKYO_CENTER: L.LatLngExpression = [35.6812, 139.7671]

function markerIcon(kind: CoolSpot['category'], selected: boolean): L.DivIcon {
  const symbol = kind === 'Park' ? 'P' : kind === 'Drinking Station' ? 'W' : 'AC'
  const className = kind === 'Park' ? 'park' : kind === 'Drinking Station' ? 'water' : 'indoor'

  return L.divIcon({
    className: 'cool-marker-shell',
    html: `<span class="cool-marker ${className}${selected ? ' selected' : ''}"><b>${symbol}</b></span>`,
    iconSize: [38, 44],
    iconAnchor: [19, 40],
    tooltipAnchor: [0, -34],
  })
}

function userIcon(): L.DivIcon {
  return L.divIcon({
    className: 'cool-marker-shell',
    html: '<span class="user-marker"><span></span></span>',
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  })
}

export default function MapView({ location, spots, selectedSpot, onSelectSpot }: MapViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<L.Map | null>(null)
  const featureLayerRef = useRef<L.LayerGroup | null>(null)

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const map = L.map(containerRef.current, {
      center: TOKYO_CENTER,
      zoom: 12,
      zoomControl: false,
    })

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom: 19,
    }).addTo(map)
    L.control.zoom({ position: 'topright' }).addTo(map)

    const layer = L.layerGroup().addTo(map)
    mapRef.current = map
    featureLayerRef.current = layer

    return () => {
      map.remove()
      mapRef.current = null
      featureLayerRef.current = null
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    const layer = featureLayerRef.current
    if (!map || !layer) return

    layer.clearLayers()
    const bounds: L.LatLngExpression[] = []

    if (location) {
      const point: L.LatLngExpression = [location.lat, location.lon]
      L.marker(point, { icon: userIcon(), zIndexOffset: 1000 })
        .bindTooltip('Your location', { direction: 'top' })
        .addTo(layer)
      bounds.push(point)
    }

    spots.forEach((spot) => {
      const point: L.LatLngExpression = [spot.lat, spot.lon]
      const tooltip = document.createElement('span')
      tooltip.textContent = spot.name

      L.marker(point, {
        icon: markerIcon(spot.category, spot === selectedSpot),
        zIndexOffset: spot === selectedSpot ? 500 : 0,
      })
        .bindTooltip(tooltip, { direction: 'top' })
        .on('click', () => onSelectSpot(spot))
        .addTo(layer)
      bounds.push(point)
    })

    if (location && selectedSpot) {
      L.polyline(
        [
          [location.lat, location.lon],
          [selectedSpot.lat, selectedSpot.lon],
        ],
        { color: '#1976d2', dashArray: '4 8', opacity: 0.75, weight: 3 }
      ).addTo(layer)
    }

    if (bounds.length > 1) {
      map.fitBounds(L.latLngBounds(bounds), { padding: [70, 70], maxZoom: 16 })
    } else if (bounds.length === 1) {
      map.flyTo(bounds[0], 15)
    }
  }, [location, onSelectSpot, selectedSpot, spots])

  return (
    <div className="map-wrap">
      <div ref={containerRef} className="map-canvas" aria-label="Map of nearby cooling places" />
      <div className="map-legend" aria-label="Map legend">
        <span>
          <i className="legend-dot park" /> Park
        </span>
        <span>
          <i className="legend-dot water" /> Drinking water
        </span>
        <span>
          <i className="legend-dot indoor" /> Indoor refuge
        </span>
      </div>
    </div>
  )
}
