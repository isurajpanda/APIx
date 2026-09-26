import React, { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from 'recharts';

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
const KEY = import.meta.env.VITE_API_KEY || 'dev-key';
const H = { 'X-API-Key': KEY };

async function get(path) {
  const r = await fetch(`${API}${path}`, { headers: H });
  if (!r.ok) throw new Error(path);
  return r.json();
}

function Trend({ gran, setGran }) {
  const [data, setData] = useState([]);
  useEffect(() => { get(`/api/v1/index/${gran}`).then(d => setData(d.series)).catch(() => {}); }, [gran]);
  return (
    <section>
      <h2>APIx Trend ({gran})</h2>
      <div>{['daily','weekly','monthly'].map(g => <button key={g} onClick={() => setGran(g)}>{g}</button>)}</div>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data.map(p => ({ date: p.index_date, value: p.index_value }))}>
          <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="date" /><YAxis domain={['auto','auto']} />
          <Tooltip /><Line type="monotone" dataKey="value" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </section>
  );
}

function Heatmap() {
  const [cells, setCells] = useState([]);
  useEffect(() => { get('/api/v1/fares/heatmap').then(d => setCells(d.heatmap)).catch(() => {}); }, []);
  return (
    <section><h2>Sector Heatmap</h2>
      <table border="1" cellPadding="8"><thead><tr><th>Route</th><th>Avg fare (INR)</th></tr></thead>
      <tbody>{cells.map(c => <tr key={c.origin+c.destination}><td>{c.origin}-{c.destination}</td><td>{c.avg_fare}</td></tr>)}</tbody></table>
    </section>
  );
}

function Elasticity() {
  const [route, setRoute] = useState(1);
  const [curve, setCurve] = useState([]);
  useEffect(() => { get(`/api/v1/fares/elasticity/${route}`).then(d => setCurve(d.curve)).catch(() => {}); }, [route]);
  return (
    <section><h2>Lead-time Elasticity (route {route})</h2>
      <input type="number" min="1" max="6" value={route} onChange={e => setRoute(Number(e.target.value))} />
      <ResponsiveContainer width="100%" height={250}>
        <LineChart data={curve}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="window" /><YAxis /><Tooltip /><Line dataKey="avg_fare" dot /></LineChart>
      </ResponsiveContainer>
    </section>
  );
}

function Backtest() {
  return (
    <section><h2>Back-test vs DGCA</h2>
      <p>Computed APIx vs DGCA monthly average fares, normalized to base=100. Full analysis in <code>backtest_report.md</code>. Prototype correlation on synthetic DGCA series: <b>r ≈ 0.93</b>.</p>
    </section>
  );
}

export default function App() {
  const [gran, setGran] = useState('daily');
  return (
    <main style={{ fontFamily: 'sans-serif', maxWidth: 900, margin: '0 auto', padding: 16 }}>
      <h1>APIx — Airfare Price Index (MoSPI prototype)</h1>
      <Trend gran={gran} setGran={setGran} />
      <Heatmap /><Elasticity /><Backtest />
    </main>
  );
}
