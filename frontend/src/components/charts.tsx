// Dependency-free SVG charts (small, themeable via CSS variables, keyboard/hover friendly).

import { useMemo, useRef, useState, type ReactNode } from "react";

interface Pad { l: number; r: number; t: number; b: number }
const W = 640;

function niceMax(v: number): number {
  if (v <= 0) return 1;
  const pow = 10 ** Math.floor(Math.log10(v));
  const n = v / pow;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * pow;
}

function Tip({ x, y, children }: { x: number; y: number; children: ReactNode }) {
  return <div className="chart-tip" style={{ left: `${x}%`, top: y }}>{children}</div>;
}

/** Line/area chart over evenly spaced points. */
export function AreaChart({ data, labels, height = 190, color = "var(--accent)", format = (v: number) => String(Math.round(v)), tooltip, unit }: {
  data: (number | null)[]; labels: string[]; height?: number; color?: string; format?: (v: number) => string; tooltip?: (i: number) => ReactNode; unit?: string;
}) {
  const pad: Pad = { l: 44, r: 12, t: 12, b: 24 };
  const [hover, setHover] = useState<number | null>(null);
  const ref = useRef<SVGSVGElement>(null);
  const values = data.filter((v): v is number => v !== null);
  const max = niceMax(Math.max(...values, 1));
  const iw = W - pad.l - pad.r, ih = height - pad.t - pad.b;
  const x = (i: number) => pad.l + (data.length <= 1 ? iw / 2 : (i / (data.length - 1)) * iw);
  const y = (v: number) => pad.t + ih - (v / max) * ih;

  const pts = data.map((v, i) => (v === null ? null : ([x(i), y(v)] as const)));
  const segments: (readonly [number, number])[][] = [];
  for (const p of pts) { if (p === null) segments.push([]); else (segments[segments.length - 1] ?? segments[segments.push([]) - 1]).push(p); }
  const line = (seg: (readonly [number, number])[]) => seg.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const gid = useMemo(() => `g${Math.random().toString(36).slice(2, 8)}`, []);

  const onMove = (e: React.MouseEvent) => {
    const rect = ref.current!.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    const idx = Math.round(((px - pad.l) / iw) * (data.length - 1));
    setHover(Math.max(0, Math.min(data.length - 1, idx)));
  };
  const ticks = [0, 0.5, 1].map((t) => t * max);
  const labelEvery = Math.max(1, Math.ceil(labels.length / 7));

  if (!values.length) return <div className="empty" style={{ padding: 40 }}><span className="faint">No data yet</span></div>;
  return (
    <div style={{ position: "relative" }}>
      <svg ref={ref} className="chart" viewBox={`0 0 ${W} ${height}`} role="img" onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        <defs><linearGradient id={gid} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={color} stopOpacity="0.32" /><stop offset="1" stopColor={color} stopOpacity="0" /></linearGradient></defs>
        {ticks.map((t) => (
          <g key={t}><line className="grid" x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} /><text x={pad.l - 8} y={y(t) + 4} textAnchor="end">{format(t)}{unit}</text></g>
        ))}
        {segments.filter((s) => s.length).map((seg, i) => (
          <g key={i}>
            {seg.length > 1 && <path d={`${line(seg)} L${seg[seg.length - 1][0]},${pad.t + ih} L${seg[0][0]},${pad.t + ih} Z`} fill={`url(#${gid})`} />}
            <path d={line(seg)} fill="none" stroke={color} strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" />
          </g>
        ))}
        {pts.map((p, i) => p && <circle key={i} cx={p[0]} cy={p[1]} r={hover === i ? 5 : data.length > 40 ? 0 : 3} fill="var(--surface)" stroke={color} strokeWidth="2" />)}
        {labels.map((l, i) => i % labelEvery === 0 && <text key={i} x={x(i)} y={height - 4} textAnchor="middle">{l}</text>)}
        {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={pad.t} y2={pad.t + ih} stroke="var(--border-strong)" />}
      </svg>
      {hover !== null && data[hover] !== null && <Tip x={(x(hover) / W) * 100} y={y(data[hover]!) / height * height}>{tooltip ? tooltip(hover) : <b>{format(data[hover]!)}{unit}</b>}</Tip>}
    </div>
  );
}

