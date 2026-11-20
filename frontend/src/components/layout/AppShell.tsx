import { ChevronRight, FolderKanban, LayoutDashboard, LogOut, Menu, Moon, ShieldCheck, Sun } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useMatch } from "react-router-dom";
import { useHealth, useProject, useProjects } from "@/api/hooks";
import { useAuth } from "@/auth/AuthContext";
import { initials } from "@/lib/format";
import { Button, StatusDot, cx } from "../ui/ui";

export function useTheme() {
  const [theme, setTheme] = useState<"dark" | "light">(() => (document.documentElement.dataset.theme as "dark" | "light") || "dark");
  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("tp.theme", next); } catch { /* storage may be unavailable */ }
    setTheme(next);
  };
  return { theme, toggle };
}

const SECTION_LABELS: Record<string, string> = {
  tests: "Test cases", endpoints: "Endpoints", collections: "Collections", runs: "Runs",
  schedules: "Schedules", import: "OpenAPI import", settings: "Settings",
};

function Breadcrumbs() {
  const match = useMatch("/projects/:projectId/*");
  const projectId = match?.params.projectId ? Number(match.params.projectId) : 0;
  const { data: project } = useProject(projectId);
  const { pathname } = useLocation();
  const parts = pathname.split("/").filter(Boolean);

  if (!parts.length) return <div className="crumbs"><span className="current">Dashboard</span></div>;
  if (parts[0] !== "projects") return <div className="crumbs"><span className="current">Not found</span></div>;
  const section = parts[2];
  return (
    <div className="crumbs">
      <Link to="/projects">Projects</Link>
      {parts[1] && <><ChevronRight size={14} />{section ? <Link to={`/projects/${parts[1]}`}>{project?.name ?? "…"}</Link> : <span className="current">{project?.name ?? "…"}</span>}</>}
      {section && <><ChevronRight size={14} />{parts[3] ? <Link to={`/projects/${parts[1]}/${section}`}>{SECTION_LABELS[section]}</Link> : <span className="current">{SECTION_LABELS[section] ?? section}</span>}</>}
      {parts[3] && <><ChevronRight size={14} /><span className="current">#{parts[3]}</span></>}
    </div>
  );
}

function UserMenu() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  if (!user) return null;
  return (
    <div style={{ position: "relative" }} ref={ref}>
      <button className="avatar" onClick={() => setOpen(!open)} aria-label="Account menu" aria-expanded={open} style={{ border: "none", cursor: "pointer" }}>{initials(user.full_name)}</button>
      {open && (
        <div className="menu" role="menu">
          <div style={{ padding: "8px 10px" }}><b>{user.full_name}</b><div className="dim truncate" style={{ fontSize: 12.5 }}>{user.email}</div></div>
          <hr />
          <button role="menuitem" onClick={logout}><LogOut size={15} /> Sign out</button>
        </div>
      )}
    </div>
  );
}

export function AppShell() {
  const [open, setOpen] = useState(false);
  const { theme, toggle } = useTheme();
  const { data: health, isError } = useHealth();
  const { data: projects } = useProjects();
  const { pathname } = useLocation();
  useEffect(() => setOpen(false), [pathname]);

  const ok = !isError && health?.status === "ok";
  return (
    <div className="app">
      <aside className={cx("sidebar", open && "open")}>
        <Link to="/" className="brand"><span className="logo"><ShieldCheck size={18} /></span>TestPilot</Link>
        <NavLink to="/" end className={({ isActive }) => cx("nav-link", isActive && "active")}><LayoutDashboard size={17} />Dashboard</NavLink>
        <NavLink to="/projects" end className={({ isActive }) => cx("nav-link", isActive && "active")}><FolderKanban size={17} />Projects</NavLink>

        {!!projects?.length && <div className="nav-label">Recent projects</div>}
        {projects?.slice(0, 6).map((p) => (
          <NavLink key={p.id} to={`/projects/${p.id}`} className={({ isActive }) => cx("nav-link", isActive && "active")}>
            <span style={{ width: 8, height: 8, borderRadius: 3, flex: "none", background: p.last_run ? (p.last_run.status === "completed" && !p.last_run.failed && !p.last_run.errored ? "var(--success)" : p.last_run.status === "completed" ? "var(--danger)" : "var(--info)") : "var(--border-strong)" }} />
            <span className="truncate">{p.name}</span>
          </NavLink>
        ))}

        <div className="sidebar-foot">
          <div className="status-card">
            <div className="row"><StatusDot ok={ok} /><b>{isError ? "API unreachable" : ok ? "All systems normal" : "Degraded"}</b></div>
            {health && (
              <div className="faint" style={{ marginTop: 6, lineHeight: 1.6 }}>
                Workers: <span className="mono">{health.execution_mode}</span><br />
                {Object.entries(health.checks).map(([k, v]) => <span key={k}>{k}: {v === "not_used" ? "n/a" : v} · </span>)}
                v{health.version}
              </div>
            )}
          </div>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <Button className="mobile-only" variant="ghost" iconOnly icon={Menu} aria-label="Open navigation" onClick={() => setOpen(true)} />
          <Breadcrumbs />
          <div className="spacer" />
          <Button variant="ghost" iconOnly icon={theme === "dark" ? Sun : Moon} onClick={toggle} aria-label="Toggle theme" />
          <UserMenu />
        </header>
        <Outlet />
      </div>
      {open && <div className="overlay" style={{ zIndex: 55, background: "rgba(0,0,0,.5)" }} onClick={() => setOpen(false)} />}
    </div>
  );
}
