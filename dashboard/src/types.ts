export interface Airport {
  code: string;
  city: string;
  name: string;
  lat: number;
  lon: number;
}

export interface Health {
  db: string;
}

export interface Route {
  route_id: string | number;
  origin: string;
  destination: string;
}

export interface SeriesPoint {
  index_date: string;
  index_value: number;
}

export interface HeatmapEntry {
  origin: string;
  destination: string;
  avg_fare: number;
  relative: number;
}

export interface RouteFare {
  avg_fare: number;
  observations: number;
  source: string;
}

export interface PriceSource {
  source: string;
  carrier: string;
  count: number;
  avg_fare: number;
  min_fare: number;
  max_fare: number;
}

export interface DatePrice {
  flight_date: string;
  avg_fare: number;
}

export interface ElasticityPoint {
  window: string;
  avg_fare: number;
}

export interface LogEntry {
  ts: string;
  level: string;
  msg: string;
}

export interface SelectOption {
  value: string;
  label: string;
}
