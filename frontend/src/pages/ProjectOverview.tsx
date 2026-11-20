import { Activity, AlertTriangle, ArrowRight, CircleDot, FileUp, FlaskConical, Gauge, Play, ShieldCheck, Timer, Turtle } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAnalytics, useRuns } from "@/api/hooks";
import { AreaChart, Ring, StackedBars } from "@/components/charts";
import { useProjectCtx } from "@/components/layout/ProjectLayout";
import { StartRunModal } from "@/components/StartRunModal";
import { Alert, Badge, Button, Card, CardHeader, EmptyState, PageSkeleton, RunStatusBadge, VerdictBadge } from "@/components/ui/ui";
import { dateTime, ms, pct, plural, timeAgo } from "@/lib/format";

export default function ProjectOverview() {
  const { project, projectId, canEdit } = useProjectCtx();
  const nav = useNavigate();
  const { data, isLoading, error } = useAnalytics(projectId);
  const { data: runs } = useRuns(projectId, { limit: 5 });
  const [starting, setStarting] = useState(false);
  const base = `/projects/${projectId}`;

  if (isLoading) return <PageSkeleton />;
  if (error || !data) return <Alert tone="danger">{(error as Error)?.message ?? "Failed to load analytics"}</Alert>;

  if (project.test_case_count === 0) {
    return (
      <Card pad>
        <h3 style={{ fontSize: 18 }}>Let's get this project set up</h3>
        <p className="dim" style={{ marginTop: 6, marginBottom: 22 }}>Three steps to your first regression report.</p>
        <ol className="steps" style={{ padding: 0, margin: 0 }}>
          <li><b>Set the base URL</b><p className="dim">{project.base_url ? <>Currently <span className="mono">{project.base_url}</span>.</> : "Tell TestPilot where your API lives."} <Link to={`${base}/settings`}>Open settings</Link></p></li>
          <li><b>Add tests</b><p className="dim">Write them by hand in the test editor, or <Link to={`${base}/import`}>import an OpenAPI/Swagger spec</Link> to generate them automatically.</p></li>
          <li><b>Run &amp; compare</b><p className="dim">Run the suite twice — the second run is automatically compared to the first.</p></li>
        </ol>
        <div className="row" style={{ marginTop: 24 }}>
          {canEdit && <Link className="btn primary" to={`${base}/tests`}><FlaskConical size={16} />Create a test case</Link>}
          {canEdit && <Link className="btn" to={`${base}/import`}><FileUp size={16} />Import OpenAPI</Link>}
        </div>
      </Card>
    );
  }

  const trend = data.trend;
  const labels = trend.map((t) => `#${t.run_id}`);
  const last = runs?.items[0];
  const lastSummary = last?.regression_summary;

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="row between wrap">
        <div className="row wrap">
          {last && <><span className="dim">Latest run</span><Link to={`${base}/runs/${last.id}`} className="mono">#{last.id}</Link><RunStatusBadge status={last.status} /><VerdictBadge verdict={lastSummary?.verdict} /><span className="faint">{timeAgo(last.finished_at ?? last.created_at)}</span></>}
        </div>
        {canEdit && <Button variant="primary" icon={Play} onClick={() => setStarting(true)}>Run tests</Button>}
      </div>

      <div className="kpis" style={{ marginBottom: 0 }}>
        <Card className="kpi"><div className="kpi-label">Pass rate</div><div className="row" style={{ marginTop: 8 }}><Ring value={data.overall.pass_rate} size={64} stroke={7} color={(data.overall.pass_rate ?? 100) >= 90 ? "var(--success)" : (data.overall.pass_rate ?? 100) >= 70 ? "var(--warning)" : "var(--danger)"} /><div><div className="kpi-sub">last {plural(data.overall.window_runs, "run")}</div><div className="kpi-sub">{data.overall.executions} executions</div></div></div></Card>
        <Card className="kpi"><div className="kpi-icon"><Timer size={17} /></div><div className="kpi-label">Avg response</div><div className="kpi-value">{ms(data.overall.avg_response_ms)}</div><div className="kpi-sub">per request</div></Card>
        <Card className="kpi"><div className="kpi-icon"><AlertTriangle size={17} /></div><div className="kpi-label">Regressions caught</div><div className="kpi-value">{data.overall.regressions_detected}</div><div className="kpi-sub">new failures vs baseline</div></Card>
        <Card className="kpi"><div className="kpi-icon"><Gauge size={17} /></div><div className="kpi-label">Coverage</div><div className="kpi-value">{data.totals.test_cases}</div><div className="kpi-sub">tests · {data.totals.endpoints} endpoints · {data.totals.schedules} schedules</div></Card>
      </div>

      <div className="grid-2">
        <div className="stack" style={{ gap: 20 }}>
          <Card>
            <CardHeader title="Average response time" icon={Timer}><span className="faint" style={{ fontSize: 12.5 }}>per run</span></CardHeader>
            <div className="card-body">
              <AreaChart data={trend.map((t) => t.avg_response_ms)} labels={labels} unit=" ms" color="var(--accent)"
                tooltip={(i) => <div><b>Run #{trend[i].run_id}</b> · {trend[i].trigger}<br />{ms(trend[i].avg_response_ms)} avg<br /><span className="faint">{dateTime(trend[i].created_at)}</span></div>} />
            </div>
          </Card>
          <Card>
            <CardHeader title="Results per run" icon={Activity} />
            <div className="card-body">
              <StackedBars labels={labels}
                series={[{ name: "Passed", color: "var(--success)", values: trend.map((t) => t.passed) }, { name: "Failed", color: "var(--danger)", values: trend.map((t) => t.failed) }, { name: "Error", color: "var(--warning)", values: trend.map((t) => t.errored) }]}
                tooltip={(i) => <div><b>Run #{trend[i].run_id}</b> <VerdictBadge verdict={trend[i].verdict} /><br />{trend[i].passed}/{trend[i].total} passed ({pct(trend[i].pass_rate)})</div>} />
            </div>
          </Card>
        </div>

        <div className="stack" style={{ gap: 20 }}>
          <Card>
            <CardHeader title="Slowest tests" icon={Turtle} />
            {data.slowest.length === 0 ? <div className="card-body faint">Run your tests to see timings.</div> : data.slowest.map((s) => (
              <div className="change-row" key={s.test_case_id} style={{ gridTemplateColumns: "minmax(0,1fr) auto" }}>
                <span className="truncate">{s.name}</span>
                <div className="right"><b>{ms(s.avg_ms)}</b><div className="faint" style={{ fontSize: 11.5 }}>max {ms(s.max_ms)} · {s.samples} samples</div></div>
              </div>
            ))}
          </Card>
          <Card>
            <CardHeader title="Flaky tests" icon={CircleDot}><span className="faint" style={{ fontSize: 12.5 }}>flip between pass/fail</span></CardHeader>
            {data.flaky.length === 0 ? <div className="card-body row"><ShieldCheck size={18} color="var(--success)" /><span className="dim">No flaky tests detected.</span></div> : data.flaky.map((f) => (
              <div className="change-row" key={f.test_case_id} style={{ gridTemplateColumns: "minmax(0,1fr) auto" }}>
                <span className="truncate">{f.name}</span>
                <div className="row"><Badge tone="warning">{f.flips} flips</Badge><span className="faint">{pct(f.pass_rate)} pass</span></div>
              </div>
            ))}
          </Card>
          <Card>
            <CardHeader title="Recent runs"><Link to={`${base}/runs`} className="row" style={{ fontSize: 13 }}>View all <ArrowRight size={14} /></Link></CardHeader>
            {!runs?.items.length ? <EmptyState icon={Play} title="No runs yet">Start a run to see results here.</EmptyState> : runs.items.map((r) => (
              <div className="change-row" key={r.id} style={{ gridTemplateColumns: "auto minmax(0,1fr) auto", cursor: "pointer" }} onClick={() => nav(`${base}/runs/${r.id}`)}>
                <span className="mono dim">#{r.id}</span>
                <span className="dim truncate">{r.passed}/{r.total} passed · {timeAgo(r.created_at)}</span>
                <VerdictBadge verdict={r.regression_summary?.verdict} />
              </div>
            ))}
          </Card>
        </div>
      </div>
      {starting && <StartRunModal onClose={() => setStarting(false)} />}
    </div>
  );
}
