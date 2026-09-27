import { useEffect, useMemo, useState, useCallback, useRef, Component, type ReactNode } from 'react';
import {
  Area, AreaChart, CartesianGrid, Line, LineChart,
  ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { Select, Tabs } from './components/ui';
import IndiaMap from './components/IndiaMap';
import type {
  Airport, Health, Route, SeriesPoint, HeatmapEntry,
  RouteFare, PriceSource, DatePrice, ElasticityPoint, LogEntry,
} from './types';

const API = import.meta.env.VITE_API_URL ?? '';

const SOURCE_DOMAINS: Record<string, string> = {
  easemytrip: 'easemytrip.com',
  makemytrip: 'makemytrip.com',
  goibibo: 'goibibo.com',
  cleartrip: 'cleartrip.com',
  ixigo: 'ixigo.com',
  yatra: 'yatra.com',
  indigo_direct: 'goindigo.in',
  airindia_direct: 'airindia.com',
  airindia_express: 'airindiaexpress.com',
  akasa_direct: 'akasaair.com',
  spicejet_direct: 'spicejet.com',
};

function getSourceUrl(source: string, origin?: string, destination?: string): string {
  const domain = SOURCE_DOMAINS[source];
  if (!domain) return '#';
  const base = `https://${domain}`;
  if (!origin || !destination) return base;
  const today = new Date();
  const dateStr = today.toISOString().slice(0, 10);
  switch (source) {
    case 'easemytrip':
      return `${base}/flights/results?oCity=${origin}&dCity=${destination}&flightType=1&ddate=${dateStr}&adult=1&child=0&infant=0&class=Economy&source=Search`;
    case 'makemytrip':
      return `${base}/flights/results?itinerary=${origin}-${destination}-${dateStr}&tripType=O&paxType=A-1_C-0_I-0&cabinClass=E`;
    case 'goibibo':
      return `${base}/flights/air-${origin}-${destination}-${dateStr}--1-0-0-E-D/`;
    case 'cleartrip':
      return `${base}/flights/results?from=${origin}&to=${destination}&depart_date=${dateStr}&adults=1&childs=0&infants=0&class=Economy`;
    case 'ixigo':
      return `${base}/search/result/flight/${origin}/${destination}/${dateStr.replace(/-/g, '')}/1/0/0/e/1?mon=true`;
    case 'yatra':
      return `${base}/air-search-ui/dom2/trigger?ADT=1&CHD=0&INF=0&class=Economy&destination=${destination}&destinationCountry=IN&flexi=0&flight_depart_date=${dateStr}&hb=0&noOfSegments=1&origin=${origin}&originCountry=IN&type=O&version=1.1&viewName=normal`;
    case 'indigo_direct':
      return `${base}/booking/search-flight.html?origin=${origin}&destination=${destination}&departureDate=${dateStr}&adults=1&children=0&infants=0&tripType=OneWay`;
    case 'airindia_direct':
      return `${base}/in/en/book-flights.html?origin=${origin}&destination=${destination}&departureDate=${dateStr}&adults=1&tripType=oneway`;
    case 'airindia_express':
      return `${base}/book/search?origin=${origin}&destination=${destination}&depart=${dateStr}&adult=1`;
    case 'akasa_direct':
      return `${base}/search-flight?origin=${origin}&destination=${destination}&departure=${dateStr}&adult=1`;
    case 'spicejet_direct':
      return `${base}/Search.aspx?origin=${origin}&destination=${destination}&departDate=${dateStr}&adults=1&children=0&infants=0`;
    default:
      return base;
  }
}

function getFaviconUrl(source: string): string {
  const domain = SOURCE_DOMAINS[source];
  return domain ? `https://www.google.com/s2/favicons?domain=${domain}&sz=32` : '';
}



async function get<T>(path: string, retries = 3): Promise<T> {
  let lastError: Error | null = null;
  for (let attempt = 0; attempt < retries; attempt++) {
    try {
      const r = await fetch(`${API}${path}`);
      if (!r.ok) throw new Error(`${r.status} ${path}`);
      return r.json();
    } catch (e) {
      lastError = e as Error;
      if (attempt < retries - 1) {
        await new Promise(r => setTimeout(r, 1000 * (attempt + 1)));
      }
    }
  }
  throw lastError;
}

async function post<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`, { method: 'POST' });
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

const GRID = '#1c1c1f';
const TICK = { fill: '#71717a', fontSize: 11 };

interface ChartTipProps {
  active?: boolean;
  payload?: Array<{ dataKey?: string | number; color?: string; stroke?: string; name?: string; value?: number | string }>;
  label?: string;
}

function ChartTip({ active, payload, label }: ChartTipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-border bg-surface/95 backdrop-blur-xl px-4 py-3 text-xs shadow-2xl">
      <div className="mb-2 font-mono text-muted font-medium">{label}</div>
      {payload.map((p) => (
        <div key={String(p.dataKey)} className="flex items-center gap-2 py-0.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: p.color || p.stroke }} />
          <span className="text-muted">{p.name}:</span>
          <span className="font-mono font-semibold text-white">{Number(p.value).toLocaleString('en-IN')}</span>
        </div>
      ))}
    </div>
  );
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class ErrorBoundary extends Component<{ children: ReactNode }, ErrorBoundaryState> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error) {
    console.error('Dashboard error:', error);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex items-center justify-center h-screen bg-background">
          <div className="text-center p-8">
            <div className="text-6xl mb-4">⚠️</div>
            <h1 className="text-xl font-bold text-foreground mb-2">Something went wrong</h1>
            <p className="text-sm text-muted mb-4">{this.state.error?.message}</p>
            <button
              onClick={() => this.setState({ hasError: false, error: null })}
              className="px-4 py-2 rounded-lg bg-accent/20 text-accent border border-accent/30 hover:bg-accent/30 transition-colors"
            >
              Try Again
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

interface FloatingTopBarProps {
  health: Health | null;
  airports: Airport[];
  selectedOrigin: string;
  selectedDestination: string;
  onSelectOrigin: (code: string) => void;
  onSelectDestination: (code: string) => void;
  onRefresh: () => void;
  refreshing: boolean;
  routeFare: RouteFare | null;
  startDate: string;
  endDate: string;
  onStartDateChange: (d: string) => void;
  onEndDateChange: (d: string) => void;
  lastUpdated: string | null;
}

function FloatingTopBar({ health, airports, selectedOrigin, selectedDestination, onSelectOrigin, onSelectDestination, onRefresh, refreshing, routeFare, startDate, endDate, onStartDateChange, onEndDateChange, lastUpdated }: FloatingTopBarProps) {
  return (
    <div className="fixed top-4 left-1/2 -translate-x-1/2 z-[1000] w-[95%] max-w-4xl">
      <div className="rounded-2xl border border-border bg-background/80 backdrop-blur-xl shadow-2xl px-4 py-3 sm:px-6 sm:py-4">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2 sm:gap-3 flex-1 flex-wrap">
            <Select
              value={selectedOrigin || ''}
              onChange={onSelectOrigin}
              options={[
                { value: '', label: 'From' },
                ...airports.map(a => ({ value: a.code, label: `${a.city} (${a.code})` }))
              ]}
              className="w-32 sm:w-40"
              aria-label="Select origin airport"
            />
            <div className="text-muted">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M14 5l7 7m0 0l-7 7m7-7H3" />
              </svg>
            </div>
            <Select
              value={selectedDestination || ''}
              onChange={onSelectDestination}
              options={[
                { value: '', label: 'To' },
                ...airports.map(a => ({ value: a.code, label: `${a.city} (${a.code})` }))
              ]}
              className="w-32 sm:w-40"
              aria-label="Select destination airport"
            />
            {routeFare && routeFare.avg_fare && (
              <div className="rounded-lg border border-accent/30 bg-accent/10 px-3 py-1.5 ml-2">
                <span className="text-sm font-bold text-accent">₹{Number(routeFare.avg_fare).toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
              </div>
            )}
          </div>

          <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
            <div className="flex items-center gap-1">
              <input
                type="date"
                value={startDate}
                onChange={(e) => onStartDateChange(e.target.value)}
                className="h-8 rounded-md border border-input bg-background px-2 text-[10px] text-foreground outline-none"
                aria-label="Start date"
              />
              <span className="text-muted text-[10px]">to</span>
              <input
                type="date"
                value={endDate}
                onChange={(e) => onEndDateChange(e.target.value)}
                className="h-8 rounded-md border border-input bg-background px-2 text-[10px] text-foreground outline-none"
                aria-label="End date"
              />
            </div>
            <button
              onClick={onRefresh}
              disabled={refreshing}
              className="flex items-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-xs text-foreground hover:bg-accent/10 transition-all disabled:opacity-50"
              aria-label="Refresh data"
            >
              <svg className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              {refreshing ? 'Refreshing' : 'Refresh'}
            </button>
            <span className="flex items-center gap-2 rounded-full border border-border bg-background px-3 py-2 text-xs">
              <span className={`h-2 w-2 rounded-full ${health?.db === 'connected' ? 'bg-emerald-400 shadow-lg shadow-emerald-400/50 animate-pulse' : 'bg-red-400 shadow-lg shadow-red-400/50'}`} />
              <span className="text-muted-foreground">{health?.db === 'connected' ? 'Live' : 'Offline'}</span>
            </span>
          </div>
        </div>
        {lastUpdated && (
          <div className="text-[10px] text-muted-foreground mt-1 text-right">
            Last updated: {new Date(lastUpdated).toLocaleString()}
          </div>
        )}
      </div>
    </div>
  );
}

interface LogsPanelProps {
  logs: LogEntry[];
  onClear: () => void;
}

function LogsPanel({ logs, onClear }: LogsPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  const levelColor = (level: string) => {
    switch (level) {
      case 'ERROR': return 'text-red-400';
      case 'WARN': return 'text-amber-400';
      case 'INFO': return 'text-emerald-400';
      default: return 'text-muted-foreground';
    }
  };

  return (
    <div className="rounded-2xl border border-border bg-background/80 backdrop-blur-xl shadow-2xl overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Activity Logs</span>
        <button onClick={onClear} className="text-[10px] text-muted-foreground hover:text-foreground transition-colors">Clear</button>
      </div>
      <div ref={scrollRef} className="h-48 overflow-y-auto p-3 font-mono text-[11px] space-y-1">
        {logs.length === 0 && <div className="text-muted-foreground italic">No activity yet</div>}
        {logs.map((log, i) => (
          <div key={i} className="flex gap-2">
            <span className="text-muted-foreground/50 shrink-0">{log.ts?.slice(11, 19)}</span>
            <span className={`shrink-0 font-semibold ${levelColor(log.level)}`}>[{log.level}]</span>
            <span className="text-foreground/70">{log.msg}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

interface PriceSourcesPanelProps {
  sources: PriceSource[];
  loading: boolean;
  origin?: string;
  destination?: string;
}

function PriceSourcesPanel({ sources, loading, origin, destination }: PriceSourcesPanelProps) {
  if (loading) {
    return (
      <div className="rounded-2xl border border-border bg-background/80 backdrop-blur-xl shadow-2xl p-4">
        <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-3">Price Sources</div>
        <div className="animate-pulse space-y-2">
          <div className="h-4 bg-muted rounded w-3/4"></div>
          <div className="h-4 bg-muted rounded w-1/2"></div>
          <div className="h-4 bg-muted rounded w-2/3"></div>
        </div>
      </div>
    );
  }

  if (!sources || sources.length === 0) {
    return (
      <div className="rounded-2xl border border-border bg-background/80 backdrop-blur-xl shadow-2xl p-4">
        <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">Price Sources</div>
        <div className="text-xs text-muted-foreground">Select a route to see sources</div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-border bg-background/80 backdrop-blur-xl shadow-2xl p-4">
      <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-3">Price Sources</div>
      <div className="space-y-2">
        {sources.map((s, i) => {
          const url = getSourceUrl(s.source, origin, destination);
          const favicon = getFaviconUrl(s.source);
          return (
            <a
              key={i}
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-between rounded-lg border border-border bg-background/50 px-3 py-2 hover:bg-accent/10 hover:border-accent/30 transition-all cursor-pointer group"
            >
              <div className="flex items-center gap-2">
                {favicon ? (
                  <img src={favicon} alt="" className="h-4 w-4 rounded-sm" loading="lazy" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />
                ) : (
                  <div className="h-4 w-4 rounded-sm bg-muted flex items-center justify-center text-[8px] text-muted-foreground font-bold">
                    {s.source.charAt(0).toUpperCase()}
                  </div>
                )}
                <div>
                  <div className="text-xs font-medium text-foreground group-hover:text-accent transition-colors">{s.source}</div>
                  <div className="text-[10px] text-muted-foreground">{s.carrier} · {s.count} obs</div>
                </div>
              </div>
              <div className="text-right">
                <div className="text-sm font-bold text-foreground">₹{Number(s.avg_fare).toLocaleString('en-IN', { maximumFractionDigits: 0 })}</div>
                <div className="text-[10px] text-muted-foreground">₹{Number(s.min_fare).toLocaleString('en-IN', { maximumFractionDigits: 0 })} – ₹{Number(s.max_fare).toLocaleString('en-IN', { maximumFractionDigits: 0 })}</div>
              </div>
            </a>
          );
        })}
      </div>
    </div>
  );
}

interface DatePricePanelProps {
  dates: DatePrice[];
  loading: boolean;
}

function DatePricePanel({ dates, loading }: DatePricePanelProps) {
  if (loading) {
    return (
      <div className="rounded-2xl border border-border bg-background/80 backdrop-blur-xl shadow-2xl p-4">
        <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-3">Date vs Price</div>
        <div className="animate-pulse space-y-2">
          <div className="h-4 bg-muted rounded w-3/4"></div>
          <div className="h-4 bg-muted rounded w-1/2"></div>
          <div className="h-4 bg-muted rounded w-2/3"></div>
        </div>
      </div>
    );
  }

  if (!dates || dates.length === 0) {
    return (
      <div className="rounded-2xl border border-border bg-background/80 backdrop-blur-xl shadow-2xl p-4">
        <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">Date vs Price</div>
        <div className="text-xs text-muted-foreground">No flights available for selected route</div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-border bg-background/80 backdrop-blur-xl shadow-2xl p-4">
      <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-3">Date vs Price</div>
      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={dates}>
          <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="flight_date" tick={{ ...TICK, fontSize: 9 }} axisLine={false} tickLine={false}
            tickFormatter={(d) => String(d).slice(5)} />
          <YAxis tick={{ ...TICK, fontSize: 9 }} domain={['auto', 'auto']} axisLine={false} tickLine={false} width={40} />
          <Tooltip content={<ChartTip />} />
          <Line type="monotone" dataKey="avg_fare" stroke="#3291ff" strokeWidth={2} dot={{ r: 3, fill: '#3291ff' }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function relColor(r: number) {
  if (r < 0.98) return 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20';
  if (r < 1.03) return 'bg-amber-500/10 text-amber-300 border-amber-500/20';
  return 'bg-red-500/10 text-red-300 border-red-500/20';
}

function exportToCSV(data: Record<string, unknown>[], filename: string) {
  if (!data.length) return;
  const headers = Object.keys(data[0]);
  const csv = [
    headers.join(','),
    ...data.map(row => headers.map(h => JSON.stringify(row[h] ?? '')).join(','))
  ].join('\n');
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function AppInner() {
  const [gran, setGran] = useState('daily');
  const [series, setSeries] = useState<SeriesPoint[]>([]);
  const [weekly, setWeekly] = useState<SeriesPoint[]>([]);
  const [heat, setHeat] = useState<HeatmapEntry[]>([]);
  const [, setHeatSrc] = useState('');
  const [routes, setRoutes] = useState<Route[]>([]);
  const [routeId, setRouteId] = useState('1');
  const [curve, setCurve] = useState<ElasticityPoint[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [err, setErr] = useState('');
  const [airports, setAirports] = useState<Airport[]>([]);
  const [selectedOrigin, setSelectedOrigin] = useState('');
  const [selectedDestination, setSelectedDestination] = useState('');
  const [routeFare, setRouteFare] = useState<RouteFare | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [showStats, setShowStats] = useState(true);
  const [showHeatmap, setShowHeatmap] = useState(true);
  const [showElasticity, setShowElasticity] = useState(true);
  const [showBacktest, setShowBacktest] = useState(true);
  const [priceSources, setPriceSources] = useState<PriceSource[]>([]);
  const [priceSourcesLoading, setPriceSourcesLoading] = useState(false);
  const [datePrices, setDatePrices] = useState<DatePrice[]>([]);
  const [datePricesLoading, setDatePricesLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [showTable, setShowTable] = useState(false);

  const debouncedOrigin = useDebounce(selectedOrigin, 300);
  const debouncedDestination = useDebounce(selectedDestination, 300);

  useEffect(() => {
    Promise.all([
      get<Health>('/api/v1/health').then(setHealth).catch((e) => setErr(String(e))),
      get<{ series: SeriesPoint[] }>('/api/v1/index/weekly').then((d) => setWeekly(d.series)).catch(() => {}),
      get<{ heatmap: HeatmapEntry[]; source: string }>('/api/v1/fares/heatmap').then((d) => { setHeat(d.heatmap); setHeatSrc(d.source || ''); }).catch(() => {}),
      get<{ routes: Route[] }>('/api/v1/routes').then((d) => setRoutes(d.routes)).catch(() => {}),
      get<{ airports: Airport[] }>('/api/v1/airports').then((d) => setAirports(d.airports)).catch(() => {}),
    ]).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const params = new URLSearchParams();
    if (startDate) params.set('start', startDate);
    if (endDate) params.set('end', endDate);
    const qs = params.toString();
    get<{ series: SeriesPoint[] }>(`/api/v1/index/${gran}${qs ? `?${qs}` : ''}`).then((d) => {
      setSeries(d.series);
      setLastUpdated(new Date().toISOString());
    }).catch(() => {});
  }, [gran, startDate, endDate]);

  useEffect(() => {
    get<{ curve: ElasticityPoint[] }>(`/api/v1/fares/elasticity/${routeId}`).then((d) => setCurve(d.curve)).catch(() => {});
  }, [routeId]);

  const fetchRouteFare = useCallback(async (origin: string, destination: string) => {
    if (!origin || !destination) {
      setRouteFare(null);
      return;
    }
    try {
      const data = await get<RouteFare>(`/api/v1/fares/route?origin=${origin}&destination=${destination}`);
      setRouteFare(data);
    } catch {
      setRouteFare(null);
    }
  }, []);

  const fetchPriceSources = useCallback(async (origin: string, destination: string) => {
    if (!origin || !destination) {
      setPriceSources([]);
      return;
    }
    setPriceSourcesLoading(true);
    try {
      const data = await get<{ sources: PriceSource[] }>(`/api/v1/fares/sources?origin=${origin}&destination=${destination}`);
      setPriceSources(data.sources || []);
    } catch {
      setPriceSources([]);
    } finally {
      setPriceSourcesLoading(false);
    }
  }, []);

  const fetchDatePrices = useCallback(async (origin: string, destination: string) => {
    if (!origin || !destination) {
      setDatePrices([]);
      return;
    }
    setDatePricesLoading(true);
    try {
      const data = await get<{ dates: DatePrice[] }>(`/api/v1/fares/by-date?origin=${origin}&destination=${destination}`);
      setDatePrices(data.dates || []);
    } catch {
      setDatePrices([]);
    } finally {
      setDatePricesLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRouteFare(debouncedOrigin, debouncedDestination);
    fetchPriceSources(debouncedOrigin, debouncedDestination);
    fetchDatePrices(debouncedOrigin, debouncedDestination);
  }, [debouncedOrigin, debouncedDestination, fetchRouteFare, fetchPriceSources, fetchDatePrices]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    setLogs(prev => [...prev, { ts: new Date().toISOString(), level: 'INFO', msg: 'Manual refresh triggered...' }]);
    try {
      const result = await post<{ logs?: LogEntry[] }>('/api/v1/refresh');
      if (result.logs) {
        setLogs(prev => [...prev, ...(result.logs ?? [])]);
      }
      const [healthRes, weeklyRes, heatRes, routesRes] = await Promise.all([
        get<Health>('/api/v1/health'),
        get<{ series: SeriesPoint[] }>('/api/v1/index/weekly'),
        get<{ heatmap: HeatmapEntry[]; source: string }>('/api/v1/fares/heatmap'),
        get<{ routes: Route[] }>('/api/v1/routes'),
      ]);
      setHealth(healthRes);
      setWeekly(weeklyRes.series);
      setHeat(heatRes.heatmap);
      setHeatSrc(heatRes.source || '');
      setRoutes(routesRes.routes);
      if (debouncedOrigin && debouncedDestination) {
        fetchRouteFare(debouncedOrigin, debouncedDestination);
        fetchPriceSources(debouncedOrigin, debouncedDestination);
        fetchDatePrices(debouncedOrigin, debouncedDestination);
      }
    } catch (e) {
      setLogs(prev => [...prev, { ts: new Date().toISOString(), level: 'ERROR', msg: `Refresh failed: ${(e as Error).message}` }]);
    } finally {
      setRefreshing(false);
    }
  }, [debouncedOrigin, debouncedDestination, fetchRouteFare, fetchPriceSources, fetchDatePrices]);

  const stats = useMemo(() => {
    if (!series.length) return {};
    const first = series[0].index_value;
    const last = series[series.length - 1].index_value;
    const chg = ((last - first) / first) * 100;
    const chg30 = series.length > 30
      ? ((last - series[series.length - 31].index_value) / series[series.length - 31].index_value) * 100
      : chg;
    return { last, chg, chg30, n: series.length };
  }, [series]);

  const backtest = useMemo(() => {
    const wmap = Object.fromEntries(weekly.map((p) => [p.index_date, p.index_value]));
    return series.map((p) => ({ date: p.index_date, daily: p.index_value, trend: wmap[p.index_date] ?? null }));
  }, [series, weekly]);

  void backtest;

  const handleExport = useCallback(() => {
    exportToCSV(series as unknown as Record<string, unknown>[], `apix-${gran}-${new Date().toISOString().slice(0, 10)}.csv`);
  }, [series, gran]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <div className="text-center">
          <div className="animate-spin h-8 w-8 border-2 border-accent border-t-transparent rounded-full mx-auto mb-4"></div>
          <p className="text-sm text-muted">Loading APIx dashboard...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen w-screen overflow-hidden bg-background font-sans text-foreground relative">
      <div className="absolute inset-0 z-0">
        <IndiaMap
          airports={airports}
          selectedOrigin={selectedOrigin}
          selectedDestination={selectedDestination}
          onSelectOrigin={(code) => setSelectedOrigin(code)}
          onSelectDestination={(code) => setSelectedDestination(code)}
          routeFare={routeFare}
        />
      </div>

      <div className="absolute inset-0 z-10 pointer-events-none">
        <div className="absolute inset-0 bg-gradient-to-b from-background/60 via-transparent to-background/80" />
      </div>

      <div className="relative z-20 h-full flex flex-col pointer-events-none">
        <div className="pointer-events-auto">
          <FloatingTopBar
            health={health}
            airports={airports}
            selectedOrigin={selectedOrigin}
            selectedDestination={selectedDestination}
            onSelectOrigin={setSelectedOrigin}
            onSelectDestination={setSelectedDestination}
            onRefresh={handleRefresh}
            refreshing={refreshing}
            routeFare={routeFare}
            startDate={startDate}
            endDate={endDate}
            onStartDateChange={setStartDate}
            onEndDateChange={setEndDate}
            lastUpdated={lastUpdated}
          />
        </div>

        <div className="flex-1 overflow-y-auto overflow-x-hidden p-4 pt-32 pointer-events-auto">
          <div className="flex flex-col lg:flex-row items-start justify-between gap-4 min-h-full">
            <div className="flex flex-col gap-3 w-full lg:w-80 shrink-0">
              {showStats && (
                <div className="grid grid-cols-2 gap-2">
                  <div className="rounded-xl border border-border bg-background/80 backdrop-blur-xl p-3 hover:border-accent/30 transition-colors">
                    <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Index</div>
                    <div className="text-xl font-bold text-foreground mt-0.5">{stats.last?.toFixed(2) ?? '—'}</div>
                  </div>
                  <div className="rounded-xl border border-border bg-background/80 backdrop-blur-xl p-3 hover:border-accent/30 transition-colors">
                    <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Change</div>
                    <div className={`text-xl font-bold mt-0.5 ${(stats.chg ?? 0) >= 0 ? 'text-red-400' : 'text-emerald-400'}`}>
                      {(stats.chg ?? 0) >= 0 ? '+' : ''}{(stats.chg ?? 0).toFixed(2)}%
                    </div>
                  </div>
                  <div className="rounded-xl border border-border bg-background/80 backdrop-blur-xl p-3 hover:border-accent/30 transition-colors">
                    <div className="text-[10px] text-muted-foreground uppercase tracking-wider">30d</div>
                    <div className={`text-xl font-bold mt-0.5 ${(stats.chg30 ?? 0) >= 0 ? 'text-red-400' : 'text-emerald-400'}`}>
                      {(stats.chg30 ?? 0) >= 0 ? '+' : ''}{(stats.chg30 ?? 0).toFixed(2)}%
                    </div>
                  </div>
                  <div className="rounded-xl border border-border bg-background/80 backdrop-blur-xl p-3 hover:border-accent/30 transition-colors">
                    <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Obs</div>
                    <div className="text-xl font-bold text-foreground mt-0.5">{stats.n ?? '—'}</div>
                  </div>
                </div>
              )}

              {showHeatmap && heat.length > 0 && (
                <div className="rounded-2xl border border-border bg-background/80 backdrop-blur-xl p-3">
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-2">Sector Heatmap</div>
                  <div className="grid grid-cols-2 gap-1.5">
                    {heat.slice(0, 6).map((c) => (
                      <div key={c.origin + c.destination} className={`rounded-lg border p-2 ${relColor(c.relative)} hover:scale-[1.02] transition-transform cursor-pointer`}>
                        <div className="font-mono text-[10px] font-semibold">{c.origin}–{c.destination}</div>
                        <div className="font-mono text-sm font-bold">₹{Number(c.avg_fare).toLocaleString('en-IN', { maximumFractionDigits: 0 })}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <PriceSourcesPanel sources={priceSources} loading={priceSourcesLoading} origin={debouncedOrigin} destination={debouncedDestination} />
            </div>

            <div className="flex flex-col gap-3 w-full lg:w-96 shrink-0">
              <LogsPanel logs={logs} onClear={() => setLogs([])} />

              <DatePricePanel dates={datePrices} loading={datePricesLoading} />

              {showElasticity && (
                <div className="rounded-2xl border border-border bg-background/80 backdrop-blur-xl p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[10px] text-muted-foreground uppercase tracking-wider">Elasticity</span>
                    <Select
                      value={routeId}
                      onChange={setRouteId}
                      options={routes.map((r) => ({ value: String(r.route_id), label: `${r.origin}–${r.destination}` }))}
                      className="h-7 text-[10px] w-28"
                    />
                  </div>
                  <ResponsiveContainer width="100%" height={120}>
                    <LineChart data={curve}>
                      <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="window" tick={{ ...TICK, fontSize: 9 }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ ...TICK, fontSize: 9 }} domain={['auto', 'auto']} axisLine={false} tickLine={false} width={40} />
                      <Tooltip content={<ChartTip />} />
                      <Line type="monotone" dataKey="avg_fare" stroke="#a78bfa" strokeWidth={2} dot={{ r: 3, fill: '#a78bfa' }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}

              {showBacktest && (
                <div className="rounded-2xl border border-border bg-background/80 backdrop-blur-xl p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[10px] text-muted-foreground uppercase tracking-wider">Trend</span>
                    <div className="flex items-center gap-2">
                      <Tabs value={gran} onChange={setGran} options={['daily', 'weekly', 'monthly']} />
                      <button
                        onClick={handleExport}
                        className="text-[10px] text-muted-foreground hover:text-foreground transition-colors px-2 py-1 rounded border border-border"
                        aria-label="Export data as CSV"
                      >
                        Export
                      </button>
                      <button
                        onClick={() => setShowTable(!showTable)}
                        className="text-[10px] text-muted-foreground hover:text-foreground transition-colors px-2 py-1 rounded border border-border"
                        aria-label="Toggle table view"
                      >
                        {showTable ? 'Chart' : 'Table'}
                      </button>
                    </div>
                  </div>
                  {showTable ? (
                    <div className="h-[140px] overflow-y-auto">
                      <table className="w-full text-[10px]">
                        <thead className="sticky top-0 bg-background">
                          <tr className="text-muted-foreground">
                            <th className="text-left p-1">Date</th>
                            <th className="text-right p-1">Value</th>
                          </tr>
                        </thead>
                        <tbody>
                          {series.slice(-20).reverse().map(p => (
                            <tr key={p.index_date} className="border-t border-border/50">
                              <td className="p-1 font-mono">{p.index_date}</td>
                              <td className="p-1 text-right font-mono">{p.index_value.toFixed(2)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <ResponsiveContainer width="100%" height={140}>
                      <AreaChart data={series.map((p) => ({ date: p.index_date.slice(5), value: p.index_value }))}>
                        <defs>
                          <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#3291ff" stopOpacity={0.4} />
                            <stop offset="100%" stopColor="#3291ff" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="date" tick={{ ...TICK, fontSize: 9 }} minTickGap={28} axisLine={false} tickLine={false} />
                        <YAxis tick={{ ...TICK, fontSize: 9 }} domain={['auto', 'auto']} axisLine={false} tickLine={false} width={36} />
                        <Tooltip content={<ChartTip />} />
                        <ReferenceLine y={100} stroke="#52525b" strokeDasharray="4 4" />
                        <Area type="monotone" dataKey="value" stroke="#3291ff" strokeWidth={2} fill="url(#g)" />
                      </AreaChart>
                    </ResponsiveContainer>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-[1000] flex gap-2 flex-wrap justify-center">
        {[
          { label: 'Stats', active: showStats, toggle: () => setShowStats(!showStats) },
          { label: 'Heatmap', active: showHeatmap, toggle: () => setShowHeatmap(!showHeatmap) },
          { label: 'Sources', active: true, toggle: () => {} },
          { label: 'Dates', active: true, toggle: () => {} },
          { label: 'Elasticity', active: showElasticity, toggle: () => setShowElasticity(!showElasticity) },
          { label: 'Trend', active: showBacktest, toggle: () => setShowBacktest(!showBacktest) },
        ].map((btn) => (
          <button
            key={btn.label}
            onClick={btn.toggle}
            className={`rounded-full px-4 py-1.5 text-xs font-medium transition-all ${
              btn.active
                ? 'bg-accent/20 text-accent border border-accent/30'
                : 'bg-background/40 text-muted-foreground border border-border hover:text-foreground'
            } backdrop-blur-xl`}
          >
            {btn.label}
          </button>
        ))}
      </div>

      {err && (
        <div className="fixed top-20 left-1/2 -translate-x-1/2 z-[1000]">
          <div className="rounded-xl border border-red-500/30 bg-red-500/10 backdrop-blur-xl px-4 py-2 text-sm text-red-300">
            {err}
          </div>
        </div>
      )}
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <AppInner />
    </ErrorBoundary>
  );
}
