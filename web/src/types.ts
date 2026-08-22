export type TierId = ' almost safe' | 'caution' | 'warning' | 'severe warning' | 'danger'
export type StopKind =
  'Parks_Green_Spaces' | 'Protected_Green_Spaces' | 'Convenience_Stores' | 'Drinking_Station'
export type Confidence = 'high' | 'medium' | 'low'

export interface Stop {
  id: string
  kind: StopKind
  name: string
  lat: number
  lng: number
  hours: string
  note?: string
  confidence: Confidence
  restricted?: boolean
}

export interface Route {
  id: 'fastest' | 'coolest'
  label: string
  distanceM: number
  minutes: number
  exposedFraction: number
  coords: [number, number][]
}

export interface WbgtReading {
  value: number
  station: string
  observedAt: string
  forecast: { time: string; value: number }[]
}

// HTTP response types for the current FastAPI endpoints. These deliberately
// retain the API's snake_case field names so the boundary is explicit and no
// untyped conversion happens inside components.
export type ApiRiskLevel = 'Almost Safe' | 'Caution' | 'Warning' | 'Severe Warning' | 'Danger'

export interface WbgtStatus {
  station: number
  prefecture: string
  observed_at: string
  data_type: 'measured' | 'estimated'
  data_quality_flag: string | number | null
  wbgt_c: number
  risk_level: ApiRiskLevel
  alert: boolean
  checked_at: string
}

export interface Coordinates {
  lat: number
  lon: number
}

export interface CoolSpot extends Coordinates {
  category: 'Park' | 'Drinking Station' | 'Convenience Store'
  name: string
  distance_m: number
  score: number
}

export interface NearbyCoolSpotsResponse {
  query: Coordinates & { radius_m: number }
  heat_alert_active: boolean
  wbgt_c: number | null
  top_overall: CoolSpot[]
  by_category: Record<string, CoolSpot[]>
}

export type SpotFilter = 'All' | 'Indoor' | 'Parks' | 'Water'
