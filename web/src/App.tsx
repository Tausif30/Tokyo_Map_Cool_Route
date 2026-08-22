import { useCallback, useEffect, useMemo, useState } from 'react'
import MapView from './MapView'
import type {
  ApiRiskLevel,
  Coordinates,
  CoolSpot,
  NearbyCoolSpotsResponse,
  SpotFilter,
  WbgtStatus,
} from './types'
import './App.css'

const API = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const SHINJUKU_DEMO: Coordinates = { lat: 35.6909, lon: 139.7003 }

const GUIDANCE: Record<ApiRiskLevel, { title: string; detail: string }> = {
  'Almost Safe': {
    title: 'Heat risk is currently low',
    detail: 'Stay hydrated and check conditions again before a longer trip.',
  },
  Caution: {
    title: 'Hydrate before you leave',
    detail: 'Take breaks in shade, especially during physical activity.',
  },
  Warning: {
    title: 'Plan regular cooling breaks',
    detail: 'Avoid strenuous activity and use shaded streets where possible.',
  },
  'Severe Warning': {
    title: 'Avoid outdoor activity if possible',
    detail: 'If travel is essential, keep it short and stop in cool indoor places.',
  },
  Danger: {
    title: 'Avoid going outside now',
    detail: 'Stay in an air-conditioned place and delay non-essential travel.',
  },
}

const FILTERS: SpotFilter[] = ['All', 'Indoor', 'Parks', 'Water']

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'An unexpected error occurred'
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

