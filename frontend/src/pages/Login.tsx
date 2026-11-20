import { CheckCircle2, GitPullRequest, Radar, ShieldCheck, Timer, Zap } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { Alert, Button, Field, Input, Segmented } from "@/components/ui/ui";

const FEATURES = [
  { icon: Zap, title: "Concurrent, distributed execution", text: "Fan tests out across Celery workers with configurable concurrency." },
  { icon: Radar, title: "Regression detection", text: "Spot newly failing tests and statistically significant slowdowns." },
  { icon: GitPullRequest, title: "CI-ready", text: "Gate pull requests from GitHub Actions with a project API key." },
  { icon: ShieldCheck, title: "SSRF-safe by default", text: "Private IPs, metadata endpoints and DNS rebinding are blocked." },
];

export default function LoginPage() {
  const { user, login, register } = useAuth();
  const nav = useNavigate();
  const location = useLocation() as { state?: { from?: string } };
  const [mode, setMode] = useState<"login" | "register">("login");
  const [form, setForm] = useState({ email: "", password: "", name: "" });
  const [error, setError] = useState<string | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={location.state?.from ?? "/"} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null); setFields({});
    try {
      if (mode === "login") await login(form.email, form.password);
      else await register(form.email, form.password, form.name);
      nav(location.state?.from ?? "/", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) { setFields(err.fieldErrors); setError(err.status === 422 ? null : err.message); }
      else setError("Unexpected error");
    } finally { setBusy(false); }
  };
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  return (
    <div className="auth">
      <section className="auth-hero">
        <div className="brand" style={{ padding: 0 }}><span className="logo"><ShieldCheck size={18} /></span>TestPilot</div>
        <div>
          <h1>Catch API regressions <em>before</em> your users do.</h1>
          <p className="lead">Register your APIs, define assertions, run them concurrently, and compare every run against the last to find what just broke.</p>
          <div className="feature-list">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <div className="feature" key={title}><div className="ico"><Icon size={17} /></div><div><b>{title}</b><span>{text}</span></div></div>
            ))}
          </div>
          <div className="mini-run" aria-hidden>
            <div className="row between"><b>Run #128 · Smoke tests</b><span className="badge danger"><span className="dot" />Regression</span></div>
            <div className="stack sm" style={{ marginTop: 12, fontSize: 13 }}>
              <div className="row"><CheckCircle2 size={15} color="var(--success)" /> GET /products <span className="spacer" /><span className="faint mono">42 ms</span></div>
              <div className="row"><CheckCircle2 size={15} color="var(--success)" /> POST /orders <span className="spacer" /><span className="faint mono">118 ms</span></div>
              <div className="row"><span style={{ color: "var(--danger)" }}>✕</span> GET /products/1 <span className="spacer" /><span className="badge danger">new failure</span></div>
              <div className="row"><Timer size={15} color="var(--warning)" /> GET /search <span className="spacer" /><span className="badge warning">+212% slower</span></div>
            </div>
          </div>
        </div>
        <span className="faint" style={{ fontSize: 12.5 }}>Built with FastAPI · PostgreSQL · Celery · Redis · React</span>
      </section>

      <section className="auth-panel">
        <form className="auth-card" onSubmit={submit} noValidate>
          <div>
            <h2>{mode === "login" ? "Welcome back" : "Create your account"}</h2>
            <p className="dim" style={{ marginTop: 6 }}>{mode === "login" ? "Sign in to continue to your workspace." : "Start testing your APIs in minutes."}</p>
          </div>
          <Segmented value={mode} onChange={(m) => { setMode(m); setError(null); setFields({}); }} options={[{ value: "login", label: "Sign in" }, { value: "register", label: "Create account" }]} />
          {error && <Alert tone="danger">{error}</Alert>}
          {mode === "register" && <Field label="Full name" error={fields.full_name}><Input value={form.name} onChange={set("name")} placeholder="Ada Lovelace" autoComplete="name" invalid={!!fields.full_name} required /></Field>}
          <Field label="Email" error={fields.email}><Input type="email" value={form.email} onChange={set("email")} placeholder="you@company.com" autoComplete="email" invalid={!!fields.email} required /></Field>
          <Field label="Password" error={fields.password} hint={mode === "register" ? "At least 8 characters" : undefined}>
            <Input type="password" value={form.password} onChange={set("password")} placeholder="••••••••" autoComplete={mode === "login" ? "current-password" : "new-password"} invalid={!!fields.password} required />
          </Field>
          <Button variant="primary" type="submit" loading={busy} block>{mode === "login" ? "Sign in" : "Create account"}</Button>
          <p className="faint" style={{ fontSize: 12.5, textAlign: "center" }}>Demo data? Run <span className="mono">scripts/seed_demo.py</span> then sign in as <span className="mono">demo@testpilot.dev</span> / <span className="mono">demo-pass-123</span></p>
        </form>
      </section>
    </div>
  );
}
