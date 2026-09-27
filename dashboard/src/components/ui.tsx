import React from 'react';
import { cn } from '../lib/utils';
import type { SelectOption } from '../types';

export function Card({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div className={cn(
      'rounded-2xl border border-border bg-background/80 backdrop-blur-xl shadow-2xl',
      className
    )}>
      {children}
    </div>
  );
}

export function CardHeader({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn('flex flex-col space-y-1.5 p-4 pb-3', className)}>{children}</div>;
}

export function CardTitle({ className, children }: { className?: string; children: React.ReactNode }) {
  return <h3 className={cn('text-sm font-medium text-muted-foreground', className)}>{children}</h3>;
}

export function CardContent({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn('p-4 pt-0', className)}>{children}</div>;
}

export function Badge({ className, children, tone = 'default' }: { className?: string; children: React.ReactNode; tone?: 'default' | 'green' | 'red' | 'blue' }) {
  const tones = {
    default: 'bg-secondary text-secondary-foreground',
    green: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    red: 'bg-red-500/10 text-red-400 border-red-500/20',
    blue: 'bg-accent/10 text-accent border-accent/20',
  };
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium',
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Tabs({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: string[] }) {
  return (
    <div className="inline-flex h-8 items-center justify-center rounded-lg bg-muted p-1">
      {options.map((o) => (
        <button
          key={o}
          onClick={() => onChange(o)}
          className={cn(
            'inline-flex items-center justify-center whitespace-nowrap rounded-md px-2.5 py-1 text-xs font-medium transition-all',
            value === o
              ? 'bg-background text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {o}
        </button>
      ))}
    </div>
  );
}

export function Select({ value, onChange, options, className }: { value: string; onChange: (v: string) => void; options: SelectOption[]; className?: string }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={cn(
        'h-8 rounded-md border border-input bg-background px-2 text-xs text-foreground outline-none',
        'focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background transition-all',
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

export function Stat({ label, value, sub, trend }: { label: string; value: React.ReactNode; sub?: string; trend?: number | null }) {
  return (
    <Card className="group">
      <CardHeader className="p-3 pb-2">
        <CardTitle className="text-[10px] uppercase tracking-wider">{label}</CardTitle>
      </CardHeader>
      <CardContent className="p-3 pt-0">
        <div className="text-2xl font-bold tracking-tight text-foreground">
          {value}
        </div>
        {sub && <p className="mt-0.5 text-[10px] text-muted-foreground">{sub}</p>}
        {trend !== undefined && trend !== null && (
          <Badge tone={trend > 0 ? 'red' : 'green'} className="mt-1.5">
            {trend > 0 ? '▲' : '▼'} {Math.abs(trend).toFixed(2)}%
          </Badge>
        )}
      </CardContent>
    </Card>
  );
}
