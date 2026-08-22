export type TierId = ' almost safe' | 'caution' | 'warning' | 'severe warning' | 'danger';
export type StopKind = 'Parks_Green_Spaces' | 'Protected_Green_Spaces' | 'Convenience_Stores' | 'Drinking_Station';
export type Confidence = 'high' | 'medium' | 'low';

export interface Stop {
  id: string;
  kind: StopKind;
  name: string;
  lat: number;
  lng: number;
  hours: string;
  note?: string;
  confidence: Confidence;
  restricted?: boolean;
}

export interface Route {
  id: 'fastest' | 'coolest';
  label: string;
  distanceM: number;
  minutes: number;
  exposedFraction: number;
  coords: [number, number][];
}

export interface WbgtReading {
  value: number;
  station: string;
  observedAt: string;
  forecast: { time: string; value: number }[];
}
