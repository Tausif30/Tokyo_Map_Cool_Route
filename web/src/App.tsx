import { useCallback, useEffect, useMemo, useState } from 'react'
import MapView from './MapView'
import type {
  ApiRiskLevel,
  Coordinates,
  CoolSpot,
  NearbyCoolSpotsResponse,
  Route,
  RouteId,
  SpotFilter,
  WalkingRoutesResponse,
  WbgtStatus,
} from './types'
import { UI_COPY } from './i18n'
import type { Language } from './i18n'
import './App.css'

const API =
  import.meta.env.VITE_API_BASE_URL ??
  `${window.location.protocol}//${window.location.hostname}:8000`
const SHINJUKU_DEMO: Coordinates = { lat: 35.6909, lon: 139.7003 }

const FILTERS: SpotFilter[] = ['All', 'Indoor', 'Parks', 'Water']
type AppCopy = (typeof UI_COPY)[Language]

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal })
  const body: unknown = await response.json()

  if (!response.ok) {
    const detail =
      typeof body === 'object' && body !== null && 'detail' in body
        ? String(body.detail)
        : `Request failed with status ${response.status}`
    throw new Error(detail)
  }

  return body as T
}

function categoryMeta(category: CoolSpot['category'], copy: AppCopy) {
  if (category === 'Park') {
    return { ...copy.categories.Park, short: 'P', className: 'park' }
  }
  if (category === 'Drinking Station') {
    return { ...copy.categories['Drinking Station'], short: 'W', className: 'water' }
  }
  return { ...copy.categories['Convenience Store'], short: 'K', className: 'indoor' }
}

function displaySpotName(spot: CoolSpot, copy: AppCopy) {
  if (spot.name === spot.category || spot.name === 'Park' || spot.name === 'Convenience Store') {
    return copy.categories[spot.category].label
  }
  return spot.name
}

function matchesFilter(spot: CoolSpot, filter: SpotFilter) {
  if (filter === 'All') return true
  if (filter === 'Parks') return spot.category === 'Park'
  if (filter === 'Water') return spot.category === 'Drinking Station'
  return spot.category === 'Convenience Store'
}

function walkingMinutes(distanceM: number) {
  return Math.max(1, Math.ceil(distanceM / 80))
}

function mergeCategoryResults(result: NearbyCoolSpotsResponse) {
  const candidates = Object.values(result.by_category).flat()
  const source = candidates.length > 0 ? candidates : result.top_overall
  const unique = new Map<string, CoolSpot>()

  source.forEach((spot) => {
    unique.set(`${spot.category}-${spot.name}-${spot.lat}-${spot.lon}`, spot)
  })
  return [...unique.values()].sort((a, b) => b.score - a.score || a.distance_m - b.distance_m)
}

function StatusCard({
  status,
  loading,
  copy,
}: {
  status: WbgtStatus | null
  loading: boolean
  copy: AppCopy
}) {
  if (loading) {
    return (
      <section className="status-card status-loading" aria-label={copy.status.loading}>
        <span />
      </section>
    )
  }

  if (!status) {
    return (
      <section className="status-card status-unavailable">
        <p className="eyebrow">{copy.status.current}</p>
        <h2>{copy.status.unavailable}</h2>
        <p>{copy.status.unavailableHelp}</p>
      </section>
    )
  }

  const riskClass = status.risk_level.toLowerCase().replace(' ', '-')
  const guidance = copy.guidance[status.risk_level]

  return (
    <section className={`status-card risk-${riskClass}`} aria-live="polite">
      <div className="status-heading">
        <div>
          <p className="eyebrow">{copy.status.tokyoNow}</p>
          <p className="wbgt-value">WBGT {status.wbgt_c}°C</p>
        </div>
        <span className="risk-badge">{copy.risk.labels[status.risk_level]}</span>
      </div>
      <div className="guidance-block">
        <span className="guidance-icon" aria-hidden="true">
          !
        </span>
        <div>
          <h2>{guidance.title}</h2>
          <p>{guidance.detail}</p>
        </div>
      </div>
      <p className="observed-time">
        {copy.status.observed} {status.observed_at} · {copy.status[status.data_type]}
      </p>
    </section>
  )
}

function RiskScale({ status, copy }: { status: WbgtStatus | null; copy: AppCopy }) {
  const tiers: ApiRiskLevel[] = ['Almost Safe', 'Caution', 'Warning', 'Severe Warning', 'Danger']
  return (
    <section className="risk-scale-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">{copy.risk.official}</p>
          <h2>{copy.risk.title}</h2>
        </div>
        <button
          className="text-button"
          type="button"
          title={copy.risk.aboutTitle}
        >
          {copy.risk.about}
        </button>
      </div>
      <div className="risk-scale">
        {tiers.map((tier) => (
          <div key={tier} className={`risk-step ${status?.risk_level === tier ? 'current' : ''}`}>
            <span />
            <small>{copy.risk.labels[tier]}</small>
          </div>
        ))}
      </div>
    </section>
  )
}

