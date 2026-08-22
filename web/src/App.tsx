import { useEffect, useState } from 'react'
import type { Coordinates, CoolSpot, NearbyCoolSpotsResponse, WbgtStatus } from './types'

const API = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'An unexpected error occurred'
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
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

export default function App() {
  const [wbgt, setWbgt] = useState<WbgtStatus | null>(null)
  const [spots, setSpots] = useState<CoolSpot[]>([])
  const [location, setLocation] = useState<Coordinates | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getJson<WbgtStatus>(`${API}/wbgt/status`)
      .then(setWbgt)
      .catch((err: unknown) => setError(errorMessage(err)))
  }, [])

  function findNearbySpots() {
    setError('')

    navigator.geolocation.getCurrentPosition(
      async ({ coords }) => {
        const { latitude, longitude } = coords
        setLocation({ lat: latitude, lon: longitude })

        const params = new URLSearchParams({
          lat: latitude.toString(),
          lon: longitude.toString(),
          radius_m: '800',
          top_n: '5',
        })

        try {
          const result = await getJson<NearbyCoolSpotsResponse>(
            `${API}/nearby-cool-spots?${params}`
          )
          setSpots(result.top_overall)
        } catch (err: unknown) {
          setError(errorMessage(err))
        }
      },
      () => setError('Location permission was denied.'),
      { enableHighAccuracy: true, timeout: 10000 }
    )
  }

  return (
    <main>
      <h1>Tokyo Cool Route</h1>

      {wbgt && (
        <section>
          <h2>Current heat conditions</h2>
          <p>WBGT: {wbgt.wbgt_c}°C</p>
          <p>Risk: {wbgt.risk_level}</p>
          <p>Observed: {wbgt.observed_at}</p>
        </section>
      )}

      <button onClick={findNearbySpots}>Find places to cool down</button>

      {location && (
        <p>
          Location: {location.lat.toFixed(5)}, {location.lon.toFixed(5)}
        </p>
      )}

      {error && <p role="alert">{error}</p>}

      <ul>
        {spots.map((spot, index) => (
          <li key={`${spot.category}-${spot.name}-${index}`}>
            <strong>{spot.name}</strong>
            <br />
            {spot.category} — {spot.distance_m} metres away
          </li>
        ))}
      </ul>
    </main>
  )
}
