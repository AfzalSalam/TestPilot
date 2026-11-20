import { Activity, AlertTriangle, ArrowRight, FolderKanban, Gauge, Plus, ShieldCheck, Timer } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useDashboard } from "@/api/hooks";
import { useAuth } from "@/auth/AuthContext";
import { StackedBars } from "@/components/charts";
import { Alert, Badge, Button, Card, CardHeader, EmptyState, PageHeader, RunStatusBadge, Skeleton, VerdictBadge } from "@/components/ui/ui";
import { ms, pct, plural, timeAgo } from "@/lib/format";
import { CreateProjectModal } from "./Projects";

function Kpi({ label, value, sub, icon: Icon }: { label: string; value: string; sub?: string; icon: typeof Gauge }) {
  return (
    <Card className="kpi">
      <div className="kpi-icon"><Icon size={17} /></div>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </Card>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const nav = useNavigate();
  const { data, isLoading, error } = useDashboard();
  const [creating, setCreating] = useState(false);
  const first = user?.full_name.split(" ")[0];

  return (
    <div className="page">
      <PageHeader title={`Welcome back${first ? `, ${first}` : ""}`} sub="Here's how your APIs have been behaving over the last 14 days.">
        <Button variant="primary" icon={Plus} onClick={() => setCreating(true)}>New project</Button>
      </PageHeader>
      {error && <Alert tone="danger">{(error as Error).message}</Alert>}

      {isLoading || !data ? (
        <div className="stack"><div className="kpis"><Skeleton h={112} /><Skeleton h={112} /><Skeleton h={112} /><Skeleton h={112} /></div><Skeleton h={300} /></div>
      ) : data.projects === 0 ? (
        <div className="card"><EmptyState icon={FolderKanban} title="No projects yet" action={<Button variant="primary" icon={Plus} onClick={() => setCreating(true)}>Create a project</Button>}>Create a project, add a few test cases, and run them to start tracking regressions.</EmptyState></div>
      ) : (
        <>
          <div className="kpis">
            <Kpi label="Pass rate" value={pct(data.pass_rate_14d)} sub={`${plural(data.runs_14d, "run")} in 14 days`} icon={ShieldCheck} />
            <Kpi label="Avg response time" value={ms(data.avg_response_ms_14d)} sub="across all completed runs" icon={Timer} />
            <Kpi label="Active runs" value={String(data.active_runs)} sub={data.active_runs ? "executing now…" : "nothing running"} icon={Activity} />
            <Kpi label="Test cases" value={String(data.test_cases)} sub={`in ${plural(data.projects, "project")}`} icon={Gauge} />
          </div>

          <div className="grid-2">
            <div className="stack">
              <Card>
                <CardHeader title="Test executions per day" icon={Activity} />
                <div className="card-body">
                  <StackedBars
                    labels={data.daily.map((d) => d.date.slice(5))}
                    series={[{ name: "Passed", color: "var(--success)", values: data.daily.map((d) => d.passed) }, { name: "Failed / error", color: "var(--danger)", values: data.daily.map((d) => d.failed) }]}
                    tooltip={(i) => <div><b>{data.daily[i].date}</b><br />{data.daily[i].runs} runs · {data.daily[i].passed} passed · {data.daily[i].failed} failed</div>}
                  />
                </div>
              </Card>
              <Card>
                <CardHeader title="Recent runs" icon={Activity} />
                {data.recent_runs.length === 0 ? <EmptyState icon={Activity} title="No runs yet">Open a project and press “Run all” to execute your tests.</EmptyState> : (
                  <div className="table-wrap"><table className="table">
                    <thead><tr><th>Run</th><th>Project</th><th>Status</th><th>Result</th><th>Regression</th><th>When</th></tr></thead>
                    <tbody>
                      {data.recent_runs.map((r) => (
                        <tr key={r.id} className="clickable" onClick={() => nav(`/projects/${r.project_id}/runs/${r.id}`)}>
                          <td className="mono">#{r.id}</td>
                          <td className="truncate" style={{ maxWidth: 160 }}>{r.project_name}</td>
                          <td><RunStatusBadge status={r.status} /></td>
                          <td>{r.passed}/{r.total}</td>
                          <td><VerdictBadge verdict={r.regression_summary?.verdict} /></td>
                          <td className="dim nowrap">{timeAgo(r.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table></div>
                )}
              </Card>
            </div>

            <Card>
              <CardHeader title="Regression alerts" icon={AlertTriangle} />
              {data.alerts.length === 0 ? <EmptyState icon={ShieldCheck} title="All clear">No new failures or slowdowns detected in recent runs.</EmptyState> : (
                <div>
                  {data.alerts.map((a) => (
                    <Link key={a.run_id} to={`/projects/${a.project_id}/runs/${a.run_id}`} className="change-row" style={{ gridTemplateColumns: "minmax(0,1fr) auto", color: "inherit", textDecoration: "none" }}>
                      <div className="stack sm" style={{ gap: 2 }}>
                        <b className="truncate">{a.project_name} · run #{a.run_id}</b>
                        <span className="dim" style={{ fontSize: 12.5 }}>{a.new_failures ? `${plural(a.new_failures, "new failure")}` : ""}{a.new_failures && a.performance_regressions ? " · " : ""}{a.performance_regressions ? `${plural(a.performance_regressions, "slowdown")}` : ""} · {timeAgo(a.created_at)}</span>
                      </div>
                      <div className="row"><Badge tone={a.verdict === "fail" ? "danger" : "warning"}>{a.verdict === "fail" ? "Regression" : "Slower"}</Badge><ArrowRight size={15} className="faint" /></div>
                    </Link>
                  ))}
                </div>
              )}
            </Card>
          </div>
        </>
      )}
      {creating && <CreateProjectModal onClose={() => setCreating(false)} />}
    </div>
  );
}
