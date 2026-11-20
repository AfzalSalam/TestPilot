import { CalendarClock, Pencil, Plus, Trash2, Zap } from "lucide-react";
import { useState } from "react";
import { useCollections, useCronPreview, useScheduleMutations, useSchedules } from "@/api/hooks";
import type { Schedule } from "@/api/types";
import { useProjectCtx } from "@/components/layout/ProjectLayout";
import { ConfirmDialog, Modal, useToast } from "@/components/ui/overlays";
import { Alert, Badge, Button, Card, EmptyState, Field, Input, PageSkeleton, Select, Switch, errorMessage } from "@/components/ui/ui";
import { dateTime, timeAgo } from "@/lib/format";

const PRESETS = [
  { label: "Every 5 min", cron: "*/5 * * * *" },
  { label: "Hourly", cron: "0 * * * *" },
  { label: "Daily 09:00", cron: "0 9 * * *" },
  { label: "Weekdays 09:00", cron: "0 9 * * 1-5" },
  { label: "Weekly (Mon)", cron: "0 9 * * 1" },
];

function ScheduleModal({ existing, onClose }: { existing: Schedule | null; onClose: () => void }) {
  const { projectId } = useProjectCtx();
  const toast = useToast();
  const { data: collections } = useCollections(projectId);
  const { create, update } = useScheduleMutations(projectId);
  const [name, setName] = useState(existing?.name ?? "");
  const [cron, setCron] = useState(existing?.cron ?? "0 9 * * *");
  const [collectionId, setCollectionId] = useState<number | null>(existing?.collection_id ?? null);
  const [concurrency, setConcurrency] = useState(existing?.concurrency ?? 4);
  const [enabled, setEnabled] = useState(existing?.enabled ?? true);
  const [error, setError] = useState<string | null>(null);
  const preview = useCronPreview(projectId, cron);
  const busy = create.isPending || update.isPending;

  const submit = () => {
    setError(null);
    const body = { name: name.trim(), cron: cron.trim(), collection_id: collectionId, concurrency, enabled };
    if (!body.name) return setError("Name is required.");
    const opts = { onSuccess: () => { toast.success(existing ? "Schedule updated" : "Schedule created"); onClose(); }, onError: (e: unknown) => setError(errorMessage(e)) };
    existing ? update.mutate({ id: existing.id, body }, opts) : create.mutate(body, opts);
  };

  return (
    <Modal title={existing ? "Edit schedule" : "New schedule"} onClose={onClose}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} onClick={submit}>{existing ? "Save" : "Create schedule"}</Button></>}>
      <div className="stack">
        {error && <Alert tone="danger">{error}</Alert>}
        <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nightly regression" autoFocus /></Field>
        <Field label="Cron expression" hint="Five fields: minute hour day-of-month month day-of-week (UTC).">
          <Input className="mono" value={cron} onChange={(e) => setCron(e.target.value)} />
        </Field>
        <div className="row wrap">{PRESETS.map((p) => <Button key={p.cron} size="sm" variant={cron === p.cron ? "primary" : "secondary"} onClick={() => setCron(p.cron)}>{p.label}</Button>)}</div>
        <div>
          {preview.isFetching && !preview.data ? <span className="faint">Checking…</span>
            : preview.data && !preview.data.valid ? <Alert tone="danger">{preview.data.message ?? "Invalid cron expression"}</Alert>
            : preview.data && <div className="dim" style={{ fontSize: 13 }}><b style={{ color: "var(--text)" }}>Next runs (UTC):</b>{preview.data.upcoming.slice(0, 4).map((d) => <div key={d} className="mono">{dateTime(d)}</div>)}</div>}
        </div>
        <div className="grid-2">
          <Field label="Scope"><Select value={collectionId ?? ""} onChange={(e) => setCollectionId(e.target.value ? Number(e.target.value) : null)}>
            <option value="">All tests</option>{collections?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>
          <Field label="Concurrency"><Input type="number" min={1} max={20} value={concurrency} onChange={(e) => setConcurrency(Math.min(20, Math.max(1, Number(e.target.value) || 1)))} /></Field>
        </div>
        <Switch checked={enabled} onChange={setEnabled} label="Enabled" />
      </div>
    </Modal>
  );
}

export default function SchedulesPage() {
  const { projectId, canEdit } = useProjectCtx();
  const toast = useToast();
  const { data, isLoading, error } = useSchedules(projectId);
  const { update, remove, trigger } = useScheduleMutations(projectId);
  const [editing, setEditing] = useState<Schedule | null | "new">(null);
  const [deleting, setDeleting] = useState<Schedule | null>(null);

  if (isLoading) return <PageSkeleton />;
  return (
    <div className="stack">
      <div className="row between wrap">
        <p className="dim" style={{ maxWidth: 560 }}>Schedules run a collection automatically. A schedule never overlaps itself: if the previous run is still going, that tick is skipped.</p>
        {canEdit && <Button variant="primary" icon={Plus} onClick={() => setEditing("new")}>New schedule</Button>}
      </div>
      {error && <Alert tone="danger">{(error as Error).message}</Alert>}
      <Card>
        {!data?.length ? <EmptyState icon={CalendarClock} title="No schedules" action={canEdit ? <Button variant="primary" icon={Plus} onClick={() => setEditing("new")}>Create schedule</Button> : undefined}>Run your suite on a cron to catch regressions without lifting a finger.</EmptyState> : (
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Name</th><th>Cron</th><th>Scope</th><th>Next run</th><th>Last run</th><th>Enabled</th>{canEdit && <th />}</tr></thead>
            <tbody>{data.map((s) => (
              <tr key={s.id}>
                <td><b>{s.name}</b></td>
                <td className="mono">{s.cron}</td>
                <td>{s.collection_name ?? "All tests"}</td>
                <td className="dim nowrap">{s.enabled && s.next_run_at ? dateTime(s.next_run_at) : <Badge>Paused</Badge>}</td>
                <td className="dim nowrap">{s.last_run_at ? timeAgo(s.last_run_at) : "—"}</td>
                <td><Switch checked={s.enabled} disabled={!canEdit} onChange={(v) => update.mutate({ id: s.id, body: { enabled: v } }, { onError: (e) => toast.error("Could not update", errorMessage(e)) })} label="" /></td>
                {canEdit && <td className="right nowrap">
                  <Button size="sm" variant="ghost" iconOnly icon={Zap} aria-label="Run now" title="Run now" onClick={() => trigger.mutate(s.id, { onSuccess: (r) => toast.success(`Run #${r.id} started`), onError: (e) => toast.error("Could not trigger", errorMessage(e)) })} />
                  <Button size="sm" variant="ghost" iconOnly icon={Pencil} aria-label="Edit" onClick={() => setEditing(s)} />
                  <Button size="sm" variant="ghost" iconOnly icon={Trash2} aria-label="Delete" onClick={() => setDeleting(s)} />
                </td>}
              </tr>))}</tbody>
          </table></div>
        )}
      </Card>
      {editing && <ScheduleModal existing={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
      {deleting && <ConfirmDialog title="Delete schedule" message={<>Delete <b>{deleting.name}</b>? Past runs are kept.</>} loading={remove.isPending} onClose={() => setDeleting(null)}
        onConfirm={() => remove.mutate(deleting.id, { onSuccess: () => { toast.success("Schedule deleted"); setDeleting(null); } })} />}
    </div>
  );
}