/** Stacked bar chart (e.g. passed vs failed per run/day). */
export function StackedBars({ series, labels, height = 190, tooltip }: {
  series: { name: string; color: string; values: number[] }[]; labels: string[]; height?: number; tooltip?: (i: number) => ReactNode;
}) {
  const pad: Pad = { l: 36, r: 8, t: 12, b: 24 };
  const [hover, setHover] = useState<number | null>(null);
  const n = labels.length;
  const totals = labels.map((_, i) => series.reduce((s, x) => s + (x.values[i] ?? 0), 0));
  const max = niceMax(Math.max(...totals, 1));
  const iw = W - pad.l - pad.r, ih = height - pad.t - pad.b;
  const slot = iw / Math.max(n, 1), bw = Math.min(30, slot * 0.66);
  const labelEvery = Math.max(1, Math.ceil(n / 8));
  if (!totals.some(Boolean)) return <div className="empty" style={{ padding: 40 }}><span className="faint">No data yet</span></div>;
  return (
    <div style={{ position: "relative" }}>
      <svg className="chart" viewBox={`0 0 ${W} ${height}`} role="img" onMouseLeave={() => setHover(null)}>
        {[0, 0.5, 1].map((t) => <g key={t}><line className="grid" x1={pad.l} x2={W - pad.r} y1={pad.t + ih - t * ih} y2={pad.t + ih - t * ih} /><text x={pad.l - 6} y={pad.t + ih - t * ih + 4} textAnchor="end">{Math.round(t * max)}</text></g>)}
        {labels.map((l, i) => {
          const cx = pad.l + slot * i + slot / 2;
          let acc = 0;
          return (
            <g key={i} onMouseEnter={() => setHover(i)} opacity={hover === null || hover === i ? 1 : 0.55}>
              <rect x={pad.l + slot * i} y={pad.t} width={slot} height={ih} fill="transparent" />
              {series.map((s) => {
                const v = s.values[i] ?? 0, h = (v / max) * ih, yy = pad.t + ih - acc - h;
                acc += h;
                return v ? <rect key={s.name} x={cx - bw / 2} y={yy} width={bw} height={h} rx={3} fill={s.color} /> : null;
              })}
              {i % labelEvery === 0 && <text x={cx} y={height - 4} textAnchor="middle">{l}</text>}
            </g>
          );
        })}
      </svg>
      {hover !== null && <Tip x={((pad.l + slot * hover + slot / 2) / W) * 100} y={pad.t + 20}>{tooltip ? tooltip(hover) : <b>{totals[hover]}</b>}</Tip>}
      <div className="legend" style={{ marginTop: 6 }}>{series.map((s) => <span key={s.name}><i style={{ background: s.color }} />{s.name}</span>)}</div>
    </div>
  );
}

/** Tiny inline sparkline. */
export function Sparkline({ data, color = "var(--accent)", width = 96, height = 28 }: { data: number[]; color?: string; width?: number; height?: number }) {
  if (data.length < 2) return null;
  const max = Math.max(...data), min = Math.min(...data), span = max - min || 1;
  const d = data.map((v, i) => `${i ? "L" : "M"}${(i / (data.length - 1)) * width},${height - 3 - ((v - min) / span) * (height - 6)}`).join(" ");
  return <svg width={width} height={height} aria-hidden><path d={d} fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

/** Donut ring for a percentage (pass-rate). */
export function Ring({ value, size = 76, stroke = 8, color = "var(--success)" }: { value: number | null; size?: number; stroke?: number; color?: string }) {
  const r = (size - stroke) / 2, c = 2 * Math.PI * r, v = value ?? 0;
  return (
    <svg width={size} height={size} role="img" aria-label={value === null ? "No data" : `${value}%`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-2)" strokeWidth={stroke} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round" strokeDasharray={`${(v / 100) * c} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`} style={{ transition: "stroke-dasharray 0.6s var(--ease)" }} />
      <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle" style={{ fill: "var(--text)", fontWeight: 700, fontSize: size / 4.2 }}>{value === null ? "—" : `${Math.round(v)}%`}</text>
    </svg>
  );
}
