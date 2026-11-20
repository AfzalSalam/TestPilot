import { AlertTriangle, ArrowLeft, CheckCircle2, ChevronRight, CircleHelp, GitCompare, RotateCw, ShieldAlert, Trash2, Turtle, XCircle } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError } from "@/api/client";
import { isActive, useRegression, useResults, useRun, useRunMutations, useRuns } from "@/api/hooks";
import type { RegressionEntry, RegressionReport, Result, Run } from "@/api/types";
import { useProjectCtx } from "@/components/layout/ProjectLayout";
import { ResultDetails } from "@/components/ResultDetails";
import { ConfirmDialog, useToast } from "@/components/ui/overlays";
import { Alert, Badge, Button, Card, CardHeader, EmptyState, PageSkeleton, ProgressBar, ResultBadge, RunStatusBadge, Segmented, Select, VerdictBadge, cx, errorMessage } from "@/components/ui/ui";
import { dateTime, ms, plural, timeAgo } from "@/lib/format";
import { TRIGGER_LABEL } from "./Runs";

// ---------------------------------------------------------------- regression pieces
function PerfMeter({ perf }: { perf: NonNullable<RegressionEntry["performance"]> }) {
  if (perf.state === "insufficient_data" || !perf.threshold_ms || !perf.current_ms || !perf.baseline_median_ms) return <span className="faint" style={{ fontSize: 12 }}>needs ≥ 3 samples ({perf.samples})</span>;
  const scale = Math.max(perf.current_ms, perf.threshold_ms) * 1.15;
  const pos = (v: number) => `${(v / scale) * 100}%`;
  return (
    <div className="perf-meter" title={`normal ≤ ${ms(perf.threshold_ms)} · typical ${ms(perf.baseline_median_ms)} · now ${ms(perf.current_ms)}`}>
      <div className="band" style={{ left: 0, width: pos(perf.threshold_ms) }} />
      <div className="mark" style={{ left: pos(perf.baseline_median_ms), background: "var(--text-dim)" }} />
      <div className="mark" style={{ left: pos(perf.current_ms), background: perf.state === "regressed" ? "var(--danger)" : "var(--success)" }} />
    </div>
  );
}

function ChangeList({ title, icon: Icon, tone, entries, perf }: { title: string; icon: typeof XCircle; tone: "danger" | "warning" | "success" | "info" | undefined; entries: RegressionEntry[]; perf?: boolean }) {
  if (!entries.length) return null;
  return (
    <Card>
      <CardHeader title={<span className="row"><Icon size={16} color={`var(--${tone ?? "text-dim"})`} />{title}<Badge tone={tone}>{entries.length}</Badge></span>} />
      {entries.map((e, i) => (
        <div className="change-row" key={i}>
          <div style={{ minWidth: 0 }}>
            <div className="row"><b className="truncate">{e.test_name}</b></div>
            <div className="faint mono truncate" style={{ fontSize: 12 }}>{e.method} {e.url}</div>
            {e.error && <div style={{ color: "var(--warning)", fontSize: 12.5 }}>{e.error}</div>}
          </div>
          {perf && e.performance ? (
            <><PerfMeter perf={e.performance} /><div className="right nowrap"><b style={{ color: "var(--danger)" }}>{ms(e.performance.current_ms)}</b><div className="faint" style={{ fontSize: 12 }}>typical {ms(e.performance.baseline_median_ms)} · +{e.performance.change_pct}%</div></div></>
          ) : (
            <><span className="row nowrap">{e.baseline_status && <ResultBadge status={e.baseline_status} />}{e.baseline_status && <ChevronRight size={14} className="faint" />}<ResultBadge status={e.status} /></span>
              <span className="faint nowrap">{e.baseline_status_code ?? "—"} → {e.status_code ?? "—"}</span></>
          )}
        </div>
      ))}
    </Card>
  );
}