interface LocationPanelProps {
  location: Coordinates | null
  selectedSpot: CoolSpot | null
  locating: boolean
  onLocate: () => void
  onDemo: () => void
  copy: AppCopy
}

function LocationPanel({ location, selectedSpot, locating, onLocate, onDemo, copy }: LocationPanelProps) {
  return (
    <section className="location-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">{copy.location.explore}</p>
          <h2>{copy.location.title}</h2>
        </div>
      </div>
      <div className="location-field">
        <span className="field-pin field-pin-a">A</span>
        <div>
          <small>{copy.location.pointA}</small>
          <strong>
            {location ? `${location.lat.toFixed(5)}, ${location.lon.toFixed(5)}` : copy.location.notSet}
          </strong>
        </div>
      </div>
      <div className="location-connector" />
      <div className="location-field">
        <span className="field-pin field-pin-b">B</span>
        <div>
          <small>{copy.location.destination}</small>
          <strong>{selectedSpot ? displaySpotName(selectedSpot, copy) : copy.location.selectPlace}</strong>
        </div>
      </div>
      <button className="primary-button" type="button" onClick={onLocate} disabled={locating}>
        <span className="crosshair" aria-hidden="true" />
        {locating ? copy.location.locating : copy.location.useLocation}
      </button>
      <button className="secondary-button" type="button" onClick={onDemo}>
        {copy.location.demo}
      </button>
    </section>
  )
}

interface SpotCardProps {
  spot: CoolSpot
  selected: boolean
  onSelect: (spot: CoolSpot) => void
  copy: AppCopy
}

function SpotCard({ spot, selected, onSelect, copy }: SpotCardProps) {
  const meta = categoryMeta(spot.category, copy)
  return (
    <button
      className={`spot-card ${selected ? 'selected' : ''}`}
      type="button"
      onClick={() => onSelect(spot)}
      aria-pressed={selected}
    >
      <span className={`spot-icon ${meta.className}`}>{meta.short}</span>
      <span className="spot-copy">
        <strong>{displaySpotName(spot, copy)}</strong>
        <span>
          {meta.detail} · {walkingMinutes(spot.distance_m)} {copy.selection.minuteWalk}
        </span>
      </span>
      <span className="spot-distance">{spot.distance_m} m</span>
      <span className="chevron" aria-hidden="true">
        ›
      </span>
    </button>
  )
}

