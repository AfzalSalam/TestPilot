import { Copy, FlaskConical, Pencil, Play, Plus, Search, Trash2, Zap } from "lucide-react";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useCollections, useTestCaseMutations, useTestCases } from "@/api/hooks";
import type { ExecuteResult, TestCase } from "@/api/types";
import { useProjectCtx } from "@/components/layout/ProjectLayout";
import { ResultDetails } from "@/components/ResultDetails";
import { StartRunModal } from "@/components/StartRunModal";
import { TestCaseEditor } from "@/components/TestCaseEditor";
import { ConfirmDialog, Modal, useToast } from "@/components/ui/overlays";
import { Badge, Button, Card, EmptyState, Input, MethodBadge, PageSkeleton, ResultBadge, Select, errorMessage } from "@/components/ui/ui";
import { ms } from "@/lib/format";

export default function TestCasesPage() {
  const { projectId, canEdit } = useProjectCtx();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const collectionFilter = params.get("collection") ? Number(params.get("collection")) : undefined;
  const [q, setQ] = useState("");
  const { data: collections } = useCollections(projectId);
  const { data, isLoading } = useTestCases(projectId, { collection_id: collectionFilter, q: q || undefined });
  const { remove, duplicate, update, trySaved } = useTestCaseMutations(projectId);

  const [editing, setEditing] = useState<TestCase | "new" | null>(null);
  const [deleting, setDeleting] = useState<TestCase | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [running, setRunning] = useState(false);
  const [quick, setQuick] = useState<{ tc: TestCase; result?: ExecuteResult; error?: string } | null>(null);

  const collectionName = useMemo(() => new Map(collections?.map((c) => [c.id, c.name])), [collections]);
  const allSelected = !!data?.length && data.every((t) => selected.has(t.id));
  const toggle = (id: number) => setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });

  const sendNow = (tc: TestCase) => {
    setQuick({ tc });
    trySaved.mutate(tc.id, { onSuccess: (result) => setQuick({ tc, result }), onError: (e) => setQuick({ tc, error: errorMessage(e) }) });
  };

  if (isLoading && !data) return <PageSkeleton />;
  const none = !data?.length;

  return (
    <div className="stack">
      <div className="row between wrap">
        <div className="row wrap">
          <div className="input-group" style={{ width: 280 }}><Search size={16} /><Input placeholder="Search name or path…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search test cases" /></div>
          <Select style={{ width: 200 }} value={collectionFilter ?? ""} aria-label="Filter by collection"
            onChange={(e) => { const next = new URLSearchParams(params); e.target.value ? next.set("collection", e.target.value) : next.delete("collection"); setParams(next); setSelected(new Set()); }}>
            <option value="">All collections</option>
            {collections?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
        </div>
        <div className="row">
          {canEdit && selected.size > 0 && <Button icon={Play} onClick={() => setRunning(true)}>Run {selected.size} selected</Button>}
          {canEdit && <Button variant="primary" icon={Plus} onClick={() => setEditing("new")}>New test case</Button>}
        </div>
      </div>

      <Card>
        {none ? (
          <EmptyState icon={FlaskConical} title={q || collectionFilter ? "No matching test cases" : "No test cases yet"} action={canEdit && !q ? <Button variant="primary" icon={Plus} onClick={() => setEditing("new")}>Create test case</Button> : undefined}>
            {q || collectionFilter ? "Try clearing the filters." : "A test case describes one HTTP request and what a healthy response looks like."}
          </EmptyState>
        ) : (
          <div className="table-wrap"><table className="table">
            <thead><tr>
              {canEdit && <th style={{ width: 36 }}><input type="checkbox" aria-label="Select all" checked={allSelected} onChange={() => setSelected(allSelected ? new Set() : new Set(data!.map((t) => t.id)))} /></th>}
              <th>Method</th><th>Test</th><th>Collection</th><th>Expect</th><th>Last result</th>{canEdit && <th />}
            </tr></thead>
            <tbody>
              {data!.map((t) => (
                <tr key={t.id} style={{ opacity: t.enabled ? 1 : 0.55 }}>
                  {canEdit && <td><input type="checkbox" aria-label={`Select ${t.name}`} checked={selected.has(t.id)} onChange={() => toggle(t.id)} /></td>}
                  <td><MethodBadge method={t.method} /></td>
                  <td style={{ maxWidth: 360 }}>
                    <div className="row"><b className="truncate" style={{ cursor: "pointer" }} onClick={() => setEditing(t)}>{t.name}</b>{!t.enabled && <Badge>disabled</Badge>}</div>
                    <div className="mono faint truncate">{t.path}</div>
                  </td>
                  <td>{t.collection_id ? <Badge tone="accent">{collectionName.get(t.collection_id) ?? "…"}</Badge> : <span className="faint">—</span>}</td>
                  <td className="dim nowrap">{t.expected_status}{t.assertions.length > 0 && <span className="faint"> +{t.assertions.length}</span>}</td>
                  <td>{t.last_status ? <div className="row"><ResultBadge status={t.last_status} /><span className="faint">{ms(t.last_response_time_ms)}</span></div> : <span className="faint">never run</span>}</td>
                  {canEdit && (
                    <td className="right nowrap">
                      <Button size="sm" variant="ghost" iconOnly icon={Zap} title="Send now (not stored)" aria-label={`Send ${t.name} now`} onClick={() => sendNow(t)} />
                      <Button size="sm" variant="ghost" iconOnly icon={Pencil} aria-label={`Edit ${t.name}`} onClick={() => setEditing(t)} />
                      <Button size="sm" variant="ghost" iconOnly icon={Copy} aria-label={`Duplicate ${t.name}`} onClick={() => duplicate.mutate(t.id, { onSuccess: () => toast.success("Duplicated"), onError: (e) => toast.error("Could not duplicate", errorMessage(e)) })} />
                      <Button size="sm" variant="ghost" iconOnly icon={Trash2} aria-label={`Delete ${t.name}`} onClick={() => setDeleting(t)} />
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </Card>
      {canEdit && !none && <p className="faint" style={{ fontSize: 12.5 }}>Tip: use ⚡ to send a single test instantly (not stored), or tick rows and press “Run selected” to create a tracked run.</p>}

      {editing && <TestCaseEditor projectId={projectId} existing={editing === "new" ? undefined : editing} defaultCollectionId={collectionFilter} onClose={() => setEditing(null)} />}
      {running && <StartRunModal testCaseIds={[...selected]} onClose={() => { setRunning(false); setSelected(new Set()); }} />}
      {deleting && <ConfirmDialog title="Delete test case" message={<>Delete <b>{deleting.name}</b>? Past results are kept in run history.</>} loading={remove.isPending}
        onClose={() => setDeleting(null)} onConfirm={() => remove.mutate(deleting.id, { onSuccess: () => { toast.success("Test case deleted"); setDeleting(null); } })} />}
      {quick && (
        <Modal wide title={`Send: ${quick.tc.name}`} onClose={() => setQuick(null)}
          footer={<>
            <Button onClick={() => update.mutate({ id: quick.tc.id, body: { enabled: !quick.tc.enabled } }, { onSuccess: (t) => setQuick({ ...quick, tc: t }) })}>{quick.tc.enabled ? "Disable test" : "Enable test"}</Button>
            <Button variant="primary" onClick={() => setQuick(null)}>Done</Button></>}>
          {quick.error ? <div className="alert danger">{quick.error}</div>
            : !quick.result ? <div className="row"><span className="spinner" /> Sending request…</div>
            : <ResultDetails result={{ ...quick.result, method: quick.tc.method }} />}
        </Modal>
      )}
    </div>
  );
}
