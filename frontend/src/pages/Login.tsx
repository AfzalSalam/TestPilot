import { CheckCircle2, GitPullRequest, Loader2, Radar, ShieldCheck, Timer, Zap } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { Alert, Button, Field, Input, Segmented } from "@/components/ui/ui";
import { supabase } from "@/lib/supabase";

const FEATURES = [
  { icon: Zap, title: "Concurrent, distributed execution", text: "Fan tests out across Celery workers with configurable concurrency." },
  { icon: Radar, title: "Regression detection", text: "Spot newly failing tests and statistically significant slowdowns." },
  { icon: GitPullRequest, title: "CI-ready", text: "Gate pull requests from GitHub Actions with a project API key." },
  { icon: ShieldCheck, title: "SSRF-safe by default", text: "Private IPs, metadata endpoints and DNS rebinding are blocked." },
];

export default function LoginPage() {
  const { user, loading: authLoading, login, register } = useAuth();
  const nav = useNavigate();
  const location = useLocation() as { state?: { from?: string } };
  const [mode, setMode] = useState<"login" | "register" | "forgot">("login");
  const [form, setForm] = useState({ email: "", password: "", name: "" });
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={location.state?.from ?? "/"} replace />;

  // Show spinner while exchanging Google token after OAuth redirect
  if (authLoading) return (
    <div className="auth" style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 16, color: "var(--dim)" }}>
        <Loader2 size={32} style={{ animation: "spin 1s linear infinite" }} />
        <span>Signing you in…</span>
      </div>
    </div>
  );

  const signInWithGoogle = async () => {
    setBusy(true);
    setError(null);
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo: window.location.origin },
      });
      if (error) setError(error.message);
    } catch {
      setError("Failed to initiate Google sign in");
    } finally {
      setBusy(false);
    }
  };

  const submitForgot = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.email) { setError("Please enter your email address"); return; }
    setBusy(true); setError(null); setInfo(null);
    try {
      const { error } = await supabase.auth.resetPasswordForEmail(form.email, {
        redirectTo: `${window.location.origin}/reset-password`,
      });
      if (error) setError(error.message);
      else setInfo("Check your email — we sent a password reset link.");
    } catch {
      setError("Failed to send reset email");
    } finally {
      setBusy(false); }
  };

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
        {mode === "forgot" ? (
          <form className="auth-card" onSubmit={submitForgot} noValidate>
            <div>
              <h2>Reset your password</h2>
              <p className="dim" style={{ marginTop: 6 }}>Enter your email and we'll send you a reset link.</p>
            </div>
            {error && <Alert tone="danger">{error}</Alert>}
            {info && <Alert tone="success">{info}</Alert>}
            <Field label="Email">
              <Input type="email" value={form.email} onChange={set("email")} placeholder="you@company.com" autoComplete="email" required />
            </Field>
            <Button variant="primary" type="submit" loading={busy} block>Send reset link</Button>
            <button type="button" onClick={() => { setMode("login"); setError(null); setInfo(null); }}
              style={{ background: "none", border: "none", color: "var(--dim)", cursor: "pointer", fontSize: 13, marginTop: 4 }}>
              ← Back to sign in
            </button>
          </form>
        ) : (
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
            {mode === "login" && (
              <div style={{ textAlign: "right", marginTop: -8 }}>
                <button type="button" onClick={() => { setMode("forgot"); setError(null); }}
                  style={{ background: "none", border: "none", color: "var(--dim)", cursor: "pointer", fontSize: 12.5 }}>
                  Forgot password?
                </button>
              </div>
            )}
            <Button variant="primary" type="submit" loading={busy} block>{mode === "login" ? "Sign in" : "Create account"}</Button>
            <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "14px 0", color: "var(--dim)", fontSize: 12 }}>
              <div style={{ flex: 1, height: 1, backgroundColor: "var(--border)" }} />
              <span>OR</span>
              <div style={{ flex: 1, height: 1, backgroundColor: "var(--border)" }} />
            </div>
            <Button type="button" variant="secondary" onClick={signInWithGoogle} disabled={busy} block
              style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
              <svg width="18" height="18" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
              </svg>
              Continue with Google
            </Button>
          </form>
        )}
      </section>
    </div>
  );
}