function RegressionView({ report }: { report: RegressionReport }) {
  const { summary: s, thresholds: t } = report;
  const nothing = !report.new_failures.length && !report.performance_regressions.length && !report.fixed.length && !report.still_failing.length && !report.new_tests.length;
  return (
    <div className="stack">
      {report.verdict === "no_baseline" && <Alert tone="info" icon={CircleHelp}>This is the first run of this scope, so there is nothing to compare against yet. Run it again to get a regression report.</Alert>}
      <ChangeList title="New failures" icon={XCircle} tone="danger" entries={report.new_failures} />
      <ChangeList title="Performance regressions" icon={Turtle} tone="warning" entries={report.performance_regressions} perf />
      <ChangeList title="Fixed" icon={CheckCircle2} tone="success" entries={report.fixed} />
      <ChangeList title="Still failing" icon={AlertTriangle} tone="danger" entries={report.still_failing} />
      <ChangeList title="New tests" icon={GitCompare} tone="info" entries={report.new_tests} />
      {report.verdict !== "no_baseline" && nothing && <Card><EmptyState icon={CheckCircle2} title="Nothing changed">All {s.still_passing} tests behave the same as in the baseline run.</EmptyState></Card>}
      <Card pad>
        <div className="row" style={{ alignItems: "flex-start" }}><CircleHelp size={18} className="dim" style={{ flex: "none", marginTop: 2 }} />
          <div className="dim" style={{ fontSize: 13 }}>
            <b style={{ color: "var(--text)" }}>How slowdowns are judged.</b> A test is flagged only if its response time exceeds <b>all</b> of: {t.slowdown_ratio}× its median over the last {t.history_window} passing runs, the median + 3 robust standard deviations (MAD), and the median + {t.min_delta_ms} ms — and only with at least {t.min_samples} samples. This keeps ordinary jitter from raising false alarms.
          </div>
        </div>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- results list
function ResultRow({ r, open, onToggle }: { r: Result; open: boolean; onToggle: () => void }) {
  const failed = r.assertion_results.filter((a) => !a.passed).length;
  return (
    <div className={cx("result", open && "open")}>
      <button className="result-head" onClick={onToggle} aria-expanded={open}>
        <ChevronRight size={16} className="chev" />
        <span className={cx("status-icon", r.status)}>{r.status === "passed" ? "✓" : r.status === "failed" ? "✕" : "!"}</span>
        <span className={cx("method", r.method)}>{r.method}</span>
        <div className="grow"><b className="truncate" style={{ display: "block" }}>{r.test_name}</b><span className="mono faint truncate" style={{ display: "block", fontSize: 12 }}>{r.url}</span></div>
        {failed > 0 && <Badge tone="danger">{plural(failed, "failed assertion")}</Badge>}
        {r.error_type && <Badge tone="warning">{r.error_type.replace(/_/g, " ")}</Badge>}
        <span className="dim nowrap" style={{ minWidth: 60, textAlign: "right" }}>{r.status_code ?? "—"}</span>
        <span className="dim nowrap" style={{ minWidth: 70, textAlign: "right" }}>{ms(r.response_time_ms)}</span>
      </button>
      {open && <div className="result-body"><ResultDetails result={r} /></div>}
    </div>
  );
}

function ResultsView({ run, projectId }: { run: Run; projectId: number }) {
  const [filter, setFilter] = useState<"all" | "passed" | "failed" | "error">("all");
  const [openIds, setOpenIds] = useState<Set<number>>(new Set());
  const { data, isLoading } = useResults(projectId, run.id, filter === "all" ? undefined : filter, isActive(run.status));
  const toggle = (id: number) => setOpenIds((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  return (
    <Card>
      <div className="card-header">
        <Segmented value={filter} onChange={setFilter} options={[{ value: "all", label: `All (${run.progress})` }, { value: "passed", label: `Passed (${run.passed})` }, { value: "failed", label: `Failed (${run.failed})` }, { value: "error", label: `Errors (${run.errored})` }]} />
        <div className="spacer" />
        {data && data.items.length > 0 && <Button size="sm" variant="ghost" onClick={() => setOpenIds(openIds.size ? new Set() : new Set(data.items.filter((r) => r.status !== "passed").map((r) => r.id)))}>{openIds.size ? "Collapse all" : "Expand failures"}</Button>}
      </div>
      {isLoading ? <div className="card-body faint">Loading results…</div>
        : !data?.items.length ? <EmptyState icon={CheckCircle2} title="No results to show">{isActive(run.status) ? "Results appear here as each test finishes." : "No results match this filter."}</EmptyState>
        : data.items.map((r) => <ResultRow key={r.id} r={r} open={openIds.has(r.id)} onToggle={() => toggle(r.id)} />)}
    </Card>
  );
}

// ---------------------------------------------------------------- page
export default function RunDetailPage() {
  const { projectId, canEdit } = useProjectCtx();
  const { runId: raw } = useParams();
  const runId = Number(raw);
  const nav = useNavigate();
  const toast = useToast();
  const { data: run, error, isLoading } = useRun(projectId, runId);
  const { cancel, rerun, remove } = useRunMutations(projectId);
  const [tab, setTab] = useState<"regression" | "results">("regression");
  const [baseline, setBaseline] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);
  const finished = run?.status === "completed";
  const { data: report, isLoading: reportLoading, error: reportError } = useRegression(projectId, runId, baseline, finished);
  const { data: candidates } = useRuns(projectId, { status: "completed", collection_id: run?.collection_id, limit: 50 });

  if (isLoading) return <PageSkeleton />;
  if (error || !run) return <Alert tone="danger">{error instanceof ApiError && error.status === 404 ? "Run not found." : (error as Error)?.message}</Alert>;

  const active = isActive(run.status);
  const verdict = run.status === "completed" ? (report?.verdict ?? run.regression_summary?.verdict) : undefined;
  const summary = report?.summary ?? run.regression_summary;
  const headline = {
    pass: ["No regressions", "Everything that passed before still passes, and response times are normal."],
    fail: ["Regression detected", `${plural(summary?.new_failures ?? 0, "test")} that passed in run #${run.baseline_run_id ?? report?.baseline_run_id} now fail.`],
    warn: ["Performance regression", `${plural(summary?.performance_regressions ?? 0, "test")} responded much slower than usual. No new functional failures.`],
    no_baseline: ["Baseline run", "First completed run of this scope — future runs will be compared against it."],
  } as const;
  const bannerClass = active ? "running" : run.status === "completed" ? (verdict ?? "no_baseline") : "fail";
  const BannerIcon = active ? RotateCw : bannerClass === "pass" ? CheckCircle2 : bannerClass === "warn" ? Turtle : bannerClass === "no_baseline" ? GitCompare : ShieldAlert;

  return (
    <div className="stack" style={{ gap: 18 }}>
      <div className="row between wrap">
        <div className="stack sm" style={{ gap: 6 }}>
          <Link to={`/projects/${projectId}/runs`} className="row dim" style={{ fontSize: 13 }}><ArrowLeft size={14} />All runs</Link>
          <div className="row wrap"><h2 style={{ fontSize: 22 }}>Run #{run.id}</h2><RunStatusBadge status={run.status} /><Badge>{TRIGGER_LABEL[run.trigger]}</Badge>{run.label && <Badge tone="accent">{run.label}</Badge>}</div>
          <div className="dim" style={{ fontSize: 13 }}>{run.collection_name ?? "All tests"} · concurrency {run.concurrency} · {dateTime(run.created_at)} ({timeAgo(run.created_at)}){run.duration_ms !== null && <> · took {ms(run.duration_ms)}</>}</div>
        </div>
        {canEdit && (
          <div className="row">
            {active && <Button icon={XCircle} loading={cancel.isPending} onClick={() => cancel.mutate(run.id, { onSuccess: () => toast.success("Run cancelled"), onError: (e) => toast.error("Could not cancel", errorMessage(e)) })}>Cancel run</Button>}
            {!active && <Button icon={RotateCw} loading={rerun.isPending} onClick={() => rerun.mutate(run.id, { onSuccess: (n) => { toast.success(`Run #${n.id} started`); nav(`/projects/${projectId}/runs/${n.id}`); }, onError: (e) => toast.error("Could not re-run", errorMessage(e)) })}>Re-run</Button>}
            {!active && <Button variant="ghost" iconOnly icon={Trash2} aria-label="Delete run" onClick={() => setDeleting(true)} />}
          </div>
        )}
      </div>

      {run.error_message && <Alert tone="danger">Run failed: {run.error_message}</Alert>}

      <div className={cx("verdict", bannerClass)}>
        <div className="v-icon"><BannerIcon size={22} className={active ? "spin" : undefined} style={active ? { animation: "spin 1.2s linear infinite" } : undefined} /></div>
        <div className="grow">
          {active ? (<><h3>{run.status === "queued" ? "Waiting for a worker…" : "Running tests…"}</h3><div style={{ maxWidth: 420, marginTop: 8 }}><ProgressBar value={run.progress} max={run.total} /></div><div className="dim" style={{ fontSize: 13, marginTop: 6 }}>{run.progress} of {run.total} tests finished</div></>)
            : run.status === "completed" && verdict ? (<><h3>{headline[verdict][0]}</h3><p className="dim">{headline[verdict][1]}</p></>)
            : (<><h3>Run {run.status}</h3><p className="dim">{run.status === "cancelled" ? "This run was cancelled before finishing; partial results are kept." : "The run did not complete."}</p></>)}
        </div>
        <div className="stat-pills">
          <div className="stat-pill"><b style={{ color: "var(--success)" }}>{run.passed}</b><span>passed</span></div>
          <div className="stat-pill"><b style={{ color: run.failed ? "var(--danger)" : undefined }}>{run.failed}</b><span>failed</span></div>
          <div className="stat-pill"><b style={{ color: run.errored ? "var(--warning)" : undefined }}>{run.errored}</b><span>errors</span></div>
          <div className="stat-pill"><b>{run.total}</b><span>total</span></div>
        </div>
      </div>

      <div className="row between wrap">
        <Segmented value={tab} onChange={setTab} options={[{ value: "regression", label: "Regression report" }, { value: "results", label: `Results (${run.progress})` }]} />
        {tab === "regression" && finished && (
          <div className="row"><GitCompare size={15} className="dim" /><span className="dim">Compare with</span>
            <Select className="sm" style={{ width: 230 }} value={baseline ?? ""} onChange={(e) => setBaseline(e.target.value ? Number(e.target.value) : null)} aria-label="Baseline run">
              <option value="">Previous run{report?.baseline_run_id ? ` (#${report.baseline_run_id})` : ""}</option>
              {candidates?.items.filter((c) => c.id !== run.id).map((c) => <option key={c.id} value={c.id}>#{c.id} · {c.passed}/{c.total} passed · {timeAgo(c.created_at)}</option>)}
            </Select>
            {report && <VerdictBadge verdict={report.verdict} />}</div>
        )}
      </div>

      {tab === "regression"
        ? !finished ? <Card><EmptyState icon={GitCompare} title="Report available when the run completes">{active ? "Regression analysis runs automatically once every test has finished." : "Cancelled or failed runs are not analysed."}</EmptyState></Card>
          : reportLoading ? <PageSkeleton /> : reportError ? <Alert tone="danger">{(reportError as Error).message}</Alert> : report && <RegressionView report={report} />
        : <ResultsView run={run} projectId={projectId} />}

      {deleting && <ConfirmDialog title="Delete run" message={<>Delete run <b>#{run.id}</b> and its results?</>} loading={remove.isPending} onClose={() => setDeleting(false)}
        onConfirm={() => remove.mutate(run.id, { onSuccess: () => { toast.success("Run deleted"); nav(`/projects/${projectId}/runs`); } })} />}
    </div>
  );
}