export default function App() {
  const [language, setLanguage] = useState<Language>(() =>
    window.localStorage.getItem('tokyo-cool-route-language') === 'ja' ? 'ja' : 'en'
  )
  const copy = UI_COPY[language]
  const [wbgt, setWbgt] = useState<WbgtStatus | null>(null)
  const [wbgtLoading, setWbgtLoading] = useState(true)
  const [wbgtError, setWbgtError] = useState('')
  const [spots, setSpots] = useState<CoolSpot[]>([])
  const [spotsLoading, setSpotsLoading] = useState(false)
  const [location, setLocation] = useState<Coordinates | null>(null)
  const [selectedSpot, setSelectedSpot] = useState<CoolSpot | null>(null)
  const [filter, setFilter] = useState<SpotFilter>('All')
  const [locationError, setLocationError] = useState('')
  const [routeResult, setRouteResult] = useState<WalkingRoutesResponse | null>(null)
  const [routeLoading, setRouteLoading] = useState(false)
  const [routeError, setRouteError] = useState('')
  const [activeRouteId, setActiveRouteId] = useState<RouteId | null>(null)

  useEffect(() => {
    document.documentElement.lang = language
    window.localStorage.setItem('tokyo-cool-route-language', language)
  }, [language])

  const fetchWbgt = useCallback((signal?: AbortSignal) => {
    return getJson<WbgtStatus>(`${API}/wbgt/status`, signal)
      .then(setWbgt)
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setWbgtError(errorMessage(error, copy.errors.generic))
      })
      .finally(() => setWbgtLoading(false))
  }, [copy.errors.generic])

  const refreshWbgt = useCallback(() => {
    setWbgtLoading(true)
    setWbgtError('')
    void fetchWbgt()
  }, [fetchWbgt])

  useEffect(() => {
    const controller = new AbortController()
    void fetchWbgt(controller.signal)
    return () => controller.abort()
  }, [fetchWbgt])

  const loadNearby = useCallback(async (coordinates: Coordinates) => {
    setSpotsLoading(true)
    setLocationError('')
    setLocation(coordinates)
    setSelectedSpot(null)
    setRouteResult(null)
    setActiveRouteId(null)
    setRouteError('')

    const params = new URLSearchParams({
      lat: coordinates.lat.toString(),
      lon: coordinates.lon.toString(),
      radius_m: '1200',
      top_n: '12',
    })

    try {
      const result = await getJson<NearbyCoolSpotsResponse>(`${API}/nearby-cool-spots?${params}`)
      const availableSpots = mergeCategoryResults(result)
      setSpots(availableSpots)
      setSelectedSpot(availableSpots[0] ?? null)
    } catch (error: unknown) {
      setSpots([])
      setLocationError(errorMessage(error, copy.errors.generic))
    } finally {
      setSpotsLoading(false)
    }
  }, [copy.errors.generic])

  const findLocation = useCallback(() => {
    if (!navigator.geolocation) {
      setLocationError(copy.errors.unsupportedLocation)
      return
    }

    setSpotsLoading(true)
    setLocationError('')
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => void loadNearby({ lat: coords.latitude, lon: coords.longitude }),
      (error) => {
        setSpotsLoading(false)
        setLocationError(
          error.code === error.PERMISSION_DENIED
            ? copy.errors.permissionDenied
            : copy.errors.locationFailed
        )
      },
      { enableHighAccuracy: true, timeout: 10000 }
    )
  }, [copy.errors, loadNearby])

  const filteredSpots = useMemo(
    () => spots.filter((spot) => matchesFilter(spot, filter)),
    [filter, spots]
  )

  const handleSelectSpot = useCallback((spot: CoolSpot) => {
    setSelectedSpot(spot)
    setRouteResult(null)
    setActiveRouteId(null)
    setRouteError('')
  }, [])

  const findRoutes = useCallback(async () => {
    if (!location || !selectedSpot) return
    setRouteLoading(true)
    setRouteError('')

    const params = new URLSearchParams({
      start_lat: location.lat.toString(),
      start_lon: location.lon.toString(),
      end_lat: selectedSpot.lat.toString(),
      end_lon: selectedSpot.lon.toString(),
      max_detour_pct: '15',
    })

    try {
      const result = await getJson<WalkingRoutesResponse>(`${API}/routes/walking?${params}`)
      setRouteResult(result)
      setActiveRouteId(result.recommended_route_id)
    } catch (error: unknown) {
      setRouteResult(null)
      setActiveRouteId(null)
      setRouteError(errorMessage(error, copy.errors.generic))
    } finally {
      setRouteLoading(false)
    }
  }, [copy.errors.generic, location, selectedSpot])

  const handleFilter = useCallback(
    (nextFilter: SpotFilter) => {
      setFilter(nextFilter)
      setSelectedSpot((current) => {
        if (current && matchesFilter(current, nextFilter)) return current
        const nextSpot = spots.find((spot) => matchesFilter(spot, nextFilter)) ?? null
        setRouteResult(null)
        setActiveRouteId(null)
        setRouteError('')
        return nextSpot
      })
    },
    [spots]
  )

  return (
    <div className="app" lang={language}>
      <header className="app-header">
        <div className="brand-mark" aria-hidden="true">
          <span />
          <i />
        </div>
        <div className="brand-copy">
          <strong>{copy.header.title}</strong>
          <span>{copy.header.subtitle}</span>
        </div>
        <div className="header-status">
          <span className={`live-indicator ${wbgt ? 'online' : ''}`} />
          {wbgt ? `WBGT ${wbgt.wbgt_c}°C` : copy.header.waiting}
        </div>
        <button
          className="language-toggle"
          type="button"
          onClick={() => setLanguage((current) => (current === 'en' ? 'ja' : 'en'))}
          aria-label={copy.header.switchLanguage}
          title={copy.header.switchLanguage}
        >
          {language === 'en' ? '日本語' : 'English'}
        </button>
      </header>

      <div className="app-layout">
        <aside className="control-panel">
          <StatusCard status={wbgt} loading={wbgtLoading} copy={copy} />
          {wbgtError && (
            <div className="inline-alert" role="alert">
              <span>{wbgtError}</span>
              <button type="button" onClick={refreshWbgt}>
                {copy.errors.retry}
              </button>
            </div>
          )}
          <RiskScale status={wbgt} copy={copy} />
          <LocationPanel
            location={location}
            selectedSpot={selectedSpot}
            locating={spotsLoading}
            onLocate={findLocation}
            onDemo={() => void loadNearby(SHINJUKU_DEMO)}
            copy={copy}
          />
          <p className="method-note">{copy.methodNote}</p>
        </aside>

        <main className="map-panel">
          <MapView
            location={location}
            spots={filteredSpots}
            selectedSpot={selectedSpot}
            routes={routeResult?.routes ?? []}
            activeRouteId={activeRouteId}
            onSelectSpot={handleSelectSpot}
            onSelectRoute={setActiveRouteId}
            language={language}
          />

          {!location && (
            <div className="map-empty-card">
              <span className="empty-map-icon" aria-hidden="true">
                ⌖
              </span>
              <p className="eyebrow">{copy.emptyMap.eyebrow}</p>
              <h1>{copy.emptyMap.title}</h1>
              <p>{copy.emptyMap.detail}</p>
              <button className="primary-button" type="button" onClick={findLocation}>
                {copy.location.useLocation}
              </button>
            </div>
          )}

          {selectedSpot && location && (
            <section className="selection-tray" aria-live="polite">
              <div className={`spot-icon ${categoryMeta(selectedSpot.category, copy).className}`}>
                {categoryMeta(selectedSpot.category, copy).short}
              </div>
              <div className="selection-copy">
                <p className="eyebrow">{copy.selection.eyebrow}</p>
                <h2>{displaySpotName(selectedSpot, copy)}</h2>
                <p>
                  {selectedSpot.distance_m} {copy.selection.away} · {copy.selection.about}{' '}
                  {walkingMinutes(selectedSpot.distance_m)} {copy.selection.minuteWalk}
                </p>
              </div>
              <div className="route-panel">
                {!routeResult && (
                  <button
                    className="find-route-button"
                    type="button"
                    onClick={() => void findRoutes()}
                    disabled={routeLoading}
                  >
                    {routeLoading ? copy.routes.calculating : copy.routes.compare}
                  </button>
                )}
                {routeError && <p className="route-error">{routeError}</p>}
                {routeResult && (
                  <div className="route-options" aria-label={copy.routes.alternativesAria}>
                    {routeResult.routes.map((route: Route) => (
                      <button
                        key={route.id}
                        type="button"
                        className={`route-option route-${route.id}${
                          route.id === activeRouteId ? ' active' : ''
                        }`}
                        onClick={() => setActiveRouteId(route.id)}
                        aria-pressed={route.id === activeRouteId}
                      >
                        <span>
                          {copy.routes.labels[route.id]}
                          {route.id === routeResult.recommended_route_id && (
                            <small>{copy.routes.bestBalance}</small>
                          )}
                        </span>
                        <strong>{route.distance_m} m</strong>
                        <em>
                          {route.walking_minutes} {copy.routes.minutes} ·{' '}
                          {Math.round(route.heat_exposure_index * 100)}% {copy.routes.exposed}
                        </em>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </section>
          )}

        </main>

        <aside className="spots-panel">
          <div className="spots-heading">
            <div>
              <p className="eyebrow">{copy.spots.within}</p>
              <h2>{copy.spots.title}</h2>
            </div>
            <span className="result-count">{filteredSpots.length}</span>
          </div>

          <div className="filter-row" aria-label={copy.spots.filterAria}>
            {FILTERS.map((item) => (
              <button
                key={item}
                type="button"
                className={filter === item ? 'active' : ''}
                onClick={() => handleFilter(item)}
                aria-pressed={filter === item}
              >
                {copy.filters[item]}
              </button>
            ))}
          </div>

          {locationError && (
            <div className="panel-alert" role="alert">
              {locationError}
            </div>
          )}

          <div className="spot-list">
            {spotsLoading &&
              Array.from({ length: 4 }, (_, index) => (
                <div className="spot-skeleton" key={index}>
                  <span />
                  <div>
                    <i />
                    <i />
                  </div>
                </div>
              ))}

            {!spotsLoading && !location && (
              <div className="empty-list">
                <span aria-hidden="true">◎</span>
                <h3>{copy.spots.emptyTitle}</h3>
                <p>{copy.spots.emptyDetail}</p>
              </div>
            )}

            {!spotsLoading && location && filteredSpots.length === 0 && (
              <div className="empty-list">
                <span aria-hidden="true">–</span>
                <h3>{copy.spots.noneTitle}</h3>
                <p>{copy.spots.noneDetail}</p>
              </div>
            )}

            {!spotsLoading &&
              filteredSpots.map((spot) => (
                <SpotCard
                  key={`${spot.category}-${spot.name}-${spot.lat}-${spot.lon}`}
                  spot={spot}
                  selected={spot === selectedSpot}
                  onSelect={handleSelectSpot}
                  copy={copy}
                />
              ))}
          </div>

          <footer className="spots-footer">
            {copy.spots.footer}
          </footer>
        </aside>
      </div>
    </div>
  )
}
