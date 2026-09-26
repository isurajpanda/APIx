import React from 'react';
import { cn } from '../lib/utils.js';

export function Card({ className, children }) {
  return (
    <div className={cn('rounded-xl border border-border bg-surface shadow-sm', className)}>
      {children}
    </div>
  );
}

export function CardHeader({ className, children }) {
  return <div className={cn('flex flex-col space-y-1.5 p-6 pb-3', className)}>{children}</div>;
}

export function CardTitle({ className, children }) {
  return <h3 className={cn('text-sm font-medium text-muted', className)}>{children}</h3>;
}

export function CardContent({ className, children }) {
  return <div className={cn('p-6 pt-0', className)}>{children}</div>;
}

export function Badge({ className, children, tone = 'default' }) {
  const tones = {
    default: 'bg-zinc-800 text-zinc-200',
    green: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    red: 'bg-red-500/15 text-red-400 border-red-500/30',
    blue: 'bg-[#3291ff]/15 text-[#3291ff] border-[#3291ff]/30',
  };
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border border-transparent px-2.5 py-0.5 text-xs font-medium',
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Tabs({ value, onChange, options }) {
  return (
    <div className="inline-flex h-9 items-center justify-center rounded-lg bg-zinc-900 p-1 text-muted">
      {options.map((o) => (
        <button
          key={o}
          onClick={() => onChange(o)}
          className={cn(
            'inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1 text-sm font-medium transition-all',
            value === o ? 'bg-zinc-800 text-white shadow' : 'hover:text-white',
          )}
        >
          {o}
        </button>
      ))}
    </div>
  );
}

export function Select({ value, onChange, options, className }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={cn(
        'h-9 rounded-md border border-border bg-surface px-3 text-sm text-white outline-none focus:border-accent',
        className,
      )}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

export function Stat({ label, value, sub, trend }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-3xl font-semibold tracking-tight">{value}</div>
        {sub && <p className="mt-1 text-xs text-muted">{sub}</p>}
        {trend && (
          <Badge tone={trend > 0 ? 'red' : 'green'} className="mt-2">
            {trend > 0 ? '▲' : '▼'} {Math.abs(trend).toFixed(2)}%
          </Badge>
        )}
      </CardContent>
    </Card>
  );
}
