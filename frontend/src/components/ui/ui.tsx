import { Check, Copy, Plus, Trash2, type LucideIcon } from "lucide-react";
import { useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { NavLink } from "react-router-dom";
import { ApiError } from "@/api/client";
import type { ResultStatus, RunStatus, Verdict } from "@/api/types";

export const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(" ");

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    const first = e.details?.[0];
    return first ? `${first.field ? first.field + ": " : ""}${first.message}` : e.message;
  }
  return e instanceof Error ? e.message : "Something went wrong";
}

// ---------------------------------------------------------------- buttons
type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger"; size?: "sm" | "md"; icon?: LucideIcon; loading?: boolean; iconOnly?: boolean; block?: boolean;
};
export function Button({ variant = "secondary", size = "md", icon: Icon, loading, iconOnly, block, className, children, disabled, ...rest }: BtnProps) {
  return (
    <button
      {...rest}
      type={rest.type ?? "button"}
      disabled={disabled || loading}
      className={cx("btn", variant !== "secondary" && variant, size === "sm" && "sm", iconOnly && "icon", iconOnly && size === "sm" && "sm", block && "block", className)}
    >
      {loading ? <span className="spinner" /> : Icon ? <Icon size={size === "sm" ? 14 : 16} /> : null}
      {!iconOnly && children}
    </button>
  );
}

export const Spinner = () => <span className="spinner" role="status" aria-label="Loading" />;

// ---------------------------------------------------------------- form controls
export function Field({ label, hint, error, children, className }: { label?: string; hint?: ReactNode; error?: string | null; children: ReactNode; className?: string }) {
  return (
    <div className={cx("field", className)}>
      {label && <label>{label}</label>}
      {children}
      {error ? <span className="error-text">{error}</span> : hint ? <span className="hint">{hint}</span> : null}
    </div>
  );
}
export const Input = ({ className, invalid, ...p }: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) => <input {...p} className={cx("input", invalid && "invalid", className)} />;
export const Textarea = ({ className, invalid, mono, ...p }: TextareaHTMLAttributes<HTMLTextAreaElement> & { invalid?: boolean; mono?: boolean }) => <textarea {...p} className={cx("textarea", mono && "code", invalid && "invalid", className)} />;
export const Select = ({ className, ...p }: SelectHTMLAttributes<HTMLSelectElement>) => <select {...p} className={cx("select", className)} />;
export function Switch({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label?: string; disabled?: boolean }) {
  return (
    <label className="row" style={{ cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.5 : 1 }}>
      <span className="switch">
        <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} aria-label={label} />
        <span />
      </span>
      {label && <span>{label}</span>}
    </label>
  );
}

/** Editable list of key/value pairs (headers, query params, variables). */
export function KeyValueEditor({ value, onChange, keyPlaceholder = "name", valuePlaceholder = "value", disabled, secret }: {
  value: Record<string, string>; onChange: (v: Record<string, string>) => void; keyPlaceholder?: string; valuePlaceholder?: string; disabled?: boolean; secret?: boolean;
}) {
  // Keep rows as an array so empty/duplicate keys don't collapse while typing.
  const [rows, setRows] = useState<[string, string][]>(() => Object.entries(value));
  const commit = (next: [string, string][]) => {
    setRows(next);
    onChange(Object.fromEntries(next.filter(([k]) => k.trim())));
  };
  return (
    <div className="stack sm">
      {rows.map(([k, v], i) => (
        <div className="kv-row" key={i}>
          <Input className="sm" placeholder={keyPlaceholder} value={k} disabled={disabled} onChange={(e) => commit(rows.map((r, j) => (j === i ? [e.target.value, r[1]] : r)))} aria-label={keyPlaceholder} />
          <Input className="sm" placeholder={valuePlaceholder} value={v} disabled={disabled} type={secret ? "password" : "text"} autoComplete="off" onChange={(e) => commit(rows.map((r, j) => (j === i ? [r[0], e.target.value] : r)))} aria-label={valuePlaceholder} />
          <Button variant="ghost" size="sm" iconOnly icon={Trash2} disabled={disabled} onClick={() => commit(rows.filter((_, j) => j !== i))} aria-label="Remove row" />
        </div>
      ))}
      {!disabled && <div><Button size="sm" variant="ghost" icon={Plus} onClick={() => setRows([...rows, ["", ""]])}>Add</Button></div>}
    </div>
  );
}

// ---------------------------------------------------------------- display
export const Card = ({ children, className, pad, onClick }: { children: ReactNode; className?: string; pad?: boolean; onClick?: () => void }) => (
  <div className={cx("card", pad && "pad", onClick && "interactive", className)} onClick={onClick} role={onClick ? "link" : undefined}>{children}</div>
);
export const CardHeader = ({ title, children, icon: Icon }: { title: ReactNode; children?: ReactNode; icon?: LucideIcon }) => (
  <div className="card-header">{Icon && <Icon size={16} className="dim" />}<h3>{title}</h3><div className="spacer" />{children}</div>
);

