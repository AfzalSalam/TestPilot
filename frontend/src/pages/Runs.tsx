import { History, Play, RotateCw, Trash2, XCircle } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { isActive, useRunMutations, useRuns } from "@/api/hooks";
import type { Run } from "@/api/types";
import { useProjectCtx } from "@/components/layout/ProjectLayout";
import { StartRunModal } from "@/components/StartRunModal";
import { ConfirmDialog, useToast } from "@/components/ui/overlays";
import { Alert, Badge, Button, Card, EmptyState, PageSkeleton, ProgressBar, RunStatusBadge, Select, VerdictBadge, errorMessage } from "@/components/ui/ui";
import { ms, timeAgo } from "@/lib/format";

export const TRIGGER_LABEL = { manual: "Manual", schedule: "Scheduled", ci: "CI" } as const;
const PAGE = 15;

export default function RunsPage() {
  const { projectId, canEdit } = useProjectCtx();
  const nav = useNavigate();
  const toast = useToast();
  const [status, setStatus] = useState("");
  const [trigger, setTrigger] = useState("");
  const [offset, setOffset] = useState(0);
  const [starting, setStarting] = useState(false);
  const [deleting, setDeleting] = useState<Run | null>(null);
  const { data, isLoading, error } = useRuns(projectId, { status: status || undefined, trigger: trigger || undefined, limit: PAGE, offset });
  const { cancel, rerun, remove } = useRunMutations(projectId);

  if (isLoading && !data) return <PageSkeleton />;
  const total = data?.total ?? 0;

  return (
    <div className="stack">
      <div className="row between wrap">
        <div className="row wrap">
          <Select style={{ width: 160 }} value={status} aria-label="Filter by status" onChange={(e) => { setStatus(e.target.value); setOffset(0); }}>
            <option value="">Any status</option>{["queued", "running", "completed", "failed", "cancelled"].map((s) => <option key={s}>{s}</option>)}
          </Select>
          <Select style={{ width: 160 }} value={trigger} aria-label="Filter by trigger" onChange={(e) => { setTrigger(e.target.value); setOffset(0); }}>
            <option value="">Any trigger</option><option value="manual">Manual</option><option value="schedule">Scheduled</option><option value="ci">CI</option>
          </Select>
        </div>
        {canEdit && <Button variant="primary" icon={Play} onClick={() => setStarting(true)}>New run</Button>}
      </div>
      {error && <Alert tone="danger">{(error as Error).message}</Alert>}

      <Card>
        {!data?.items.length ? (
          <EmptyState icon={History} title={status || trigger ? "No runs match" : "No runs yet"} action={canEdit && !status && !trigger ? <Button variant="primary" icon={Play} onClick={() => setStarting(true)}>Start a run</Button> : undefined}>
            {status || trigger ? "Clear the filters to see all runs." : "Run your tests to start building history. Each run is compared with the previous one automatically."}
          </EmptyState>
        ) : (
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Run</th><th>Status</th><th>Scope</th><th style={{ minWidth: 150 }}>Progress</th><th>Regression</th><th>Duration</th><th>Started</th>{canEdit && <th />}</tr></thead>
            <tbody>
              {data.items.map((r) => (
                <tr key={r.id} className="clickable" onClick={() => nav(`/projects/${projectId}/runs/${r.id}`)}>
                  <td><b className="mono">#{r.id}</b><div className="faint truncate" style={{ maxWidth: 150, fontSize: 12 }}>{r.label || "—"}</div></td>
                  <td><RunStatusBadge status={r.status} /></td>
                  <td><div className="truncate" style={{ maxWidth: 160 }}>{r.collection_name ?? "All tests"}</div><Badge tone={r.trigger === "ci" ? "info" : r.trigger === "schedule" ? "accent" : undefined}>{TRIGGER_LABEL[r.trigger]}</Badge></td>
                  <td>
                    {isActive(r.status) ? <div className="stack sm" style={{ gap: 4 }}><ProgressBar value={r.progress} max={r.total} /><span className="faint" style={{ fontSize: 12 }}>{r.progress}/{r.total} tests</span></div>
                      : <span><b style={{ color: "var(--success)" }}>{r.passed}</b><span className="faint"> / </span><b style={{ color: r.failed + r.errored ? "var(--danger)" : undefined }}>{r.failed + r.errored}</b><span className="faint"> of {r.total}</span></span>}
                  </td>
                  <td><VerdictBadge verdict={r.regression_summary?.verdict} /></td>
                  <td className="dim nowrap">{ms(r.duration_ms)}</td>
                  <td className="dim nowrap">{timeAgo(r.created_at)}</td>
                  {canEdit && (
                    <td className="right nowrap" onClick={(e) => e.stopPropagation()}>
                      {isActive(r.status)
                        ? <Button size="sm" variant="ghost" iconOnly icon={XCircle} aria-label="Cancel run" title="Cancel" onClick={() => cancel.mutate(r.id, { onSuccess: () => toast.success(`Run #${r.id} cancelled`), onError: (e) => toast.error("Could not cancel", errorMessage(e)) })} />
                        : <><Button size="sm" variant="ghost" iconOnly icon={RotateCw} aria-label="Re-run" title="Re-run" onClick={() => rerun.mutate(r.id, { onSuccess: (n) => { toast.success(`Run #${n.id} started`); nav(`/projects/${projectId}/runs/${n.id}`); }, onError: (e) => toast.error("Could not re-run", errorMessage(e)) })} />
                          <Button size="sm" variant="ghost" iconOnly icon={Trash2} aria-label="Delete run" title="Delete" onClick={() => setDeleting(r)} /></>}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
        {total > PAGE && (
          <div className="row between" style={{ padding: "12px 18px", borderTop: "1px solid var(--border)" }}>
            <span className="dim">Showing {offset + 1}–{Math.min(offset + PAGE, total)} of {total}</span>
            <div className="row"><Button size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</Button><Button size="sm" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>Next</Button></div>
          </div>
        )}
      </Card>
      {starting && <StartRunModal onClose={() => setStarting(false)} />}
      {deleting && <ConfirmDialog title="Delete run" message={<>Delete run <b>#{deleting.id}</b> and all of its results? This also removes it from trend charts and baselines.</>} loading={remove.isPending}
        onClose={() => setDeleting(null)} onConfirm={() => remove.mutate(deleting.id, { onSuccess: () => { toast.success("Run deleted"); setDeleting(null); } })} />}
    </div>
  );
}