function categoryMeta(category: CoolSpot['category']) {
  if (category === 'Park') {
    return { label: 'Park', short: 'P', detail: 'Outdoor shade', className: 'park' }
  }
  if (category === 'Drinking Station') {
    return { label: 'Water', short: 'W', detail: 'Hydration point', className: 'water' }
  }
  return { label: 'Indoor', short: 'AC', detail: 'Indoor refuge', className: 'indoor' }
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

function StatusCard({ status, loading }: { status: WbgtStatus | null; loading: boolean }) {
  if (loading) {
    return (
      <section className="status-card status-loading" aria-label="Loading current WBGT">
        <span />
      </section>
    )
  }

  if (!status) {
    return (
      <section className="status-card status-unavailable">
        <p className="eyebrow">Current conditions</p>
        <h2>WBGT unavailable</h2>
        <p>Run WBGT_Monitor.py, then refresh this page.</p>
      </section>
    )
  }

  const riskClass = status.risk_level.toLowerCase().replace(' ', '-')
  const guidance = GUIDANCE[status.risk_level]

  return (
    <section className={`status-card risk-${riskClass}`} aria-live="polite">
      <div className="status-heading">
        <div>
          <p className="eyebrow">Tokyo right now</p>
          <p className="wbgt-value">WBGT {status.wbgt_c}°C</p>
        </div>
        <span className="risk-badge">{status.risk_level}</span>
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
        Observed {status.observed_at} · {status.data_type}
      </p>
    </section>
  )
}

function RiskScale({ status }: { status: WbgtStatus | null }) {
  const tiers: ApiRiskLevel[] = ['Almost Safe', 'Caution', 'Warning', 'Severe Warning', 'Danger']
  return (
    <section className="risk-scale-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Official scale</p>
          <h2>WBGT risk level</h2>
        </div>
        <button
          className="text-button"
          type="button"
          title="WBGT is the Wet Bulb Globe Temperature"
        >
          About WBGT
        </button>
      </div>
      <div className="risk-scale">
        {tiers.map((tier) => (
          <div key={tier} className={`risk-step ${status?.risk_level === tier ? 'current' : ''}`}>
            <span />
            <small>{tier}</small>
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
}

function LocationPanel({ location, selectedSpot, locating, onLocate, onDemo }: LocationPanelProps) {
  return (
    <section className="location-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Explore nearby</p>
          <h2>Choose your location</h2>
        </div>
      </div>
      <div className="location-field">
        <span className="field-pin field-pin-a">A</span>
        <div>
          <small>Point A</small>
          <strong>
            {location ? `${location.lat.toFixed(5)}, ${location.lon.toFixed(5)}` : 'Not set'}
          </strong>
        </div>
      </div>
      <div className="location-connector" />
      <div className="location-field">
        <span className="field-pin field-pin-b">B</span>
        <div>
          <small>Cool destination</small>
          <strong>{selectedSpot?.name ?? 'Select a place on the map'}</strong>
        </div>
      </div>
      <button className="primary-button" type="button" onClick={onLocate} disabled={locating}>
        <span className="crosshair" aria-hidden="true" />
        {locating ? 'Finding your location…' : 'Use my location'}
      </button>
      <button className="secondary-button" type="button" onClick={onDemo}>
        Try Shinjuku demo
      </button>
    </section>
  )
}

interface SpotCardProps {
  spot: CoolSpot
  selected: boolean
  onSelect: (spot: CoolSpot) => void
}

function SpotCard({ spot, selected, onSelect }: SpotCardProps) {
  const meta = categoryMeta(spot.category)
  return (
    <button
      className={`spot-card ${selected ? 'selected' : ''}`}
      type="button"
      onClick={() => onSelect(spot)}
      aria-pressed={selected}
    >
      <span className={`spot-icon ${meta.className}`}>{meta.short}</span>
      <span className="spot-copy">
        <strong>{spot.name}</strong>
        <span>
          {meta.detail} · {walkingMinutes(spot.distance_m)} min walk
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
  const [wbgt, setWbgt] = useState<WbgtStatus | null>(null)
  const [wbgtLoading, setWbgtLoading] = useState(true)
  const [wbgtError, setWbgtError] = useState('')
  const [spots, setSpots] = useState<CoolSpot[]>([])
  const [spotsLoading, setSpotsLoading] = useState(false)
  const [location, setLocation] = useState<Coordinates | null>(null)
  const [selectedSpot, setSelectedSpot] = useState<CoolSpot | null>(null)
  const [filter, setFilter] = useState<SpotFilter>('All')
  const [locationError, setLocationError] = useState('')

  const fetchWbgt = useCallback((signal?: AbortSignal) => {
    return getJson<WbgtStatus>(`${API}/wbgt/status`, signal)
      .then(setWbgt)
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setWbgtError(errorMessage(error))
      })
      .finally(() => setWbgtLoading(false))
  }, [])

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
      setLocationError(errorMessage(error))
    } finally {
      setSpotsLoading(false)
    }
  }, [])

  const findLocation = useCallback(() => {
    if (!navigator.geolocation) {
      setLocationError('This browser does not support location access.')
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
            ? 'Location permission was denied. Use the Shinjuku demo or enable location access.'
            : 'Your location could not be determined. Please try again.'
        )
      },
      { enableHighAccuracy: true, timeout: 10000 }
    )
  }, [loadNearby])

  const filteredSpots = useMemo(
    () => spots.filter((spot) => matchesFilter(spot, filter)),
    [filter, spots]
  )

  const handleSelectSpot = useCallback((spot: CoolSpot) => setSelectedSpot(spot), [])
  const handleFilter = useCallback(
    (nextFilter: SpotFilter) => {
      setFilter(nextFilter)
      setSelectedSpot((current) => {
        if (current && matchesFilter(current, nextFilter)) return current
        return spots.find((spot) => matchesFilter(spot, nextFilter)) ?? null
      })
    },
    [spots]
  )

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand-mark" aria-hidden="true">
          <span />
          <i />
        </div>
        <div className="brand-copy">
          <strong>Tokyo Cool Route</strong>
          <span>Heat-safe walking support</span>
        </div>
        <div className="header-status">
          <span className={`live-indicator ${wbgt ? 'online' : ''}`} />
          {wbgt ? `WBGT ${wbgt.wbgt_c}°C` : 'Waiting for WBGT'}
        </div>
      </header>

      <div className="app-layout">
        <aside className="control-panel">
          <StatusCard status={wbgt} loading={wbgtLoading} />
          {wbgtError && (
            <div className="inline-alert" role="alert">
              <span>{wbgtError}</span>
              <button type="button" onClick={refreshWbgt}>
                Retry
              </button>
            </div>
          )}
          <RiskScale status={wbgt} />
          <LocationPanel
            location={location}
            selectedSpot={selectedSpot}
            locating={spotsLoading}
            onLocate={findLocation}
            onDemo={() => void loadNearby(SHINJUKU_DEMO)}
          />
          <p className="method-note">
            Official WBGT guidance · Cool-place ranking is an estimate based on category and
            distance.
          </p>
        </aside>

        <main className="map-panel">
          <MapView
            location={location}
            spots={filteredSpots}
            selectedSpot={selectedSpot}
            onSelectSpot={handleSelectSpot}
          />

          {!location && (
            <div className="map-empty-card">
              <span className="empty-map-icon" aria-hidden="true">
                ⌖
              </span>
              <p className="eyebrow">Start here</p>
              <h1>Find relief from the heat nearby</h1>
              <p>
                Use your current location to see parks, drinking water, and indoor places to cool
                down.
              </p>
              <button className="primary-button" type="button" onClick={findLocation}>
                Use my location
              </button>
            </div>
          )}

          {selectedSpot && location && (
            <section className="selection-tray" aria-live="polite">
              <div className={`spot-icon ${categoryMeta(selectedSpot.category).className}`}>
                {categoryMeta(selectedSpot.category).short}
              </div>
              <div className="selection-copy">
                <p className="eyebrow">Selected cool spot</p>
                <h2>{selectedSpot.name}</h2>
                <p>
                  {selectedSpot.distance_m} m away · about {walkingMinutes(selectedSpot.distance_m)}{' '}
                  min walk
                </p>
              </div>
              <div className="route-placeholder">
                <span>Fastest/coolest route comparison</span>
                <button
                  type="button"
                  disabled
                  title="The FastAPI backend does not expose a route endpoint yet"
                >
                  Route backend required
                </button>
              </div>
            </section>
          )}
        </main>

        <aside className="spots-panel">
          <div className="spots-heading">
            <div>
              <p className="eyebrow">Within 1.2 km</p>
              <h2>Nearby cool spots</h2>
            </div>
            <span className="result-count">{filteredSpots.length}</span>
          </div>

          <div className="filter-row" aria-label="Filter cooling places">
            {FILTERS.map((item) => (
              <button
                key={item}
                type="button"
                className={filter === item ? 'active' : ''}
                onClick={() => handleFilter(item)}
                aria-pressed={filter === item}
              >
                {item}
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
                <h3>Your nearby places will appear here</h3>
                <p>Share your location or use the demo point to explore the interface.</p>
              </div>
            )}

            {!spotsLoading && location && filteredSpots.length === 0 && (
              <div className="empty-list">
                <span aria-hidden="true">–</span>
                <h3>No matching places found</h3>
                <p>Choose another category or try a different location.</p>
              </div>
            )}

            {!spotsLoading &&
              filteredSpots.map((spot) => (
                <SpotCard
                  key={`${spot.category}-${spot.name}-${spot.lat}-${spot.lon}`}
                  spot={spot}
                  selected={spot === selectedSpot}
                  onSelect={handleSelectSpot}
                />
              ))}
          </div>

          <footer className="spots-footer">
            Availability and opening hours should be confirmed before travel.
          </footer>
        </aside>
      </div>
    </div>
  )
}
