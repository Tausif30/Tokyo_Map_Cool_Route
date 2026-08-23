import { useEffect, useRef } from 'react'
import * as L from 'leaflet'
import type { Coordinates, CoolSpot, Route, RouteId } from './types'
import { UI_COPY } from './i18n'
import type { Language } from './i18n'

interface MapViewProps {
  location: Coordinates | null
  spots: CoolSpot[]
  selectedSpot: CoolSpot | null
  routes: Route[]
  activeRouteId: RouteId | null
  language: Language
  onSelectSpot: (spot: CoolSpot) => void
  onSelectRoute: (routeId: RouteId) => void
}

const TOKYO_CENTER: L.LatLngExpression = [35.6812, 139.7671]

function markerIcon(kind: CoolSpot['category'], selected: boolean): L.DivIcon {
  const symbol = kind === 'Park' ? 'P' : kind === 'Drinking Station' ? 'W' : 'K'
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

const ROUTE_COLORS: Record<RouteId, string> = {
  shortest: '#d1495b',
  coolest: '#2e7d32',
  balanced: '#1976d2',
}

export default function MapView({
  location,
  spots,
  selectedSpot,
  routes,
  activeRouteId,
  language,
  onSelectSpot,
  onSelectRoute,
}: MapViewProps) {
  const copy = UI_COPY[language]
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
    const resizeObserver = new ResizeObserver(() => map.invalidateSize({ pan: false }))
    resizeObserver.observe(containerRef.current)
    mapRef.current = map
    featureLayerRef.current = layer

    return () => {
      resizeObserver.disconnect()
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

    routes.forEach((route) => {
      const active = route.id === activeRouteId
      const segments = route.coords.map((segment) =>
        segment.map(([lat, lon]) => [lat, lon] as L.LatLngTuple)
      )
      const polyline = L.polyline(segments, {
        color: ROUTE_COLORS[route.id],
        weight: active ? 7 : 3,
        opacity: active ? 0.9 : 0.35,
        dashArray: active ? undefined : '7 8',
        lineCap: 'round',
        lineJoin: 'round',
      })
        .bindTooltip(`${copy.routes.labels[route.id]}: ${route.distance_m} m`, { sticky: true })
        .on('click', () => onSelectRoute(route.id))
        .addTo(layer)

      if (active) polyline.bringToFront()
      route.coords.flat().forEach(([lat, lon]) => bounds.push([lat, lon]))
    })

    if (location) {
      const point: L.LatLngExpression = [location.lat, location.lon]
      L.marker(point, { icon: userIcon(), zIndexOffset: 1000 })
        .bindTooltip(copy.map.yourLocation, { direction: 'top' })
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

    if (location && selectedSpot && routes.length === 0) {
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
  }, [activeRouteId, copy, location, onSelectRoute, onSelectSpot, routes, selectedSpot, spots])

  return (
    <div className="map-wrap">
      <div ref={containerRef} className="map-canvas" aria-label={copy.map.aria} />
      <div className="map-legend" aria-label={copy.map.legendAria}>
        <span>
          <i className="legend-dot park" /> {copy.map.park}
        </span>
        <span>
          <i className="legend-dot water" /> {copy.map.water}
        </span>
        <span>
          <i className="legend-dot indoor" /> {copy.map.indoor}
        </span>
        {routes.length > 0 && (
          <span>
            <i className="legend-route" /> {copy.map.route}
          </span>
        )}
      </div>
    </div>
  )
}
