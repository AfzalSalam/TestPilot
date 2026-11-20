import { Activity, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { ApiError } from "@/api/client";
import { useEndpointMutations, useEndpoints } from "@/api/hooks";
import type { Endpoint, HttpMethod } from "@/api/types";
import { useProjectCtx } from "@/components/layout/ProjectLayout";
import { ConfirmDialog, Modal, useToast } from "@/components/ui/overlays";
import { Alert, Badge, Button, Card, EmptyState, Field, Input, MethodBadge, PageSkeleton, Select, Textarea } from "@/components/ui/ui";

const METHODS: HttpMethod[] = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"];

function EndpointModal({ existing, onClose }: { existing?: Endpoint; onClose: () => void }) {
  const { projectId } = useProjectCtx();
  const toast = useToast();
  const { create, update } = useEndpointMutations(projectId);
  const [form, setForm] = useState({ name: existing?.name ?? "", method: (existing?.method ?? "GET") as HttpMethod, path: existing?.path ?? "/", description: existing?.description ?? "" });
  const mutation = existing ? update : create;
  const err = mutation.error instanceof ApiError ? mutation.error : null;
  const fe = err?.fieldErrors ?? {};
  const submit = () => {
    const done = { onSuccess: () => { toast.success(existing ? "Endpoint updated" : "Endpoint registered"); onClose(); } };
    if (existing) update.mutate({ id: existing.id, body: form }, done); else create.mutate(form, done);
  };
  return (
    <Modal title={existing ? "Edit endpoint" : "Register endpoint"} onClose={onClose} footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={mutation.isPending} disabled={!form.name.trim() || !form.path.trim()} onClick={submit}>{existing ? "Save" : "Register"}</Button></>}>
      <form className="stack" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        {err && !Object.keys(fe).length && <Alert tone="danger">{err.message}</Alert>}
        <Field label="Name" error={fe.name}><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="List products" autoFocus /></Field>
        <div className="row" style={{ alignItems: "flex-start" }}>
          <Field label="Method"><Select value={form.method} onChange={(e) => setForm({ ...form, method: e.target.value as HttpMethod })} style={{ width: 120 }}>{METHODS.map((m) => <option key={m}>{m}</option>)}</Select></Field>
          <Field label="Path" className="grow" error={fe.path} hint="Relative to the project base URL, e.g. /products/{id}"><Input value={form.path} onChange={(e) => setForm({ ...form, path: e.target.value })} className="mono" /></Field>
        </div>
        <Field label="Description"><Textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
      </form>
    </Modal>
  );
}

export default function EndpointsPage() {
  const { projectId, canEdit } = useProjectCtx();
  const toast = useToast();
  const { data, isLoading } = useEndpoints(projectId);
  const { remove } = useEndpointMutations(projectId);
  const [editing, setEditing] = useState<Endpoint | "new" | null>(null);
  const [deleting, setDeleting] = useState<Endpoint | null>(null);
  const [q, setQ] = useState("");
  const rows = useMemo(() => (data ?? []).filter((e) => `${e.name} ${e.path} ${e.method}`.toLowerCase().includes(q.toLowerCase())), [data, q]);

  if (isLoading) return <PageSkeleton />;
  return (
    <div className="stack">
      <div className="row between wrap">
        <div className="input-group" style={{ width: 300 }}><Search size={16} /><Input placeholder="Search endpoints…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search endpoints" /></div>
        {canEdit && <Button variant="primary" icon={Plus} onClick={() => setEditing("new")}>Register endpoint</Button>}
      </div>
      <Card>
        {!data?.length ? <EmptyState icon={Activity} title="No endpoints registered" action={canEdit ? <Button variant="primary" icon={Plus} onClick={() => setEditing("new")}>Register endpoint</Button> : undefined}>Endpoints document the operations your API offers. Import an OpenAPI spec to register them all at once.</EmptyState>
          : (
            <div className="table-wrap"><table className="table">
              <thead><tr><th>Method</th><th>Path</th><th>Name</th><th>Source</th>{canEdit && <th />}</tr></thead>
              <tbody>
                {rows.map((e) => (
                  <tr key={e.id}>
                    <td><MethodBadge method={e.method} /></td>
                    <td className="mono">{e.path}</td>
                    <td><div>{e.name}</div>{e.description && <div className="faint truncate" style={{ maxWidth: 360, fontSize: 12.5 }}>{e.description}</div>}</td>
                    <td><Badge tone={e.source === "openapi" ? "accent" : undefined}>{e.source}</Badge></td>
                    {canEdit && <td className="right nowrap"><Button size="sm" variant="ghost" iconOnly icon={Pencil} aria-label={`Edit ${e.name}`} onClick={() => setEditing(e)} /><Button size="sm" variant="ghost" iconOnly icon={Trash2} aria-label={`Delete ${e.name}`} onClick={() => setDeleting(e)} /></td>}
                  </tr>
                ))}
                {!rows.length && <tr><td colSpan={5} className="faint" style={{ textAlign: "center", padding: 28 }}>No endpoints match “{q}”.</td></tr>}
              </tbody>
            </table></div>
          )}
      </Card>
      {editing && <EndpointModal existing={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} />}
      {deleting && <ConfirmDialog title="Delete endpoint" message={<>Delete <b>{deleting.method} {deleting.path}</b>? Test cases linked to it are kept.</>} loading={remove.isPending}
        onClose={() => setDeleting(null)} onConfirm={() => remove.mutate(deleting.id, { onSuccess: () => { toast.success("Endpoint deleted"); setDeleting(null); } })} />}
    </div>
  );
}
