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

export interface Place {
  name: string;
  category: string;
  lat: number;
  lon: number;
  distance_m?: number;
}


export type RouteId = 'shortest' | 'coolest' | 'balanced'

export interface Route {
  id: RouteId
  label: string
  description: string
  distance_m: number
  walking_minutes: number
  detour_pct: number
  heat_exposure_index: number
  cooling_score: number
  coords: [number, number][][]
}

export interface WalkingRoutesResponse {
  query: {
    start: Coordinates
    end: Coordinates
    direct_distance_m: number
    max_detour_pct: number
  }
  wbgt_c: number
  wbgt_source: 'current_status' | 'request' | 'fallback'
  recommended_route_id: RouteId
  routes: Route[]
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
