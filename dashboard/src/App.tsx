import { useEffect, useMemo, useState, useCallback, useRef } from 'react';
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

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`);
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}

async function post<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`, { method: 'POST' });
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
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
}

function FloatingTopBar({ health, airports, selectedOrigin, selectedDestination, onSelectOrigin, onSelectDestination, onRefresh, refreshing, routeFare }: FloatingTopBarProps) {
  return (
    <div className="fixed top-4 left-1/2 -translate-x-1/2 z-[1000] w-[95%] max-w-4xl">
      <div className="rounded-2xl border border-border bg-background/80 backdrop-blur-xl shadow-2xl px-6 py-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 flex-1">
            <Select
              value={selectedOrigin || ''}
              onChange={onSelectOrigin}
              options={[
                { value: '', label: 'From' },
                ...airports.map(a => ({ value: a.code, label: `${a.city} (${a.code})` }))
              ]}
              className="w-40"
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
              className="w-40"
            />
            {routeFare && routeFare.avg_fare && (
              <div className="rounded-lg border border-accent/30 bg-accent/10 px-3 py-1.5 ml-2">
                <span className="text-sm font-bold text-accent">₹{Number(routeFare.avg_fare).toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
              </div>
            )}
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={onRefresh}
              disabled={refreshing}
              className="flex items-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-xs text-foreground hover:bg-accent/10 transition-all disabled:opacity-50"
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
}

function PriceSourcesPanel({ sources, loading }: PriceSourcesPanelProps) {
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
        {sources.map((s, i) => (
          <div key={i} className="flex items-center justify-between rounded-lg border border-border bg-background/50 px-3 py-2">
            <div>
              <div className="text-xs font-medium text-foreground">{s.source}</div>
              <div className="text-[10px] text-muted-foreground">{s.carrier} · {s.count} obs</div>
            </div>
            <div className="text-right">
              <div className="text-sm font-bold text-foreground">₹{Number(s.avg_fare).toLocaleString('en-IN', { maximumFractionDigits: 0 })}</div>
              <div className="text-[10px] text-muted-foreground">₹{Number(s.min_fare).toLocaleString('en-IN', { maximumFractionDigits: 0 })} – ₹{Number(s.max_fare).toLocaleString('en-IN', { maximumFractionDigits: 0 })}</div>
            </div>
          </div>
        ))}
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
        <div className="text-xs text-muted-foreground">Select a route to see date pricing</div>
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

export default function App() {
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

  useEffect(() => {
    get<Health>('/api/v1/health').then(setHealth).catch((e) => setErr(String(e)));
    get<{ series: SeriesPoint[] }>('/api/v1/index/weekly').then((d) => setWeekly(d.series)).catch(() => {});
    get<{ heatmap: HeatmapEntry[]; source: string }>('/api/v1/fares/heatmap').then((d) => { setHeat(d.heatmap); setHeatSrc(d.source || ''); }).catch(() => {});
    get<{ routes: Route[] }>('/api/v1/routes').then((d) => setRoutes(d.routes)).catch(() => {});
    get<{ airports: Airport[] }>('/api/v1/airports').then((d) => setAirports(d.airports)).catch(() => {});
  }, []);

  useEffect(() => {
    get<{ series: SeriesPoint[] }>(`/api/v1/index/${gran}`).then((d) => setSeries(d.series)).catch(() => {});
  }, [gran]);

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
    fetchRouteFare(selectedOrigin, selectedDestination);
    fetchPriceSources(selectedOrigin, selectedDestination);
    fetchDatePrices(selectedOrigin, selectedDestination);
  }, [selectedOrigin, selectedDestination, fetchRouteFare, fetchPriceSources, fetchDatePrices]);

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
      if (selectedOrigin && selectedDestination) {
        fetchRouteFare(selectedOrigin, selectedDestination);
        fetchPriceSources(selectedOrigin, selectedDestination);
        fetchDatePrices(selectedOrigin, selectedDestination);
      }
    } catch (e) {
      setLogs(prev => [...prev, { ts: new Date().toISOString(), level: 'ERROR', msg: `Refresh failed: ${(e as Error).message}` }]);
    } finally {
      setRefreshing(false);
    }
  }, [selectedOrigin, selectedDestination, fetchRouteFare, fetchPriceSources, fetchDatePrices]);

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
          />
        </div>

        <div className="flex-1 flex items-end justify-between p-4 gap-4 pointer-events-none">
          <div className="flex flex-col gap-3 pointer-events-auto w-72">
            {showStats && (
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-xl border border-border bg-background/80 backdrop-blur-xl p-3">
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Index</div>
                  <div className="text-xl font-bold text-foreground mt-0.5">{stats.last?.toFixed(2) ?? '—'}</div>
                </div>
                <div className="rounded-xl border border-border bg-background/80 backdrop-blur-xl p-3">
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Change</div>
                  <div className={`text-xl font-bold mt-0.5 ${(stats.chg ?? 0) >= 0 ? 'text-red-400' : 'text-emerald-400'}`}>
                    {(stats.chg ?? 0) >= 0 ? '+' : ''}{(stats.chg ?? 0).toFixed(2)}%
                  </div>
                </div>
                <div className="rounded-xl border border-border bg-background/80 backdrop-blur-xl p-3">
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wider">30d</div>
                  <div className={`text-xl font-bold mt-0.5 ${(stats.chg30 ?? 0) >= 0 ? 'text-red-400' : 'text-emerald-400'}`}>
                    {(stats.chg30 ?? 0) >= 0 ? '+' : ''}{(stats.chg30 ?? 0).toFixed(2)}%
                  </div>
                </div>
                <div className="rounded-xl border border-border bg-background/80 backdrop-blur-xl p-3">
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
                    <div key={c.origin + c.destination} className={`rounded-lg border p-2 ${relColor(c.relative)}`}>
                      <div className="font-mono text-[10px] font-semibold">{c.origin}–{c.destination}</div>
                      <div className="font-mono text-sm font-bold">₹{Number(c.avg_fare).toLocaleString('en-IN', { maximumFractionDigits: 0 })}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <PriceSourcesPanel sources={priceSources} loading={priceSourcesLoading} />
          </div>

          <div className="flex flex-col gap-3 pointer-events-auto w-80">
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
                  <Tabs value={gran} onChange={setGran} options={['daily', 'weekly', 'monthly']} />
                </div>
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
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-[1000] flex gap-2">
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
