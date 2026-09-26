import React, { useEffect, useMemo, useState } from 'react';
import {
  Area, AreaChart, CartesianGrid, Cell, Legend, Line, LineChart,
  ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { Badge, Card, CardContent, CardHeader, CardTitle, Select, Stat, Tabs } from './components/ui.jsx';

const API = import.meta.env.VITE_API_URL ?? '';
const KEY = import.meta.env.VITE_API_KEY || 'dev-key';
const H = { 'X-API-Key': KEY };

async function get(path) {
  const r = await fetch(`${API}${path}`, { headers: H });
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}

const GRID = '#1c1c1f';
const TICK = { fill: '#71717a', fontSize: 11 };

function ChartTip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs shadow-xl">
      <div className="mb-1 font-mono text-muted">{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full" style={{ background: p.color || p.stroke }} />
          <span className="text-muted">{p.name}:</span>
          <span className="font-mono font-medium text-white">{Number(p.value).toLocaleString('en-IN')}</span>
        </div>
      ))}
    </div>
  );
}

function Navbar({ health }) {
  return (
    <header className="sticky top-0 z-10 border-b border-border bg-background/80 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
        <div className="flex items-center gap-2.5">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-white text-sm font-bold text-black">▲</span>
          <span className="font-semibold tracking-tight">APIx</span>
          <Badge tone="blue" className="ml-1">MoSPI prototype</Badge>
        </div>
        <div className="flex items-center gap-3 text-xs text-muted">
          <span className="flex items-center gap-1.5">
            <span className={`h-2 w-2 rounded-full ${health?.db === 'connected' ? 'bg-emerald-400' : 'bg-red-400'}`} />
            {health?.db === 'connected' ? 'DB connected' : 'DB unreachable'}
          </span>
          <a href="/docs" className="rounded-md border border-border px-2.5 py-1 text-white hover:bg-zinc-900">
            API docs
          </a>
        </div>
      </div>
    </header>
  );
}

function relColor(r) {
  // green (cheap) -> amber -> red (expensive), relative to base period
  if (r < 0.98) return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30';
  if (r < 1.03) return 'bg-amber-500/15 text-amber-300 border-amber-500/30';
  return 'bg-red-500/15 text-red-300 border-red-500/30';
}