export const Badge = ({ tone, children, pulse }: { tone?: "success" | "danger" | "warning" | "info" | "accent"; children: ReactNode; pulse?: boolean }) => (
  <span className={cx("badge", tone, pulse && "pulse")}><span className="dot" />{children}</span>
);
export const MethodBadge = ({ method }: { method: string }) => <span className={cx("method", method)}>{method}</span>;

const runTone: Record<RunStatus, "success" | "danger" | "warning" | "info" | undefined> = { queued: "info", running: "info", completed: "success", failed: "danger", cancelled: undefined };
export const RunStatusBadge = ({ status }: { status: RunStatus }) => <Badge tone={runTone[status]} pulse={status === "running" || status === "queued"}>{status}</Badge>;
const resTone = { passed: "success", failed: "danger", error: "warning" } as const;
export const ResultBadge = ({ status }: { status: ResultStatus }) => <Badge tone={resTone[status]}>{status}</Badge>;
export function VerdictBadge({ verdict }: { verdict: Verdict | null | undefined }) {
  if (!verdict) return <span className="faint">—</span>;
  const map = { pass: ["success", "No regressions"], warn: ["warning", "Slower"], fail: ["danger", "Regression"], no_baseline: [undefined, "Baseline"] } as const;
  const [tone, label] = map[verdict];
  return <Badge tone={tone}>{label}</Badge>;
}

export function StatusDot({ ok }: { ok: boolean }) {
  return <span style={{ width: 8, height: 8, borderRadius: "50%", background: ok ? "var(--success)" : "var(--danger)", boxShadow: `0 0 0 3px ${ok ? "var(--success-soft)" : "var(--danger-soft)"}`, flex: "none" }} />;
}

export function EmptyState({ icon: Icon, title, children, action }: { icon: LucideIcon; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      <div className="icon"><Icon size={24} /></div>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function PageHeader({ title, sub, children }: { title: ReactNode; sub?: ReactNode; children?: ReactNode }) {
  return (
    <div className="page-header">
      <div className="grow"><h1>{title}</h1>{sub && <p className="sub">{sub}</p>}</div>
      {children && <div className="page-actions">{children}</div>}
    </div>
  );
}

export function Alert({ tone = "info", children, icon: Icon }: { tone?: "info" | "danger" | "warning" | "success"; children: ReactNode; icon?: LucideIcon }) {
  return <div className={cx("alert", tone)} role={tone === "danger" ? "alert" : undefined}>{Icon && <Icon size={16} />}<div className="grow">{children}</div></div>;
}

export function Skeleton({ h = 16, w = "100%" }: { h?: number; w?: number | string }) {
  return <div className="skeleton" style={{ height: h, width: w }} />;
}
export const PageSkeleton = () => (
  <div className="stack"><Skeleton h={34} w={260} /><div className="grid-3"><Skeleton h={110} /><Skeleton h={110} /><Skeleton h={110} /></div><Skeleton h={260} /></div>
);

export function ProgressBar({ value, max }: { value: number; max: number }) {
  return <div className="progress" role="progressbar" aria-valuenow={value} aria-valuemax={max}><div style={{ width: `${max ? Math.min(100, (value / max) * 100) : 0}%` }} /></div>;
}

export function CodeBlock({ children, copy = true }: { children: string; copy?: boolean }) {
  const [done, setDone] = useState(false);
  return (
    <pre className="code">
      {copy && (
        <Button className="copy-btn" size="sm" variant="ghost" iconOnly icon={done ? Check : Copy} aria-label="Copy"
          onClick={() => { navigator.clipboard?.writeText(children); setDone(true); setTimeout(() => setDone(false), 1500); }} />
      )}
      {children}
    </pre>
  );
}

export function Tabs({ items }: { items: { to: string; label: string; icon?: LucideIcon; count?: number; end?: boolean }[] }) {
  return (
    <nav className="tabs" aria-label="Sections">
      {items.map(({ to, label, icon: Icon, count, end }) => (
        <NavLink key={to} to={to} end={end} className={({ isActive }) => cx("tab", isActive && "active")}>
          {Icon && <Icon size={15} />}{label}{count !== undefined && <span className="count">{count}</span>}
        </NavLink>
      ))}
    </nav>
  );
}

export function Segmented<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: { value: T; label: string }[] }) {
  return (
    <div className="segmented" role="tablist">
      {options.map((o) => <button key={o.value} className={cx(value === o.value && "active")} onClick={() => onChange(o.value)} role="tab" aria-selected={value === o.value}>{o.label}</button>)}
    </div>
  );
}