export default function App() {
  const [gran, setGran] = useState('daily');
  const [series, setSeries] = useState([]);
  const [weekly, setWeekly] = useState([]);
  const [heat, setHeat] = useState([]);
  const [heatSrc, setHeatSrc] = useState('');
  const [routes, setRoutes] = useState([]);
  const [routeId, setRouteId] = useState('1');
  const [curve, setCurve] = useState([]);
  const [health, setHealth] = useState(null);
  const [err, setErr] = useState('');

  useEffect(() => {
    get('/api/v1/health').then(setHealth).catch((e) => setErr(String(e)));
    get('/api/v1/index/weekly').then((d) => setWeekly(d.series)).catch(() => {});
    get('/api/v1/fares/heatmap', ).then((d) => { setHeat(d.heatmap); setHeatSrc(d.source || ''); }).catch(() => {});
    get('/api/v1/routes').then((d) => setRoutes(d.routes)).catch(() => {});
  }, []);
  useEffect(() => {
    get(`/api/v1/index/${gran}`).then((d) => setSeries(d.series)).catch(() => {});
  }, [gran]);
  useEffect(() => {
    get(`/api/v1/fares/elasticity/${routeId}`).then((d) => setCurve(d.curve)).catch(() => {});
  }, [routeId]);

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

  const routeLabel = (id) => {
    const r = routes.find((x) => String(x.route_id) === String(id));
    return r ? `${r.origin}–${r.destination}` : `Route ${id}`;
  };

  return (
    <div className="min-h-screen bg-background font-sans text-zinc-50">
      <Navbar health={health} />
      <main className="mx-auto max-w-6xl space-y-6 px-6 py-8">
        {err && (
          <Card className="border-red-500/40">
            <CardContent className="pt-6 text-sm text-red-300">API error: {err} — is the backend running?</CardContent>
          </Card>
        )}

        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Airfare Price Index</h1>
          <p className="mt-1 text-sm text-muted">
            Laspeyres-style index over {routes.length || '…'} DGCA-weighted domestic sectors · base = 100
            {health?.last_scrape && (
              <span className="font-mono"> · last scrape {String(health.last_scrape).slice(0, 16).replace('T', ' ')}</span>
            )}
          </p>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Current index" value={stats.last?.toFixed(2) ?? '…'} sub={`${gran} · v1.0 methodology`} />
          <Stat label="Change (period)" value={`${stats.chg >= 0 ? '+' : ''}${(stats.chg ?? 0).toFixed(2)}%`} trend={stats.chg} />
          <Stat label="Change (30d)" value={`${stats.chg30 >= 0 ? '+' : ''}${(stats.chg30 ?? 0).toFixed(2)}%`} trend={stats.chg30} />
          <Stat label="Observations" value={stats.n ?? '…'} sub={`${routes.length} routes · 5 lead-time windows`} />
        </div>

        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Index trend</CardTitle>
            <Tabs value={gran} onChange={setGran} options={['daily', 'weekly', 'monthly']} />
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={320}>
              <AreaChart data={series.map((p) => ({ date: p.index_date.slice(5), value: p.index_value }))}>
                <defs>
                  <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3291ff" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#3291ff" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tick={TICK} minTickGap={28} axisLine={false} tickLine={false} />
                <YAxis tick={TICK} domain={['auto', 'auto']} axisLine={false} tickLine={false} width={48} />
                <Tooltip content={<ChartTip />} />
                <ReferenceLine y={100} stroke="#52525b" strokeDasharray="4 4" />
                <Area type="monotone" dataKey="value" name="APIx" stroke="#3291ff" strokeWidth={2} fill="url(#g)" />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>Sector heatmap — latest fares vs base</CardTitle>
              {heatSrc === 'db' && <Badge tone="green">live DB</Badge>}
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {heat.map((c) => (
                  <div key={c.origin + c.destination} className={`rounded-lg border p-3 ${relColor(c.relative)}`}>
                    <div className="font-mono text-sm font-semibold">{c.origin}–{c.destination}</div>
                    <div className="mt-1 font-mono text-lg">₹{Number(c.avg_fare).toLocaleString('en-IN', { maximumFractionDigits: 0 })}</div>
                    <div className="font-mono text-xs opacity-80">×{Number(c.relative).toFixed(3)} vs base</div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>Lead-time elasticity</CardTitle>
              <Select
                value={routeId}
                onChange={setRouteId}
                options={routes.map((r) => ({ value: String(r.route_id), label: `${r.origin}–${r.destination}` }))}
              />
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={262}>
                <LineChart data={curve}>
                  <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="window" tick={TICK} axisLine={false} tickLine={false} label={{ value: 'days ahead', position: 'insideBottom', offset: -2, fill: '#71717a', fontSize: 11 }} />
                  <YAxis tick={TICK} domain={['auto', 'auto']} axisLine={false} tickLine={false} width={56} />
                  <Tooltip content={<ChartTip />} />
                  <Line type="monotone" dataKey="avg_fare" name={`${routeLabel(routeId)} fare`} stroke="#a78bfa" strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
              <p className="mt-2 text-xs text-muted">
                Booking T+45 vs T+1 saves ≈
                {curve.length
                  ? ` ${(((curve[0].avg_fare - curve[curve.length - 1].avg_fare) / curve[0].avg_fare) * 100).toFixed(1)}%`
                  : ' …'} on {routeLabel(routeId)}.
              </p>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <div>
              <CardTitle>Back-test — daily index vs 7-day trend</CardTitle>
              <p className="mt-1 text-xs text-muted">45 days of pipeline data · DGCA benchmark status in <span className="font-mono">backtest_report.md</span></p>
            </div>
            <Badge tone="blue">APIx internal back-test</Badge>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={backtest}>
                <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tick={TICK} minTickGap={40} axisLine={false} tickLine={false}
                  tickFormatter={(d) => String(d).slice(5)} />
                <YAxis tick={TICK} domain={['auto', 'auto']} axisLine={false} tickLine={false} width={48} />
                <Tooltip content={<ChartTip />} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line type="monotone" dataKey="daily" name="APIx daily" stroke="#3291ff" strokeWidth={1.5} dot={false} />
                <Line type="monotone" dataKey="trend" name="7-day trend" stroke="#34d399" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <footer className="flex items-center justify-between pb-4 text-xs text-muted">
          <span>APIx · MoSPI prototype · methodology v1.0</span>
          <span className="font-mono">GET /api/v1/index/daily · X-API-Key</span>
        </footer>
      </main>
    </div>
  );
}
